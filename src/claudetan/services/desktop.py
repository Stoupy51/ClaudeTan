""" The windows of the user's applications, read and used through UI Automation without ever taking the focus from a game.

Pressing a button of Firefox and filling a classic Windows field leave the focus where it is.
Any other action brings its window to the front, as UI Automation gives the application that right,
so it waits until the user is away from keyboard and mouse.
"""
# Imports
import ctypes
import functools
import os
import time
from _ctypes import COMError
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from ctypes import windll, wintypes
from dataclasses import dataclass
from pathlib import Path

import uiautomation as auto
from PySide6.QtGui import QImage

from claudetan.config import APP_DATA, Config
from claudetan.i18n import tr

# Constants
COM: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=1, initializer=auto.InitializeUIAutomationInCurrentThread)
""" UI Automation's objects only work on the thread that made them, so every call goes through this one. """
ELEMENTS: dict[str, Element] = {}
""" What the last `read_window` listed, by the number it gave. """
AWAKE: set[int] = set()
""" Processes already asked for their elements: Chromium builds a page's only once a program asks, in about 3 s. """
WAKE_S: float = 4.0
APPROVED: set[str] = set()
""" Applications the user let her act in since the app started. """
ACTING_TOOLS: frozenset[str] = frozenset({"mcp__claudetan__press", "mcp__claudetan__fill"})
NEVER: frozenset[str] = frozenset({"windowsterminal.exe", "openconsole.exe", "conhost.exe", "cmd.exe", "powershell.exe", "pwsh.exe"})
""" Terminals, which would give her a shell outside Claude Code's permissions, whatever the config says. """
LISTED_TYPES: frozenset[str] = frozenset({
	"Button", "CheckBox", "ComboBox", "Edit", "Hyperlink", "ListItem", "MenuItem", "RadioButton", "TabItem", "TreeItem",
})
""" Types of element listed even without a name, as she may act on them. """
MAX_LINES: int = 600
MAX_TEXT: int = 200
""" Letters of a name or a value kept in the listing. """
CAPTURE: Path = APP_DATA / "captures" / "window.png"
""" Where `look_window` draws a window, in a folder the session may read without asking. """
QUIET_S: float = 3.0
""" How long the user leaves keyboard and mouse alone before she does something that brings a window to the front. """
QUIET_WAIT_S: float = 20.0
""" How long she waits for that, within the 30 s a tool call has. """
FULL_SCREEN_STATES: frozenset[int] = frozenset({2, 3, 4})
""" `SHQueryUserNotificationState` values of a full screen application, a Direct3D game or a presentation. """
PROCESS_QUERY_LIMITED_INFORMATION: int = 0x1000
WM_SETTEXT: int = 0x000C
PW_RENDERFULLCONTENT: int = 2
""" Has `PrintWindow` draw what Chromium and Firefox render with the GPU, which it leaves black otherwise. """


# Classes
@dataclass(frozen=True)
class Element:
	""" Something `read_window` listed, which `press` and `fill` act on by its number. """
	control: auto.Control
	app: str
	""" File name of its application's program, in lower case. """
	label: str
	""" Its type, name and value, as listed. """


class RefusedError(Exception):
	""" Why she cannot do what the tool asks, told to the session as the tool's answer. """


class LastInput(ctypes.Structure):
	""" `LASTINPUTINFO`, the time of the user's last key press or mouse move. """
	_fields_ = (("size", wintypes.UINT), ("ticks", wintypes.DWORD))


# Functions
def com[**P](function: Callable[P, str]) -> Callable[P, str]:
	""" Runs the tool on `COM`, and answers why it did nothing when it is RefusedError or its element is gone. """
	@functools.wraps(function)
	def run(*args: P.args, **kwargs: P.kwargs) -> str:
		try:
			return COM.submit(function, *args, **kwargs).result()
		except RefusedError as refusal:
			return str(refusal)
		except COMError as error:
			return tr(f"It failed ({error}): read the window again.", f"Ça a échoué ({error}) : relis la fenêtre.")
	return run


@com
def list_windows() -> str:
	windows = [(window, *access(window.ProcessId)) for window in auto.GetRootControl().GetChildren() if window.Name]
	lines = [f"{window.NativeWindowHandle}: {window.Name} ({app}, {level})" for window, app, level in windows if level]
	return "\n".join(lines) or tr(
		"No window of an application I may use is open.", "Aucune fenêtre d'une application que je peux utiliser n'est ouverte.",
	)


