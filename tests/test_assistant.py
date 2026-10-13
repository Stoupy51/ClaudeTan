""" Claude-tan's reactions to the session's hook events, and the queue that keeps commands from being typed during a turn. """
# Imports
from ctypes import windll

import pytest
from PySide6.QtWidgets import QApplication

import claudetan.app
import claudetan.config
from claudetan.actions import VK_MUTE
from claudetan.app import Assistant
from claudetan.config import DEFAULTS, Config
from claudetan.overlay.avatar import Avatar, Pill
from claudetan.session import JsonDict


# Functions
@pytest.fixture
def assistant(app: QApplication, monkeypatch: pytest.MonkeyPatch) -> Assistant:
	monkeypatch.setattr(claudetan.app, "chime", mute)
	monkeypatch.setattr(claudetan.config, "USER_CONFIG", DEFAULTS)
	return Assistant(Avatar(), Pill(), Config.load())


def mute(*_notes: float) -> None:
	""" Stands in for the chimes, which would ring on the speakers during the tests. """


def hook(name: str, **fields: object) -> JsonDict:
	return {"hook_event_name": name, **fields}


def test_commands_wait_for_the_running_turn(assistant: Assistant) -> None:
	sent: list[str] = []
	assistant.send.connect(sent.append)
	assistant.on_command("ouvre Spotify")
	assistant.on_hook(hook("UserPromptSubmit", prompt="ouvre Spotify"))
	assistant.on_command("mets de la musique")
	assert sent == ["ouvre Spotify"]

	assistant.on_hook(hook("Stop", last_assistant_message="Spotify est ouvert."))
	assert sent == ["ouvre Spotify", "mets de la musique"]


def test_commands_wait_for_a_compaction_between_turns(assistant: Assistant) -> None:
	sent: list[str] = []
	assistant.send.connect(sent.append)
	assistant.on_hook(hook("PreCompact", trigger="manual", custom_instructions=None))
	assistant.on_command("ouvre Spotify")
	assert sent == []

	assistant.on_hook(hook("PostCompact", trigger="manual", compact_summary="Résumé"))
	assert sent == ["ouvre Spotify"]


def test_an_automatic_compaction_keeps_the_turn_running(assistant: Assistant) -> None:
	sent: list[str] = []
	assistant.send.connect(sent.append)
	assistant.on_hook(hook("UserPromptSubmit", prompt="range le projet"))
	assistant.on_hook(hook("PreCompact", trigger="auto", custom_instructions=None))
	assistant.on_hook(hook("PostCompact", trigger="auto", compact_summary="Résumé"))
	assistant.on_command("ouvre Spotify")
	assert sent == []


def test_background_work_keeps_the_pill_until_its_result(assistant: Assistant) -> None:
	assistant.on_hook(hook("UserPromptSubmit", prompt="range le projet"))
	assistant.on_hook(hook("SubagentStart", agent_id="a1", agent_type="expert"))
	assistant.on_hook(hook("Stop", last_assistant_message="Je confie ça à l'expert."))
	assistant.leave()
	assert assistant.pill.isVisible()

	assistant.on_hook(hook("SubagentStop", agent_id="a1", agent_type="expert", last_assistant_message="Rangé."))
	assistant.on_hook(hook("UserPromptSubmit", prompt="L'expert a fini."))
	assistant.on_hook(hook("Stop", last_assistant_message="Le projet est rangé."))
	assert not assistant.pill.isVisible()
	assert assistant.avatar.bubble.text == "Le projet est rangé."


def test_permission_is_asked_then_thanked(assistant: Assistant) -> None:
	command = {"command": "rm -r build", "description": "Supprime build"}
	assistant.on_hook(hook("UserPromptSubmit", prompt="supprime le dossier build"))
	assistant.on_hook(hook("PreToolUse", tool_name="Bash", tool_input=command, tool_use_id="t1"))
	assistant.on_hook(hook("PermissionRequest", tool_name="Bash", tool_input=command))
	assert assistant.avatar.expression == "please"

	assistant.on_hook(hook("PostToolUse", tool_name="Bash", tool_input=command, tool_response={}, tool_use_id="t1"))
	assert assistant.avatar.expression == "thanks"



def test_local_actions_skip_the_session(assistant: Assistant, monkeypatch: pytest.MonkeyPatch) -> None:
	keys: list[int] = []
	def press(key: int, _scan: int, flags: int, _extra: int) -> None:
		if not flags:
			keys.append(key)
	monkeypatch.setattr(windll.user32, "keybd_event", press)
	sent: list[str] = []
	assistant.send.connect(sent.append)
	assistant.on_command("Coupe le son.")
	assert keys == [VK_MUTE]
	assert sent == []
	assert assistant.avatar.expression == "present"


def test_stopping_everything_restarts_the_session_and_forgets_the_work(assistant: Assistant) -> None:
	restarts: list[bool] = []
	assistant.restart.connect(lambda: restarts.append(True))
	assistant.on_hook(hook("UserPromptSubmit", prompt="range le projet"))
	assistant.on_hook(hook("SubagentStart", agent_id="worker"))
	assistant.on_command("Stop.")
	assert restarts == [True]
	assert not assistant.busy
	assert not assistant.agents
	assert assistant.avatar.expression == "present"


def test_settings_of_a_new_app_restart_it_once_she_is_free(assistant: Assistant, monkeypatch: pytest.MonkeyPatch) -> None:
	restarts: list[bool] = []
	assistant.restart.connect(lambda: restarts.append(True))
	config = Config.load()
	assistant.on_config(config, ["wake"])
	assistant.leave()
	assert restarts == []

	assistant.on_hook(hook("UserPromptSubmit", prompt="range le projet"))
	assistant.on_config(config, ["prompt"])
	assistant.leave()
	assert restarts == []

	assistant.on_hook(hook("Stop", last_assistant_message="C'est rangé."))
	assistant.leave()
	assert restarts == [True]

