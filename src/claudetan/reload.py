""" Applies the hidden session's changes to the app's code: a changed module reloads in place when nothing running holds its objects.

A module that takes names from another with `from ... import` keeps the old objects when only the other reloads, so it reloads with it.
A change reaching one of `LIVE` restarts the app instead, through the launcher, on the same conversation.
"""
# Imports
import ast
import importlib
import json
import logging
import sys
from graphlib import TopologicalSorter
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from claudetan import actions
from claudetan.config import ROOT
from claudetan.launcher import git, set_aside
from claudetan.mcp import tool
from claudetan.session import JsonDict

# Constants
LOG: logging.Logger = logging.getLogger("claudetan")
PACKAGE: Path = Path(__file__).parent
EDIT_TOOLS: frozenset[str] = frozenset({"Edit", "Write", "MultiEdit"})
LIVE: tuple[str, ...] = (
	"claudetan.app", "claudetan.config", "claudetan.session", "claudetan.mcp", "claudetan.reload", "claudetan.launcher",
	"claudetan.windows", "claudetan.voice", "claudetan.services.alarms",
)
""" Modules, with their submodules, that the running app holds objects of: the windows, the session, the microphone, the timers. """


# Classes
class Reloader(QObject):
	""" Gathers the files the hidden session edits, and applies the change once it has nothing running. """
	restart = Signal(str)
	""" The change needs the app started again: the line telling the launcher what it is, should the app then fail to start. """
	tools_changed = Signal()
	""" The reloaded actions changed the session's tools, which it reads only when it starts. """
	reloaded = Signal(list)
	""" The modules just reloaded, for the windows to be built again from them. """
	broken = Signal(str)
	""" The change failed to load, and was put aside in git: the error. """

	def __init__(self) -> None:
		super().__init__()
		self.edited: set[Path] = set()
		self.modified = {path: path.stat().st_mtime_ns for path in PACKAGE.rglob("*.py")}
		""" When each source file was last written, which catches the edits made through a shell instead of an edit tool. """
		self.since = git(ROOT, "rev-parse", "HEAD")
		""" The commit the running code was loaded from, after which the session's commits belong to its change. """

	def on_hook(self, event: JsonDict) -> None:
		if event["hook_event_name"] == "PostToolUse" and event["tool_name"] in EDIT_TOOLS:
			path = Path(event["tool_input"]["file_path"]).resolve()
			if path.is_relative_to(ROOT):
				self.edited.add(path)

	def apply(self) -> None:
		for path in PACKAGE.rglob("*.py"):
			if self.modified.get(path) != (written := path.stat().st_mtime_ns):
				self.modified[path] = written
				self.edited.add(path.resolve())

		if not self.edited:
			return
		files = sorted(str(path) for path in self.edited)
		order = reload_order({module for path in self.edited if (module := module_name(path)) in sys.modules})
		if order is None:
			LOG.info("Restarting for: %s", ", ".join(files))
			self.restart.emit(json.dumps({"files": files, "since": self.since}))
			return

		self.edited.clear()
		tools = [tool(action) for action in actions.ACTIONS]
		try:
			reload(order)
			LOG.info("Reloaded: %s", ", ".join(order))
		except Exception as error:
			LOG.exception("Change put aside, it broke %s", ", ".join(order))
			set_aside(files, self.since)
			reload(order)
			self.broken.emit(f"{type(error).__name__}: {error}")
		self.since = git(ROOT, "rev-parse", "HEAD")
		self.reloaded.emit(order)
		if [tool(action) for action in actions.ACTIONS] != tools:
			self.tools_changed.emit()


# Functions
def module_name(path: Path) -> str | None:
	""" The module of one of the app's source files, None for any other file.

	>>> module_name(PACKAGE / "services" / "weather.py")
	'claudetan.services.weather'
	>>> module_name(PACKAGE / "voice" / "__init__.py")
	'claudetan.voice'
	>>> module_name(PACKAGE / "config.toml") is None
	True
	"""
	if path.suffix != ".py" or not path.is_relative_to(PACKAGE):
		return None
	parts = path.relative_to(PACKAGE.parent).with_suffix("").parts
	return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def reload_order(changed: set[str]) -> list[str] | None:
	""" The loaded modules to reload for `changed` to apply, each after those it takes names from, None when the app must restart. """
	takes_from = {
		name: names_taken(Path(module.__file__))
		for name, module in list(sys.modules.items()) if name.split(".")[0] == "claudetan" and module.__file__
	}
	reloaded = set(changed)
	while dependents := {name for name, taken in takes_from.items() if taken & reloaded} - reloaded:
		reloaded |= dependents
	if any(name == live or name.startswith(f"{live}.") for name in reloaded for live in LIVE):
		return None
	return list(TopologicalSorter({name: takes_from[name] & reloaded for name in reloaded}).static_order())


def names_taken(source: Path) -> set[str]:
	""" The app's modules that a module's top-level `from ... import` takes names other than submodules from. """
	return {
		statement.module for statement in ast.parse(source.read_bytes()).body
		if isinstance(statement, ast.ImportFrom) and statement.module and statement.module.split(".")[0] == "claudetan"
		and any(f"{statement.module}.{alias.name}" not in sys.modules for alias in statement.names)
	}


def reload(order: list[str]) -> None:
	for name in order:
		importlib.reload(sys.modules[name])

