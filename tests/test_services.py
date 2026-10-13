""" The timer, the weather and the program launcher she offers. """
# Imports
import os
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication
from stouputils.typing import JsonDict

from claudetan.actions import ALARMS, route
from claudetan.services import claude, programs, weather


# Functions
def test_a_timer_set_by_voice_rings_with_what_it_is_for(app: QApplication) -> None:
	action, arguments = route("Mets un minuteur de 0 secondes.") or (None, {})
	assert action
	rang: list[str] = []
	ALARMS.rang.connect(rang.append)
	assert action.run({**arguments, "label": "les pâtes"}) == "Minuteur de 0 s lancé."
	while not rang:
		app.processEvents()
	assert rang == ["les pâtes"]


def test_the_weather_of_a_city_is_told_in_words(monkeypatch: pytest.MonkeyPatch) -> None:
	def get(url: str, _query: JsonDict) -> JsonDict:
		if url == weather.GEOCODING:
			return {"results": [{"name": "Rennes", "latitude": 48.1, "longitude": -1.7}]}
		return {
			"current": {"weather_code": 61, "temperature_2m": 14.4, "apparent_temperature": 12.6, "wind_speed_10m": 20.0},
			"daily": {"temperature_2m_min": [9.0], "temperature_2m_max": [16.2], "precipitation_probability_max": [70]},
		}
	monkeypatch.setattr(weather, "get", get)
	assert weather.forecast("Rennes") == (
		"Rennes : pluie faible, 14 °C (ressenti 13), vent 20 km/h. Aujourd'hui entre 9 et 16 °C, 70 % de risque de pluie."
	)


def test_a_program_is_found_by_part_of_its_shortcut_name_closest_first(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
	for name in ("Discord Canary.lnk", "Discord.lnk", "Steam.lnk"):
		(tmp_path / name).touch()
	started: list[str] = []
	monkeypatch.setattr(programs, "START_MENUS", (tmp_path,))
	def startfile(path: str) -> None:
		started.append(Path(path).stem)
	monkeypatch.setattr(os, "startfile", startfile)
	assert programs.launch("disc") == "J'ouvre Discord."
	assert started == ["Discord"]
	assert programs.launch("word") == "Je ne trouve pas de programme word."


def test_the_plan_usage_and_the_context_come_from_the_slash_commands_output(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
	outputs = {
		"/usage": (
			"You are currently using your subscription\n\n"
			"Current session: 22% used \u00b7 resets Oct 14, 1:30am (Europe/Paris)\n"
			"Current week (all models): 27% used \u00b7 resets Oct 19, 12am (Europe/Paris)\n"
		),
		"/context": "## Context Usage\n\n**Model:** claude-sonnet-5-5  \n**Tokens:** 107.6k / 1m (11%)\n\n### Estimated usage\n",
	}
	def panel(command: str, *_options: str) -> str:
		return outputs[command]
	monkeypatch.setattr(claude, "panel", panel)
	monkeypatch.setattr(claude, "SESSION_ID", tmp_path / "session_id")
	assert claude.context() == "Il n'y a pas encore de conversation."

	claude.SESSION_ID.write_text("abc")
	assert claude.context() == "Contexte de claude-sonnet-5-5 : 107.6k / 1m (11%)."
	assert claude.plan_usage() == (
		"22 % de la fenêtre de 5 heures (renouvelée Oct 14, 1:30am (Europe/Paris)), "
		"27 % de la semaine (renouvelée Oct 19, 12am (Europe/Paris))."
	)

