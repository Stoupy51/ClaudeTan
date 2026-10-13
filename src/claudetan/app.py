""" ClaudeTan: Claude-tan reacting to what she hears and to the hidden Claude Code session, through its hook events. """
# Imports
import logging
import re
import signal
import subprocess
import sys
import threading
import tomllib
from collections import deque
from collections.abc import Mapping
from concurrent.futures import Future
from dataclasses import fields
from functools import partial
from pathlib import Path
from urllib.parse import urlparse

import stouputils as stp
from PySide6.QtCore import QFileSystemWatcher, QObject, QPoint, QTimer, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from claudetan.actions import Action, chosen_model, route
from claudetan.config import APP_DATA, LOG_FILE, USER_CONFIG, Config
from claudetan.console import enable_colors
from claudetan.mcp import ActionServer
from claudetan.overlay.avatar import Avatar, Pill, chime
from claudetan.overlay.bubble import plain
from claudetan.overlay.tray import Tray
from claudetan.session import HookServer, JsonDict, Session
from claudetan.voice.audio import microphone
from claudetan.voice.listener import FOLLOW_UP_S, Listener

# Constants
LOG: logging.Logger = logging.getLogger("claudetan")
""" The app's own log, kept at INFO while the libraries stay at WARNING. """
WAKE_NOTES: tuple[float, ...] = (880.0, 1318.5)
DONE_NOTES: tuple[float, ...] = (1046.5, 1318.5, 1568.0)
LONG_TASK_MS: int = 20_000
""" How long a turn runs before she shrinks to the pill. """
HEARD_MS: int = 4000
""" How long the sentence she understood stays up when the session does not start on it right away. """
CONFIG_NOTICE_MS: int = 6000
""" How long she stays up to say what she applied from the saved config. """
STARTUP_S: float = 60.0
""" How long the session and Whisper may take to start before the app reports them as failed. """
COMPACT_IDLE_MS: int = 55 * 60_000
""" Quiet time after which a large session is compacted, while its prompt cache (1 h on a subscription) still makes that cheap. """
COMPACT_TIMEOUT_MS: int = 180_000
""" How long quitting waits for the session's compaction. """
INSTANCE_NAME: str = "ClaudeTan"
""" Local server of the running app: a new one connects to it to have it quit. """
SESSION_KEYS: frozenset[str] = frozenset({"agent_model", "prompt"})
""" Settings Claude Code reads only when it starts, applied by restarting the session on the same conversation. """
READY: str = "ready\n"
""" Last line the background app writes to `main`, which returns on it: the venv's launcher keeps the pipe open after it. """


