""" The hidden session's changes to the app's code: reloaded in place when they can be, put aside when they break the app. """
# Imports
import importlib
import json
import os
import shutil
import subprocess
import sys
import threading
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
from PySide6.QtWidgets import QApplication

from claudetan import config, reload
from claudetan.launcher import git, set_aside
from claudetan.reload import PACKAGE, Reloader, reload_order

# Constants
COUNTER: str = """
from functools import partial
from threading import Event

from PySide6.QtCore import QObject, Signal

STEP: int = 1
TICKS: list[int] = []


class Counter(QObject):
	ticked = Signal()

	def __init__(self) -> None:
		super().__init__()
		self.count = 0
		self.ticked.connect(self.on_tick)
		self.ticked.connect(partial(record, self))

	def on_tick(self) -> None:
		self.count += STEP


def record(counter: Counter) -> None:
	TICKS.append(counter.count)


def wait(started: Event, done: Event) -> None:
	started.set()
	done.wait()


COUNTER: Counter = Counter()
"""
""" A module holding a live object connected to its own method and to a `partial` of a function, and a function a thread waits in. """
END_TO_END: str = """
import json

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

application = QApplication([])
from claudetan import app, config, reload
from claudetan.overlay.avatar import Avatar, Pill


class Listener(QObject):
	cancelled = Signal()


def edit(name: str, old: str, new: str) -> None:
	path = reload.PACKAGE / name
	path.write_text(path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")


assistant = app.Assistant(Avatar(), Pill(), config.Config.load())
listener = Listener()
listener.cancelled.connect(assistant.on_cancel)
reloader = reload.Reloader()
restarts: list[str] = []
reloader.restart.connect(restarts.append)

edit("config.py", "# Classes", "EXTRA: int = 1\\n\\n\\n# Classes")
edit("app.py", "Okay, forget it.", "Okay, dropped.")
reloader.apply()
listener.cancelled.emit()
bubble = assistant.avatar.bubble.text
edit("app.py", "self.busy = False\\n", "self.busy = False\\n\\t\\tself.extra = 0\\n")
reloader.apply()
same_config = config.Config.load() == assistant.config
print(json.dumps({"package": str(reload.PACKAGE), "bubble": bubble, "same_config": same_config, "restarts": len(restarts)}))
"""
""" Builds her `Assistant` from a copy of the app, and reloads a change reaching every module, then one to `Assistant.__init__`. """


# Functions
@pytest.fixture
def hot(app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
	""" The module `hot.counter` of `COUNTER`, in a git repository taken as the app's, with a thread waiting in it. """
	package = tmp_path / "hot"
	package.mkdir()
	(package / "__init__.py").write_text("", encoding="utf-8")
	(package / "counter.py").write_text(COUNTER, encoding="utf-8")
	commit(tmp_path, monkeypatch)
	monkeypatch.setattr(reload, "PACKAGE", package)
	monkeypatch.setattr(config, "ROOT", tmp_path)
	monkeypatch.setattr(sys, "path", [str(tmp_path), *sys.path])
	module = importlib.import_module("hot.counter")
	started, done = threading.Event(), threading.Event()
	threading.Thread(target=module.wait, args=(started, done), daemon=True).start()
	started.wait()
	yield module
	done.set()
	del sys.modules["hot.counter"], sys.modules["hot"]


def commit(repository: Path, monkeypatch: pytest.MonkeyPatch) -> str:
	""" Commits what the folder holds, as a new git repository, and returns the commit. """
	config_file = repository.parent / "gitconfig"
	config_file.write_text("[user]\n\tname = Claude-tan\n\temail = claude-tan@localhost\n", encoding="utf-8")
	monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config_file))
	git(repository, "init")
	git(repository, "add", ".")
	git(repository, "commit", "--message", "Good")
	return git(repository, "rev-parse", "HEAD")


