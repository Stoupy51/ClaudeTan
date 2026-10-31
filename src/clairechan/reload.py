""" Applies the hidden session's changes to the app's code in place once it has nothing running, restarting the app only when it must.

A changed module and those taking names from it with `from ... import` run again in their own namespace, as `importlib.reload` does.
Besides, every object of their functions takes the new code, wherever the app holds it, such as in a `partial` or a thread,
each class keeps its identity and takes its new members, so that its live objects run the new methods,
and a module-level statement that did not change keeps its value, such as a timer, a cache or a permission given.
The app restarts when a live object comes from changed code: a running loop, or an object built by a changed `__init__`.
"""
# Imports
import ast
import builtins
import gc
import importlib
import json
import logging
import sys
from collections import defaultdict
from collections.abc import Callable, Iterator
from graphlib import TopologicalSorter
from pathlib import Path
from types import FrameType, FunctionType, GeneratorType, ModuleType

from PySide6.QtCore import QObject, Signal

from clairechan import actions, config, launcher, mcp, windows

# Constants
LOG: logging.Logger = logging.getLogger("clairechan")
PACKAGE: Path = Path(__file__).parent
ASSETS: Path = config.ROOT / "assets"
""" Images the overlay loads when its windows are built, built again when one changes. """
BUILD_CLASS: Callable[..., type] = builtins.__build_class__
VALUES: tuple[type[ast.stmt], ...] = (ast.Assign, ast.AnnAssign)
UPDATED_METACLASSES: tuple[type, ...] = (type, type(QObject))
""" Metaclasses whose classes take new members; the others, such as ctypes structures, are created anew. """
FIXED_MEMBERS: frozenset[str] = frozenset({"__dict__", "__weakref__", "staticMetaObject"})
""" Members a class gets from Python or Qt when it is created, which no other class may give it. """


# Classes
class Reloader(QObject):
	""" Applies the changes made to the app's files since it loaded them. """
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
		self.loaded = watched_files()
		""" The content of each file as the running app loaded it. """
		self.since = launcher.git(config.ROOT, "rev-parse", "HEAD")
		""" The commit the running code was loaded from, after which the session's commits belong to its change. """

	def apply(self) -> None:
		files = watched_files()
		edited = sorted(str(path) for path, content in files.items() if self.loaded.get(path) != content)
		if not edited:
			return

		try:
			order = reload_order({module for path in edited if (module := module_name(Path(path))) in sys.modules})
			reason = restart_reason(order, self.loaded)
		except SyntaxError as error:
			self.put_aside(edited, error)
			return

		if reason:
			LOG.info("Restarting, as %s, for: %s", reason, ", ".join(edited))
			self.restart.emit(json.dumps({"files": edited, "since": self.since}))
			return

		tools = [mcp.tool(action) for action in actions.ACTIONS]
		try:
			reload(order, self.loaded)
		except Exception as error:
			self.put_aside(edited, error)
			reload(order, files)
		else:
			LOG.info("Reloaded: %s", ", ".join(order))
			self.since = launcher.git(config.ROOT, "rev-parse", "HEAD")
		self.loaded = watched_files()
		self.reloaded.emit([*order, windows.OVERLAY] if any(Path(path).is_relative_to(ASSETS) for path in edited) else order)
		if [mcp.tool(action) for action in actions.ACTIONS] != tools:
			self.tools_changed.emit()

	def put_aside(self, edited: list[str], error: Exception) -> None:
		""" Undoes in git a change that failed to load, and tells why. """
		LOG.exception("Change put aside: %s", ", ".join(edited))
		launcher.set_aside(edited, self.since)
		self.since = launcher.git(config.ROOT, "rev-parse", "HEAD")
		self.broken.emit(f"{type(error).__name__}: {error}")


# Functions
def watched_files() -> dict[Path, bytes]:
	return {path: path.read_bytes() for path in [*PACKAGE.rglob("*.py"), *ASSETS.rglob("*.png")]}


def module_name(path: Path) -> str | None:
	""" The module of one of the app's source files, None for any other file.

	>>> module_name(PACKAGE / "services" / "weather.py")
	'clairechan.services.weather'
	>>> module_name(PACKAGE / "voice" / "__init__.py")
	'clairechan.voice'
	>>> module_name(PACKAGE / "config.toml") is None
	True
	"""
	if path.suffix != ".py" or not path.is_relative_to(PACKAGE):
		return None
	parts = path.relative_to(PACKAGE.parent).with_suffix("").parts
	return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def reload_order(changed: set[str]) -> list[str]:
	""" The loaded modules to reload for `changed` to apply, each after those it takes names from. """
	takes_from = {
		name: names_taken(Path(module.__file__))
		for name, module in list(sys.modules.items()) if name.split(".")[0] == PACKAGE.name and module.__file__
	}
	reloaded = set(changed)
	while dependents := {name for name, taken in takes_from.items() if taken & reloaded} - reloaded:
		reloaded |= dependents
	return list(TopologicalSorter({name: takes_from[name] & reloaded for name in reloaded}).static_order())