# Classes
class Assistant(QObject):
	""" What Claude-tan shows at each step of a request, and when the next command may be typed into the session. """
	send = Signal(str)
	""" A command to type, emitted only between turns: keys typed while a dialog is open would answer it. """
	idle = Signal()
	""" No hook for `COMPACT_IDLE_MS` and no turn running. """
	restart = Signal()
	""" The session starts again: `SESSION_KEYS` settings changed while she was free, or she was told to stop everything. """

	def __init__(self, avatar: Avatar, pill: Pill, config: Config) -> None:
		super().__init__()
		self.config = config
		self.avatar = avatar
		self.pill = pill
		self.commands: deque[str] = deque()
		self.busy = False
		self.agents: set[str] = set()
		self.asking = False
		self.worked = False
		""" Whether the turn used a tool, which makes her present the result rather than smile. """
		self.restart_pending = False
		self.activity = ""
		self.message_id = ""
		self.message = ""

		self.long_task = QTimer(self)
		self.long_task.setSingleShot(True)
		self.long_task.setInterval(LONG_TASK_MS)
		self.long_task.timeout.connect(self.shrink)
		self.dismiss = QTimer(self)
		self.dismiss.setSingleShot(True)
		self.dismiss.timeout.connect(self.leave)
		self.idle_timer = QTimer(self)
		self.idle_timer.setSingleShot(True)
		self.idle_timer.setInterval(COMPACT_IDLE_MS)
		self.idle_timer.timeout.connect(self.on_idle)

	def on_wake(self) -> None:
		chime(*WAKE_NOTES)
		self.appear("hello", bubble="Oui ?")
		self.dismiss.start(round(FOLLOW_UP_S * 1000))

	def on_dictation(self, text: str) -> None:
		self.appear("idle", bubble=f"« {text} » Dis « {self.config.done_hint} » pour envoyer.")
		self.dismiss.stop()

	def on_cancel(self) -> None:
		LOG.info("Request cancelled")
		self.appear("idle", bubble="D'accord, j'oublie.")
		self.dismiss.start(HEARD_MS)

	def on_config(self, config: Config, changed: list[str]) -> None:
		LOG.info("Config changed: %s", ", ".join(changed))
		self.config = config
		if "avatar_zoom" in changed or "text_zoom" in changed:
			self.avatar.set_zoom(config.avatar_zoom, config.text_zoom)
			self.pill.set_zoom(config.avatar_zoom)
		if "model" in changed:
			self.switch_model(config.model)
		self.restart_pending = self.restart_pending or not SESSION_KEYS.isdisjoint(changed)
		later = " Je relance la session Claude pour l'appliquer dès que je n'ai plus rien en cours." if self.restart_pending else ""
		self.appear("happy", bubble=f"J'ai relu ta config : {', '.join(changed)}.{later}")
		self.dismiss.start(CONFIG_NOTICE_MS)

	def on_config_error(self, error: str) -> None:
		LOG.warning("Config not applied: %s", error)
		self.appear("sad", bubble=f"Je n'arrive pas à lire ta config, je garde l'ancienne : {error}")
		self.dismiss.start(CONFIG_NOTICE_MS)

	def on_command(self, text: str) -> None:
		LOG.info("Heard: %s", text)
		if routed := route(text):
			action, arguments = routed
			LOG.info("Local action: %s", action.name)
			self.appear("present", bubble=self.run_action(action, arguments))
			self.dismiss.start(HEARD_MS)
			return

		self.appear("idle", bubble=f"« {text} »" + (" Je m'en occupe juste après." if self.busy else ""))
		self.dismiss.start(HEARD_MS)
		self.commands.append(text)
		self.flush()

	def run_action(self, action: Action, arguments: Mapping[str, str | None]) -> str:
		""" Carries the action out, whoever asked, and returns what it says about it. """
		text = action.run(arguments)
		match action.name:
			case "stop_all":
				self.stop_all()
			case "model" if model := chosen_model(arguments):
				self.switch_model(model)
			case _:
				pass
		return text

	def switch_model(self, model: str) -> None:
		self.commands.append(f"/model {model}")
		self.flush()

	def on_tool_call(self, action: Action, arguments: dict[str, str], text: Future[str]) -> None:
		""" The session called the action as a tool: she does it without interrupting what she shows. """
		LOG.info("Tool called: %s", action.name)
		text.set_result(self.run_action(action, arguments))

	def stop_all(self) -> None:
		""" Drops the queued commands and what the session runs, its agents included, by starting it again. """
		self.commands.clear()
		self.agents.clear()
		self.end_turn()
		self.restart_pending = False
		self.restart.emit()

	def on_hook(self, event: JsonDict) -> None:
		self.idle_timer.start()
		match event["hook_event_name"]:
			case "UserPromptSubmit":
				self.on_prompt(event["prompt"])
			case "PreToolUse":
				self.on_tool(describe_tool(event["tool_name"], event["tool_input"]))
			case "PostToolUse" if self.asking:
				self.settle_permission()
				self.appear("thanks", bubble="Merci !")
			case "PermissionRequest":
				self.on_permission(describe_tool(event["tool_name"], event["tool_input"]))
			case "Notification" if event["notification_type"] == "permission_prompt":
				self.on_permission(event["message"])
			case "MessageDisplay":
				self.on_text(event["message_id"], event["delta"], streaming=not event["final"])
			case "SubagentStart":
				self.agents.add(event["agent_id"])
				self.shrink()
			case "SubagentStop":
				self.agents.discard(event["agent_id"])
			case "Stop":
				self.on_stop(event["last_assistant_message"])
			case "StopFailure":
				self.on_failure(event["error"])
			# Claude Code compacts on its own during a turn, which stays busy
			case "PreCompact" if event["trigger"] != "auto":
				self.busy = True
			case "PostCompact" if event["trigger"] != "auto":
				self.busy = False
				self.flush()
			case _:
				pass

	def on_prompt(self, prompt: str) -> None:
		""" A turn starts, typed by the app, sent from the Remote Control, or started by Claude Code itself. """
		LOG.info("Prompt: %s", prompt)
		self.busy = True
		self.worked = False
		self.activity = ""
		self.dismiss.stop()
		self.long_task.start()
		if not self.pill.isVisible():
			self.appear("thinking", bubble=prompt)

	def on_tool(self, activity: str) -> None:
		LOG.info("Action: %s", activity)
		self.worked = True
		self.settle_permission()
		if activity != self.activity and not self.pill.isVisible():
			self.activity = activity
			self.appear("working", bubble=activity)

	def on_permission(self, request: str) -> None:
		if self.asking:
			return
		LOG.info("Permission asked: %s", request)
		self.asking = True
		self.long_task.stop()
		self.appear("please", bubble=f"J'ai besoin de ton accord : {request}. Clique sur moi pour répondre.")

	def settle_permission(self) -> None:
		""" Closes a pending permission prompt, allowed or not, and restarts the countdown to the pill. """
		if self.asking:
			self.asking = False
			self.long_task.start()

	def on_text(self, message_id: str, delta: str, *, streaming: bool) -> None:
		self.message = self.message + delta if message_id == self.message_id else delta
		self.message_id = message_id
		if not self.pill.isVisible():
			self.appear("idle", bubble=self.message, talking=streaming)

	def on_stop(self, reply: str) -> None:
		LOG.info("Reply: %s", reply)
		self.end_turn()
		if not self.agents:
			chime(*DONE_NOTES)
		self.appear("present" if self.worked else "happy", bubble=reply)
		self.dismiss.start(reading_ms(reply))
		self.flush()

	def on_failure(self, error: str) -> None:
		LOG.warning("Request failed: %s", error)
		self.end_turn()
		self.appear("sad", bubble=f"Oups, la requête a échoué ({error}).")
		self.dismiss.start(reading_ms(error))
		self.flush()

	def end_turn(self) -> None:
		self.busy = False
		self.asking = False
		self.long_task.stop()

	def flush(self) -> None:
		if self.commands and not self.busy:
			self.send.emit(self.commands.popleft())

	def appear(self, expression: str, bubble: str, *, talking: bool = False) -> None:
		self.pill.hide()
		self.avatar.set_expression(expression, talking=talking, bubble=bubble)
		self.avatar.pop_in()

	def shrink(self) -> None:
		self.avatar.pop_out()
		self.pill.show_at(self.avatar.home() + QPoint(self.avatar.width(), self.avatar.height()))

	def leave(self) -> None:
		""" Out of the way once nothing needs her: the pill while work goes on, hidden otherwise. """
		if self.busy or self.agents:
			self.shrink()
			return
		self.pill.hide()
		self.avatar.pop_out()
		if self.restart_pending:
			self.restart_pending = False
			self.restart.emit()

	def on_idle(self) -> None:
		if not self.busy:
			self.idle.emit()