@com
def read_window(window: str) -> str:
	control, app, level = open_window(window)
	if control.ProcessId not in AWAKE:
		AWAKE.add(control.ProcessId)
		listing(control, app, level)
		time.sleep(WAKE_S)
	return listing(control, app, level)


@com
def look_window(window: str) -> str:
	control, _app, _level = open_window(window)
	hwnd = control.NativeWindowHandle
	if windll.user32.IsIconic(hwnd):
		raise RefusedError(tr("The window is minimized, so it draws nothing.", "La fenêtre est réduite, elle ne dessine rien."))
	draw(hwnd)
	return tr(
		f"Drawn in {CAPTURE}: read that file to see the window.", f"Dessinée dans {CAPTURE} : lis ce fichier pour voir la fenêtre.",
	)


@com
def press(element: str) -> str:
	found = usable(element)
	done = tr(f"Pressed {found.label}.", f"J'ai appuyé sur {found.label}.")
	if found.control.FrameworkId == "Gecko":
		found.control.GetLegacyIAccessiblePattern().DoDefaultAction()
		return done
	return in_front(lambda: press_now(found.control), done)


@com
def fill(element: str, text: str) -> str:
	found = usable(element)
	done = tr(f"Wrote into {found.label}.", f"J'ai écrit dans {found.label}.")
	hwnd = found.control.NativeWindowHandle
	if hwnd and (found.control.ClassName == "Edit" or found.control.ClassName.startswith("RichEdit")):
		windll.user32.SendMessageW(hwnd, WM_SETTEXT, 0, text)
		return done
	value = found.control.GetPattern(auto.PatternId.ValuePattern)
	if not isinstance(value, auto.ValuePattern):
		raise RefusedError(tr(f"{found.label} takes no text.", f"{found.label} ne prend pas de texte."))
	return in_front(lambda: value.SetValue(text), done)


def permission(tool: str, tool_input: dict[str, object]) -> str | None:
	""" Why the session must ask the user before this tool call: her first action in an application since the app started. """
	found = ELEMENTS.get(str(tool_input.get("element"))) if tool in ACTING_TOOLS else None
	if not found or found.app in APPROVED:
		return None
	return f"First time Claude-tan acts in {found.app} since ClaudeTan started: {found.label}"


def access(pid: int) -> tuple[str, str]:
	""" The file name of the process's program in lower case, and what she may do in it: "read", "act", or "" for nothing. """
	app = executable(pid)
	return app, "" if pid == os.getpid() or app in NEVER else Config.load().apps.get(app, "")


def executable(pid: int) -> str:
	process = windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid)
	path = ctypes.create_unicode_buffer(1024)
	windll.kernel32.QueryFullProcessImageNameW(process, 0, path, ctypes.byref(wintypes.DWORD(len(path))))
	windll.kernel32.CloseHandle(process)
	return Path(path.value).name.lower()


def open_window(window: str) -> tuple[auto.Control, str, str]:
	""" The window `list_windows` gave this id, its application and what she may do in it. """
	control = auto.ControlFromHandle(int(window)) if window.isdigit() else None
	if not control:
		raise RefusedError(tr("No window has this id: list them again.", "Aucune fenêtre n'a cet id : liste-les à nouveau."))
	app, level = access(control.ProcessId)
	if not level:
		raise RefusedError(tr(f"The user did not open {app} to me.", f"L'utilisateur ne m'a pas ouvert {app}."))
	return control, app, level


def listing(control: auto.Control, app: str, level: str) -> str:
	""" The window's title and its elements, numbered for `press` and `fill`. """
	ELEMENTS.clear()
	lines = [f"{control.Name} ({app}, {level})"]
	for element, _depth in auto.WalkControl(control):
		if len(ELEMENTS) == MAX_LINES:
			lines.append(tr("And more, not listed.", "Et d'autres, non listés."))
			break
		if (label := describe(element)) and not element.IsOffscreen:
			number = str(len(ELEMENTS) + 1)
			ELEMENTS[number] = Element(element, app, label)
			lines.append(f"[{number}] {label}")
	return "\n".join(lines)


