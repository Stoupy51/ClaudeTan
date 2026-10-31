""" The timer, the weather and the program launcher she offers. """
# Imports
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, override

import pytest
from PySide6.QtWidgets import QApplication
from stouputils.typing import JsonDict

from clairechan import i18n
from clairechan.actions import find, route
from clairechan.services import agents, claude, minecraft, programs, weather
from clairechan.services.alarms import ALARMS


# Functions
def test_a_timer_set_by_voice_rings_with_what_it_is_for(app: QApplication) -> None:
	action, arguments = route("Mets un minuteur de 0 secondes.") or (None, {})
	assert action
	rang: list[str] = []
	ALARMS.rang.connect(rang.append)
	assert action.run({**arguments, "label": "les pâtes"}) == "0 s timer started."
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
		"Rennes: light rain, 14 °C (feels like 13), wind 20 km/h. Today between 9 and 16 °C, 70% chance of rain."
	)


def test_a_program_is_found_by_part_of_its_shortcut_name_closest_first(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
	for name in ("Discord Canary.lnk", "Discord.lnk", "Steam.lnk"):
		(tmp_path / name).touch()
	started: list[str] = []
	monkeypatch.setattr(programs, "START_MENUS", (tmp_path,))
	def startfile(path: str) -> None:
		started.append(Path(path).stem)
	monkeypatch.setattr(os, "startfile", startfile)
	assert programs.launch("disc") == "Opening Discord."
	assert started == ["Discord"]
	assert programs.launch("word") == "I can't find a program called word."


def test_the_plan_usage_and_the_context_are_laid_out_for_a_human_in_french(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
	monkeypatch.setattr(i18n, "heard", "fr")
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


def test_english_requests_reach_the_same_actions_as_french_ones() -> None:
	requests = {
		"Set a timer for 8 seconds.": "timer", "Mets un minuteur de 8 secondes.": "timer",
		"What's the weather in London?": "weather", "Quel temps fait-il à Rennes ?": "weather",
		"Show me the context.": "context", "Quel est le contexte ?": "context",
	}
	routed = {request: (route(request) or (None,))[0] for request in requests}
	assert routed == {request: find(name) for request, name in requests.items()}


def test_a_minecraft_tool_relays_the_bridge_answer_and_says_when_the_client_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
	received: list[JsonDict] = []
	class Bridge(BaseHTTPRequestHandler):
		def do_POST(self) -> None:
			received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
			self.send_response(200)
			self.end_headers()
			self.wfile.write(b'{"ok":true}')

		@override
		def log_message(self, format: str, *args: Any) -> None:
			pass

	server = HTTPServer(("127.0.0.1", 0), Bridge)
	threading.Thread(target=server.handle_request, daemon=True).start()
	monkeypatch.setattr(minecraft, "BRIDGE", f"http://127.0.0.1:{server.server_port}")
	assert find("minecraft_hold").run({"key": "use", "ticks": None}) == '{"ok":true}'
	assert received == [{"key": "use", "ticks": "1"}]

	server.server_close()
	assert find("minecraft_state").run({}) == "The test client is not running: start it with minecraft_start."



def test_the_agent_progress_tells_what_a_running_agent_and_a_finished_one_did(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
	session = tmp_path / "project" / "abc" / "subagents"
	session.mkdir(parents=True)
	monkeypatch.setattr(agents, "PROJECTS", tmp_path)
	monkeypatch.setattr(agents, "SESSION_ID", tmp_path / "session_id")
	(tmp_path / "session_id").write_text("abc", encoding="utf-8")
	started = {"type": "user", "timestamp": "2026-10-18T21:00:00+00:00", "message": {"content": "task"}}

	def call(name: str, tool_input: JsonDict) -> JsonDict:
		block = {"type": "tool_use", "name": name, "input": tool_input}
		return {"type": "assistant", "message": {"stop_reason": "tool_use", "content": [block]}}

	read = call("Read", {"file_path": "D:/x/a.py"})
	for agent, last in (("agent-running", call("Edit", {"file_path": "D:/x/app.py"})), ("agent-done", call("SubagentHandback", {}))):
		(session / f"{agent}.meta.json").write_text(json.dumps({"description": agent}), encoding="utf-8")
		rows = "\n".join(json.dumps(row) for row in (started, read, last))
		(session / f"{agent}.jsonl").write_text(rows, encoding="utf-8")

	report = agents.progress()
	assert "agent-running: running" in report
	assert "2 tool calls, last: edits app.py" in report
	assert "agent-done: finished" in report

