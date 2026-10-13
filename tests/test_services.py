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


def test_the_plan_usage_and_the_context_are_laid_out_for_a_human(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
	outputs = {
		"/usage": (
			"You are currently using your subscription\n\n"
			"Current session: 22% used · resets Oct 14, 1:30am (Europe/Paris)\n"
			"Current week (all models): 27% used · resets Oct 19, 12am (Europe/Paris)\n"
		),
		"/context": (
			"## Context Usage\n\n**Model:** claude-sonnet-5-5  \n**Tokens:** 330.3k / 1m (33%)\n\n### Estimated usage by category\n\n"
			"| Category | Tokens | Percentage |\n|----------|--------|------------|\n"
			"| System prompt | 3.4k | 0.3% |\n| System tools | 20.6k | 2.1% |\n| MCP server instructions | 717 | 0.1% |\n"
			"| MCP tools (deferred) | 2.4k | 0.2% |\n| Memory files | 8.6k | 0.9% |\n| Skills | 6.4k | 0.6% |\n"
			"| Messages | 290.6k | 29.1% |\n| Free space | 636.7k | 63.7% |\n\n### MCP Tools\n\n| Tool | Server | Tokens |\n"
			"| mcp__x | x | 162 |\n"
		),
	}
	def panel(command: str, *_options: str) -> str:
		return outputs[command]
	monkeypatch.setattr(claude, "panel", panel)
	monkeypatch.setattr(claude, "SESSION_ID", tmp_path / "session_id")
	assert str(claude.context()) == "Il n'y a pas encore de conversation."


	claude.SESSION_ID.write_text("abc")
	report = claude.context()
	assert [part.key for part in report.slices][:2] == ["Messages", "System tools"]
	assert str(report) == (
		"Contexte : 330,3k / 1m (33\u00a0%)\n"
		"Modèle : claude-sonnet-5-5\n"
		"Messages : 290,6k (29,1\u00a0%)\n"
		"Outils : 20,6k (2,1\u00a0%)\n"
		"Mémoire : 8,6k (0,9\u00a0%)\n"
		"Skills : 6,4k (0,6\u00a0%)\n"
		"Prompt : 3,4k (0,3\u00a0%)\n"
		"Consignes MCP : 717 (0,1\u00a0%)\n"
		"Libre : 636,7k (63,7\u00a0%)"
	)
	assert claude.plan_usage() == (
		"Forfait Claude\nFenêtre de 5 h : 22\u00a0% utilisés, renouvelée Oct 14, 1:30am\n"
		"Semaine : 27\u00a0% utilisés, renouvelée Oct 19, 12am"
	)