def describe(control: auto.Control) -> str:
	""" Its type, name and value as listed, empty for a container with nothing to say. """
	kind = control.ControlTypeName.removesuffix("Control")
	name = control.Name.strip()[:MAX_TEXT]
	value = control.GetPattern(auto.PatternId.ValuePattern) if kind in ("Edit", "ComboBox") else None
	text = value.Value[:MAX_TEXT] if isinstance(value, auto.ValuePattern) else ""
	if not (name or text or kind in LISTED_TYPES):
		return ""
	return f'{kind} "{name}"' + (f' = "{text}"' if text else "")


def draw(hwnd: int) -> None:
	""" Draws the window into `CAPTURE`, even behind other windows. """
	rect = wintypes.RECT()
	windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
	screen = windll.user32.GetDC(0)
	memory = windll.gdi32.CreateCompatibleDC(screen)
	bitmap = windll.gdi32.CreateCompatibleBitmap(screen, rect.right - rect.left, rect.bottom - rect.top)
	windll.gdi32.SelectObject(memory, bitmap)
	windll.user32.PrintWindow(hwnd, memory, PW_RENDERFULLCONTENT)
	QImage.fromHBITMAP(bitmap).save(str(CAPTURE))
	windll.gdi32.DeleteObject(bitmap)
	windll.gdi32.DeleteDC(memory)
	windll.user32.ReleaseDC(0, screen)


def usable(element: str) -> Element:
	""" The element `read_window` listed under this number, once the user lets her act in its application. """
	found = ELEMENTS.get(element)
	if not found:
		raise RefusedError(tr("No element has this number: read the window again.", "Aucun élément n'a ce numéro, relis la fenêtre."))
	if found.app in NEVER or Config.load().apps.get(found.app) != "act":
		raise RefusedError(tr(f"The user lets me only read {found.app}.", f"L'utilisateur me laisse seulement lire {found.app}."))
	APPROVED.add(found.app)
	return found


def in_front(act: Callable[[], object], done: str) -> str:
	""" Does what brings a window to the front, then gives the user their window back.

	It waits until they leave keyboard and mouse alone, with nothing full screen, in an application of the config, never a game.
	"""
	deadline = time.monotonic() + QUIET_WAIT_S
	while idle_s() < QUIET_S or full_screen() or not access(foreground_pid())[1]:
		if time.monotonic() > deadline:
			return tr(
				"Not done, so as not to disturb the user: they kept using the keyboard or mouse, "
				"or were in a full screen application or one the config does not list, such as a game.",
				"Pas fait, pour ne pas déranger l'utilisateur : il utilisait le clavier ou la souris, "
				"ou était dans une application en plein écran ou absente de la config, comme un jeu.",
			)
		time.sleep(0.2)

	previous = windll.user32.GetForegroundWindow()
	act()
	if windll.user32.GetForegroundWindow() != previous and (window := auto.ControlFromHandle(previous)):
		window.SetFocus()
	return done


def press_now(control: auto.Control) -> None:
	""" Presses the element through the first pattern it has of those a click would use, a gone element having none. """
	if isinstance(invoke := control.GetPattern(auto.PatternId.InvokePattern), auto.InvokePattern):
		invoke.Invoke()
	elif isinstance(toggle := control.GetPattern(auto.PatternId.TogglePattern), auto.TogglePattern):
		toggle.Toggle()
	elif isinstance(item := control.GetPattern(auto.PatternId.SelectionItemPattern), auto.SelectionItemPattern):
		item.Select()
	elif isinstance(expand := control.GetPattern(auto.PatternId.ExpandCollapsePattern), auto.ExpandCollapsePattern):
		expand.Collapse() if expand.ExpandCollapseState == auto.ExpandCollapseState.Expanded else expand.Expand()
	elif legacy := control.GetLegacyIAccessiblePattern():
		legacy.DoDefaultAction()
	else:
		raise RefusedError(tr("This element is gone: read the window again.", "Cet élément n'existe plus, relis la fenêtre."))


def idle_s() -> float:
	""" Seconds since the user last pressed a key or moved the mouse. """
	last = LastInput(ctypes.sizeof(LastInput))
	windll.user32.GetLastInputInfo(ctypes.byref(last))
	return (windll.kernel32.GetTickCount() - last.ticks) % 2**32 / 1000


def foreground_pid() -> int:
	pid = wintypes.DWORD()
	windll.user32.GetWindowThreadProcessId(windll.user32.GetForegroundWindow(), ctypes.byref(pid))
	return pid.value


def full_screen() -> bool:
	state = ctypes.c_int()
	windll.shell32.SHQueryUserNotificationState(ctypes.byref(state))
	return state.value in FULL_SCREEN_STATES