def names_taken(source: Path) -> set[str]:
	""" The app's modules that a module's top-level `from ... import` takes names other than submodules from. """
	return {
		statement.module for statement in ast.parse(source.read_bytes()).body
		if isinstance(statement, ast.ImportFrom) and statement.module and statement.module.split(".")[0] == PACKAGE.name
		and any(f"{statement.module}.{alias.name}" not in sys.modules for alias in statement.names)
	}


def restart_reason(order: list[str], loaded: dict[Path, bytes]) -> str | None:
	""" Why the modules cannot reload in place, None when they can.

	The objects of `clairechan.overlay` do not count, since `Windows` builds them again.
	"""
	if __name__ in order:
		return "the reloader changed"
	objects: list[object] = gc.get_objects()
	alive = {type(value) for value in objects}
	running = {(frame.f_code.co_filename, frame.f_code.co_qualname.split(".<locals>")[0]) for frame in frames(objects)}
	for name in order:
		module = sys.modules[name]
		path = Path(str(module.__file__))
		old, new = definitions(loaded[path]), definitions(path.read_bytes())
		statements = old | new
		changed = changed_names(old, new)
		values = {qualname for qualname in changed if isinstance(statements[qualname], VALUES)}
		runs = [qualname for file, qualname in running if file == module.__file__ and qualname in old]
		if changed_runs := [qualname for qualname in runs if qualname in changed or reads(old[qualname]) & values]:
			return f"{name}.{changed_runs[0]} runs"
		if built := [kind for kind in live_classes(module, alive) if built_by(kind.__qualname__, statements) & changed]:
			return f"objects of {name}.{built[0].__qualname__} are alive"
	return None


def frames(objects: list[object]) -> Iterator[FrameType]:
	""" Every frame running on a thread or waiting in a generator, with those it was called from. """
	generators = [value.gi_frame for value in objects if isinstance(value, GeneratorType) and value.gi_frame]
	# No public API gives the frames of the other threads, where her microphone and voice loop
	for frame in [*sys._current_frames().values(), *generators]:  # pyright: ignore[reportPrivateUsage]
		while frame:
			yield frame
			frame = frame.f_back


def live_classes(module: ModuleType, alive: set[type]) -> list[type]:
	""" The module's classes that have objects alive, but those `Windows` builds again. """
	if module.__name__.startswith(windows.OVERLAY):
		return []
	classes = [value for value in vars(module).values() if isinstance(value, type) and value.__module__ == module.__name__]
	return [kind for kind in classes if any(issubclass(other, kind) for other in alive)]


def definitions(source: bytes) -> dict[str, ast.stmt]:
	""" The statements of a module and of its classes' bodies, by the name they bind, such as `Assistant.on_hook`.

	>>> sorted(definitions(b"X = 1\\nclass A:\\n\\tsent = Signal()\\n\\tdef f(self) -> None: ..."))
	['A.f', 'A.sent', 'X']
	"""
	found: dict[str, ast.stmt] = {}
	for statement in ast.parse(source).body:
		found |= dict.fromkeys(bound(statement), statement)
		if isinstance(statement, ast.ClassDef):
			found |= {f"{statement.name}.{name}": member for member in statement.body for name in bound(member)}
	return found


def bound(statement: ast.stmt) -> list[str]:
	""" The names an assignment or a function definition binds, none for any other statement. """
	match statement:
		case ast.FunctionDef(name=name) | ast.AsyncFunctionDef(name=name):
			return [name]
		case ast.Assign(targets=targets):
			return [node.id for target in targets for node in ast.walk(target) if isinstance(node, ast.Name)]
		case ast.AnnAssign(target=ast.Name(id=name)):
			return [name]
		case _:
			return []


def changed_names(old: dict[str, ast.stmt], new: dict[str, ast.stmt]) -> set[str]:
	""" The names of `definitions` whose statement changed, with the module-level values computed from a changed name.

	>>> sorted(changed_names(definitions(b"A = 1\\nB = A + 1\\nC = 3"), definitions(b"A = 2\\nB = A + 1\\nC = 3")))
	['A', 'B']
	"""
	changed = (old.keys() ^ new.keys()) | {name for name in old.keys() & new.keys() if ast.dump(old[name]) != ast.dump(new[name])}
	values = {name: statement for name, statement in new.items() if isinstance(statement, VALUES)}
	while spread := {name for name, statement in values.items() if reads(statement) & changed} - changed:
		changed |= spread
	return changed


def reads(statement: ast.stmt) -> set[str]:
	return {node.id for node in ast.walk(statement) if isinstance(node, ast.Name)}