# Functions
def describe_tool(name: str, tool_input: JsonDict) -> str:
	""" What a tool call does, in a few words for the bubble.

	>>> describe_tool("Edit", {"file_path": "D:/repo/claudetan/app.py", "old_string": "a", "new_string": "b"})
	'modifie app.py'
	>>> describe_tool("Bash", {"command": "git status", "description": "Show working tree status"})
	'Show working tree status'
	>>> describe_tool("mcp__claudetan__screenshot", {"screen": 2})
	'screenshot'
	"""
	match name:
		case "Read":
			return f"lit {Path(tool_input['file_path']).name}"
		case "Write":
			return f"écrit {Path(tool_input['file_path']).name}"
		case "Edit" | "MultiEdit":
			return f"modifie {Path(tool_input['file_path']).name}"
		case "Bash" | "PowerShell":
			return tool_input.get("description") or f"lance {tool_input['command'][:60]}"
		case "Grep" | "Glob":
			return f"cherche {tool_input['pattern']}"
		case "WebSearch":
			return f"cherche « {tool_input['query']} » sur le web"
		case "WebFetch":
			return f"lit {urlparse(str(tool_input['url'])).netloc}"
		case "Agent" | "Task":
			return f"confie une tâche : {tool_input['description']}"
		case "AskUserQuestion":
			return tool_input["questions"][0]["question"]
		case _:
			return name.rsplit("__", 1)[-1]


def reading_ms(text: str) -> int:
	""" How long a text stays up: 4 s, plus 50 ms per character, which the bubble scrolls through at that pace, 60 s at most. """
	return min(4000 + 50 * len(plain(text)), 60_000)