def edit(module: ModuleType, old: str, new: str) -> None:
	path = Path(str(module.__file__))
	path.write_text(path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")


def test_live_objects_run_the_new_code_and_keep_their_state(hot: ModuleType) -> None:
	reloader = Reloader()
	restarts: list[str] = []
	reloader.restart.connect(restarts.append)
	counter, ticks = hot.COUNTER, hot.TICKS
	counter.ticked.emit()

	edit(hot, "STEP: int = 1", "STEP: int = 10")
	edit(hot, "TICKS.append(counter.count)", "TICKS.append(-counter.count)")
	edit(hot, "self.count += STEP\n", "self.count += STEP\n\n\tdef doubled(self) -> int:\n\t\treturn 2 * self.count\n")
	reloader.apply()
	counter.ticked.emit()
	assert not restarts
	assert hot.COUNTER is counter and hot.TICKS is ticks == [1, -11]
	assert counter.doubled() == 22
	assert isinstance(counter, hot.Counter) and hot.Counter().count == 0


@pytest.mark.parametrize(("old", "new"), [
	("self.count = 0\n", "self.count = 0\n\t\tself.name = ''\n"),
	("ticked = Signal()", "ticked = Signal(int)"),
	("done.wait()", "done.wait(60)"),
])
def test_a_change_to_what_built_a_live_object_or_to_running_code_restarts_the_app(hot: ModuleType, old: str, new: str) -> None:
	reloader = Reloader()
	restarts: list[str] = []
	reloader.restart.connect(restarts.append)
	edit(hot, old, new)
	reloader.apply()
	assert json.loads(restarts[0])["files"] == [hot.__file__]


@pytest.mark.parametrize(("broken", "error"), [("STEP: int = MISSING", "NameError"), ("STEP: int = (", "SyntaxError")])
def test_a_change_that_fails_to_load_is_put_aside_and_the_old_code_kept(hot: ModuleType, broken: str, error: str) -> None:
	reloader = Reloader()
	errors: list[str] = []
	reloader.broken.connect(errors.append)
	counter = hot.COUNTER

	edit(hot, "STEP: int = 1", broken)
	reloader.apply()
	assert [message.split(":")[0] for message in errors] == [error]
	assert "STEP: int = 1" in Path(str(hot.__file__)).read_text(encoding="utf-8")
	assert hot.COUNTER is counter and hot.STEP == 1


def test_modules_reload_after_those_they_take_names_from() -> None:
	importlib.import_module("claudetan.app")
	order = reload_order({"claudetan.overlay.avatar"})
	assert order.index("claudetan.overlay.avatar") < order.index("claudetan.overlay.tray")
	assert "claudetan.app" not in order


def test_the_app_reloads_its_own_modules_in_place_from_a_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
	package = tmp_path / "src" / "claudetan"
	shutil.copytree(PACKAGE, package, ignore=shutil.ignore_patterns("__pycache__"))
	shutil.copytree(reload.ASSETS, tmp_path / "assets")
	commit(tmp_path, monkeypatch)
	env = os.environ | {"PYTHONPATH": str(package.parent), "APPDATA": str(tmp_path), "QT_QPA_PLATFORM": "offscreen"}
	run = subprocess.run([sys.executable, "-c", END_TO_END], cwd=tmp_path, env=env, capture_output=True, text=True, check=False)
	assert run.returncode == 0, run.stderr
	result = json.loads(run.stdout.splitlines()[-1])
	assert result == {"package": str(package), "bubble": "Okay, dropped.", "same_config": True, "restarts": 1}


def test_a_broken_change_is_stashed_and_its_commits_reverted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
	repository = tmp_path / "repository"
	repository.mkdir()
	action = repository / "action.py"
	action.write_text("good\n", encoding="utf-8")
	since = commit(repository, monkeypatch)

	action.write_text("committed\n", encoding="utf-8")
	git(repository, "commit", "--all", "--message", "Broken")
	action.write_text("left uncommitted\n", encoding="utf-8")
	added = repository / "added.py"
	added.write_text("new\n", encoding="utf-8")
	set_aside([str(action), str(added)], since)

	assert action.read_text(encoding="utf-8") == "good\n"
	assert not added.exists()
	assert "a change that broke the app" in git(repository, "stash", "list")