def built_by(class_name: str, statements: dict[str, ast.stmt]) -> set[str]:
	""" What the objects of a class were built from: `__init__` and the values of the class body, such as signals and fields.

	It follows the module's values they read and the functions they call, there or on `self`, but not into other modules:
	a function only passed along, such as a slot, runs its new code anyway.
	"""
	prefix = f"{class_name}."
	fields = [name for name, statement in statements.items() if name.startswith(prefix) and isinstance(statement, VALUES)]
	todo = [f"{prefix}__init__", *fields]
	found: set[str] = set()
	while todo:
		name = todo.pop()
		if name in found or name not in statements:
			continue
		found.add(name)
		called = calls(statements[name])
		todo += [f"{prefix}{call.removeprefix('self.')}" for call in called if call.startswith("self.")]
		todo += [read for read in reads(statements[name]) if read in called or isinstance(statements.get(read), VALUES)]
	return found


def calls(statement: ast.stmt) -> set[str]:
	""" The functions a statement calls by their name, and the methods it calls on `self`, as `self.name`. """
	found: set[str] = set()
	for node in ast.walk(statement):
		match node:
			case ast.Call(func=ast.Name(id=name)):
				found.add(name)
			case ast.Call(func=ast.Attribute(value=ast.Name(id="self"), attr=method)):
				found.add(f"self.{method}")
			case _:
				pass
	return found


def reload(order: list[str], loaded: dict[Path, bytes]) -> None:
	""" Runs the modules again in their namespaces, then gives every object of their functions the new code. """
	files = {str(sys.modules[name].__file__) for name in order}
	before = functions(files)
	for name in order:
		reload_module(sys.modules[name], loaded)

	for key, news in functions(files).items():
		added = [function for function in news if function not in before[key]]
		# Two definitions sharing a name, such as a property's getter and setter, leave nothing to tell which one is new
		if len({function.__code__ for function in added}) != 1:
			continue
		new = added[0]
		# A method that starts or stops calling `super()` changes its closure, which a function object cannot take
		for old in (function for function in before[key] if function.__code__.co_freevars == new.__code__.co_freevars):
			old.__code__, old.__defaults__, old.__kwdefaults__ = new.__code__, new.__defaults__, new.__kwdefaults__


def functions(files: set[str]) -> defaultdict[tuple[str, str], list[FunctionType]]:
	""" Every function object of the source files that is not nested in another function, by file and qualified name. """
	found: defaultdict[tuple[str, str], list[FunctionType]] = defaultdict(list)
	for value in gc.get_objects():
		if isinstance(value, FunctionType) and value.__code__.co_filename in files and "<" not in value.__qualname__:
			found[value.__code__.co_filename, value.__qualname__].append(value)
	return found


def reload_module(module: ModuleType, loaded: dict[Path, bytes]) -> None:
	""" Runs the module again, its classes keeping their identity, and its unchanged module-level statements their value. """
	path = Path(str(module.__file__))
	before = dict(vars(module))
	new = definitions(path.read_bytes())
	kept = [name for name in new.keys() - changed_names(definitions(loaded[path]), new) if "." not in name and name in before]
	classes = {
		value.__qualname__: value for value in before.values() if isinstance(value, type) and value.__module__ == module.__name__
	}

	def build_class(body: FunctionType, name: str, *bases: type, **keywords: object) -> type:
		new_class = BUILD_CLASS(body, name, *bases, **keywords)
		old_class = classes.get(new_class.__qualname__) if body.__globals__ is vars(module) else None
		if (
			old_class is None or type(old_class) not in UPDATED_METACLASSES
			or old_class.__bases__ != new_class.__bases__ or signals(old_class) != signals(new_class)
		):
			return new_class
		update_class(old_class, new_class)
		return old_class

	builtins.__build_class__ = build_class
	try:
		importlib.reload(module)
	finally:
		builtins.__build_class__ = BUILD_CLASS
	vars(module).update({name: before[name] for name in kept})


def signals(kind: type) -> dict[str, str]:
	return {name: str(value) for name, value in vars(kind).items() if isinstance(value, Signal)}


def update_class(old: type, new: type) -> None:
	""" Gives a class the members of its new version, but its signals, which Qt fixed when it created the class. """
	for name, value in vars(new).items():
		if name not in FIXED_MEMBERS and not isinstance(value, Signal):
			setattr(old, name, value)
	for name in vars(old).keys() - vars(new).keys():
		delattr(old, name)
	# The methods calling `super()` share a cell holding their class, which must be the one the objects have
	for value in vars(new).values():
		if isinstance(value, FunctionType) and value.__closure__ and "__class__" in value.__code__.co_freevars:
			value.__closure__[value.__code__.co_freevars.index("__class__")].cell_contents = old