def main() -> None:
	""" Starts the app in the background and returns once it reports it is ready, so no console window stays open. """
	enable_colors()
	stp.progress("Starting ClaudeTan, which takes about 15 s...")
	# A gui-script would not do: uv makes the venv's pythonw.exe a copy of the console python.exe, which opens a window
	app = subprocess.Popen(
		[sys.executable, "-m", "claudetan.app"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
		text=True, creationflags=subprocess.CREATE_NO_WINDOW,
	)
	assert app.stdout
	for line in app.stdout:
		if line == READY:
			stp.info('Say "Hey Claude, ..." to ask her something, and quit her from her tray icon.')
			return
		print(line, end="", flush=True)
	stp.error(f"ClaudeTan stopped while starting, see {stp.CYAN}{LOG_FILE}")


def reload_config(watcher: QFileSystemWatcher, listener: Listener, assistant: Assistant) -> None:
	""" Applies the saved config: the listener reads its settings on each sentence, and `Assistant.on_config` applies the others. """
	# Editors save by replacing the file, which drops it from the watch
	watcher.addPath(str(USER_CONFIG))
	try:
		config = Config.load()
	except (tomllib.TOMLDecodeError, re.error) as error:
		assistant.on_config_error(str(error))
		return

	changed = [field.name for field in fields(Config) if getattr(config, field.name) != getattr(listener.config, field.name)]
	if changed:
		listener.config = config
		assistant.on_config(config, changed)


def report_ready(session: Session, listener: Listener) -> None:
	""" Tells `main`, through stdout, how the session and Whisper started. """
	if session.started.wait(STARTUP_S):
		stp.info(f"Claude Code session {'resumed' if session.id else 'started'}: {stp.CYAN}{session.url}")
		stp.info(f"Plan usage: {session.plan_usage()}")
	else:
		stp.warning("Claude Code did not start Remote Control: run uv run claudetan-setup, then start the app again", file=sys.stdout)
	if listener.loaded.wait(STARTUP_S):
		stp.info("Whisper runs on the GPU")
	else:
		stp.warning("Whisper did not load", file=sys.stdout)
	stp.info(f"Log: {stp.CYAN}{LOG_FILE}")
	print(READY, end="", flush=True)


def shut_down(app: QApplication, tray: Tray, assistant: Assistant, session: Session) -> None:
	""" Quits, after compacting a large session so that the next start does not reread it all once the prompt cache has expired. """
	tray.hide()
	if assistant.busy or not session.compact():
		app.quit()
		return
	session.compacted.connect(app.quit)
	QTimer.singleShot(COMPACT_TIMEOUT_MS, app.quit)


def replace_running_app() -> None:
	""" Has the app already running quit, and waits until it has, so that starting the app again applies new code and settings. """
	running = QLocalSocket()
	running.connectToServer(INSTANCE_NAME)
	if running.waitForConnected(1000):
		stp.progress("Waiting for the running app to quit, after it compacts its session when that is large...")
		running.waitForDisconnected(COMPACT_TIMEOUT_MS + 10_000)


def run() -> None:
	APP_DATA.mkdir(parents=True, exist_ok=True)
	logging.basicConfig(
		filename=LOG_FILE, encoding="utf-8", level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s",
	)
	LOG.setLevel(logging.INFO)
	# Without a console the default hooks print tracebacks nowhere
	sys.excepthook = lambda _kind, exception, _trace: logging.critical("Uncaught error", exc_info=exception)
	threading.excepthook = lambda hook: logging.critical("Uncaught error in %s", hook.thread, exc_info=hook.exc_value)
	# Qt's event loop never hands control back to Python's KeyboardInterrupt, so let Ctrl+C end the process directly
	signal.signal(signal.SIGINT, signal.SIG_DFL)

	app = QApplication(sys.argv)
	app.setQuitOnLastWindowClosed(False)
	replace_running_app()
	instance = QLocalServer()
	instance.listen(INSTANCE_NAME)
	config = Config.load()
	avatar, pill = Avatar(config.avatar_zoom, config.text_zoom), Pill(config.avatar_zoom)
	assistant = Assistant(avatar, pill, config)
	tray = Tray()
	tray.show()
	hooks = HookServer()
	tools = ActionServer()
	session = Session(hooks.url, tools.url, config)
	quit_app = partial(shut_down, app, tray, assistant, session)
	tray.quit_requested.connect(quit_app)
	instance.newConnection.connect(quit_app)
	for clicked in (avatar.clicked, pill.clicked, tray.open_session):
		clicked.connect(session.open)
	hooks.posted.connect(session.on_hook)
	hooks.posted.connect(assistant.on_hook)
	tools.called.connect(assistant.on_tool_call)
	assistant.send.connect(session.send)
	assistant.idle.connect(session.compact)
	app.aboutToQuit.connect(session.close)
	listener = Listener(config)
	listener.woke.connect(assistant.on_wake)
	listener.dictated.connect(assistant.on_dictation)
	listener.cancelled.connect(assistant.on_cancel)
	listener.heard.connect(assistant.on_command)
	assistant.restart.connect(lambda: session.restart(listener.config))
	watcher = QFileSystemWatcher([str(USER_CONFIG)])
	saved = QTimer(singleShot=True, interval=300)
	saved.timeout.connect(partial(reload_config, watcher, listener, assistant))
	watcher.fileChanged.connect(lambda: saved.start())
	threading.Thread(target=listener.run, args=(microphone(),), daemon=True).start()
	report_ready(session, listener)
	sys.exit(app.exec())


if __name__ == "__main__":
	run()

