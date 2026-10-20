""" The hidden session's changes to the app's code: reloaded in place when they can be, put aside when they break the app. """
# Imports
import importlib
import json
import os
from pathlib import Path

import pytest

from claudetan import actions
from claudetan.launcher import git, set_aside
from claudetan.reload import PACKAGE, Reloader, reload_order


# Functions
def test_actions_and_services_reload_alone_and_the_rest_restarts_the_app() -> None:
	importlib.import_module("claudetan.app")
	assert reload_order({"claudetan.services.weather"}) == ["claudetan.services.weather"]
	assert reload_order({"claudetan.actions"}) == ["claudetan.actions"]
	assert reload_order({"claudetan.i18n"}) is None
	assert reload_order({"claudetan.voice.listener"}) is None

	overlay = reload_order({"claudetan.overlay.avatar"})
	assert overlay is not None and overlay.index("claudetan.overlay.avatar") < overlay.index("claudetan.overlay.tray")
	assert "claudetan.app" not in overlay
	assert reload_order({"claudetan.windows"}) is None


def test_an_edited_action_reloads_in_place_and_an_edited_session_restarts_the_app() -> None:
	reloader = Reloader()
	restarts: list[str] = []
	reloader.restart.connect(restarts.append)
	loaded = actions.ACTIONS

	reloader.on_hook(edit(PACKAGE / "actions.py"))
	reloader.apply()
	assert actions.ACTIONS is not loaded
	assert not restarts

	session = (PACKAGE / "session.py").resolve()
	reloader.on_hook(edit(session))
	reloader.apply()
	assert json.loads(restarts[0])["files"] == [str(session)]


def test_a_file_written_by_a_shell_restarts_the_app_like_an_edited_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
	package = tmp_path / "claudetan"
	package.mkdir()
	session = package / "session.py"
	session.write_text("old\n", encoding="utf-8")
	monkeypatch.setattr("claudetan.reload.PACKAGE", package)
	importlib.import_module("claudetan.session")
	reloader = Reloader()
	restarts: list[str] = []
	reloader.restart.connect(restarts.append)
	reloader.apply()
	assert not restarts

	os.utime(session, ns=(1, 1))
	reloader.apply()
	assert json.loads(restarts[0])["files"] == [str(session.resolve())]


def test_a_broken_change_is_stashed_and_its_commits_reverted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
	config = tmp_path / "gitconfig"
	config.write_text("[user]\n\tname = Claude-tan\n\temail = claude-tan@localhost\n", encoding="utf-8")
	monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
	repository = tmp_path / "repository"
	repository.mkdir()
	action = repository / "action.py"
	action.write_text("good\n", encoding="utf-8")
	git(repository, "init")
	git(repository, "add", ".")
	git(repository, "commit", "--message", "Good")
	since = git(repository, "rev-parse", "HEAD")

	action.write_text("committed\n", encoding="utf-8")
	git(repository, "commit", "--all", "--message", "Broken")
	action.write_text("left uncommitted\n", encoding="utf-8")
	added = repository / "added.py"
	added.write_text("new\n", encoding="utf-8")
	set_aside([str(action), str(added)], since)

	assert action.read_text(encoding="utf-8") == "good\n"
	assert not added.exists()
	assert "a change that broke the app" in git(repository, "stash", "list")


def edit(path: Path) -> dict[str, object]:
	""" The hook the session posts once its `Edit` tool changed the file. """
	return {"hook_event_name": "PostToolUse", "tool_name": "Edit", "tool_input": {"file_path": str(path)}}

