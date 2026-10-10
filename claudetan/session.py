""" The hidden Claude Code session: `claude --remote-control` in a pseudo terminal, and the hook events it posts to the app. """
# Imports
import json
import os
import re
import subprocess
import threading
import time
import uuid
import webbrowser
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, override

import pyte
from PySide6.QtCore import QObject, QTimer, Signal
from winpty import PtyProcess

from claudetan.config import APP_DATA, ROOT, USER_CONFIG

# Constants
type JsonDict = dict[str, Any]
SYSTEM_PROMPT: str = (
	f"You are Claude-tan, the voice assistant of ClaudeTan, an app installed in {ROOT} that keeps its settings in {USER_CONFIG}.\n"
	"ClaudeTan started this Claude Code session hidden in a pseudo-terminal, with Remote Control and the auto permission mode, "
	"resumes it each time the app starts, and follows it through hooks to animate your avatar on the screen.\n"
	"Prompts come from the user's voice, transcribed by Whisper, which can mishear words, "
	"or from the Remote Control on claude.ai or in the Claude app on their iPhone.\n"
	"Your replies appear in a speech bubble next to your avatar, which only shows the start of long ones.\n"
)
""" What the app tells the session about itself, before the user's additions from the config. """
HOOK_EVENTS: tuple[str, ...] = (
	"UserPromptSubmit", "PreToolUse", "PostToolUse", "PermissionRequest", "Notification", "MessageDisplay",
	"SubagentStart", "SubagentStop", "Stop", "StopFailure",
)
SESSION_ID: Path = APP_DATA / "session_id"
""" The conversation the app resumes, saved once a hook reports it, so a session that never got a prompt is not resumed. """
SESSION_URL: re.Pattern[str] = re.compile(r"https://claude\.ai/code/session_\w+")
PLAN_USAGE: re.Pattern[str] = re.compile(
	r"Current session\W+(?P<window>\d+)% used\s+Resets (?P<window_reset>[^)]*\)).*?"
	r"Current week \(all models\)\W+(?P<week>\d+)% used\s+Resets (?P<week_reset>[^)]*\))",
	re.DOTALL,
)
""" The two limits of the `/usage` panel, each followed by when it resets, such as "Resets Oct 12, 12am (Europe/Paris)". """
NESTED_SESSION_VARS: tuple[str, ...] = (
	"CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_CHILD_SESSION",
	"CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_MESSAGING_TOKEN", "CLAUDE_PID",
)
""" Set when the app runs inside another Claude Code session; the hosted `claude` refuses to start nested while they are present. """
PASTE_DELAY_MS: int = 400
""" Pause between the text and Enter, so the TUI takes the text as one paste before submitting it. """


# Classes
class HookServer(QObject):
	""" Local endpoint for the session's `type: "http"` hooks, relaying each payload to the Qt thread. """
	posted = Signal(dict)

	def __init__(self) -> None:
		super().__init__()
		relay = self.posted

		class Handler(BaseHTTPRequestHandler):
			def do_POST(self) -> None:
				relay.emit(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
				self.send_response(200)
				self.end_headers()

			@override
			def log_message(self, format: str, *args: Any) -> None:
				pass

		server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
		self.url = f"http://127.0.0.1:{server.server_port}"
		threading.Thread(target=server.serve_forever, daemon=True).start()


class Session:
	""" Claude Code started in the repo, resuming the saved conversation, with its hooks posting to `hooks_url`. """

	def __init__(self, hooks_url: str, additions: str) -> None:
		settings = APP_DATA / "session_settings.json"
		hooks = {name: [{"hooks": [{"type": "http", "url": hooks_url, "timeout": 5}]}] for name in HOOK_EVENTS}
		settings.write_text(json.dumps({"hooks": hooks}), encoding="utf-8")
		prompt = APP_DATA / "session_prompt.md"
		prompt.write_text(system_prompt(additions), encoding="utf-8")

		self.id = SESSION_ID.read_text() if SESSION_ID.exists() else ""
		resume = ["--resume", self.id] if self.id else ["--session-id", str(uuid.uuid4())]
		claude = [
			"claude", "--remote-control", "ClaudeTan", "--permission-mode", "auto",
			"--settings", str(settings), "--append-system-prompt-file", str(prompt), *resume,
		]
		# chcp 65001: without it the pseudo console feeds Claude Code accented letters in cp850
		argv = ["cmd.exe", "/c", "chcp", "65001", ">nul", "&&", *claude]
		env = {name: value for name, value in os.environ.items() if name not in NESTED_SESSION_VARS}
		self.pty = PtyProcess.spawn(argv, cwd=str(ROOT), env=env, dimensions=(50, 200))
		self.screen = pyte.Screen(200, 50)
		""" What the terminal shows, rebuilt from its output: Claude Code only redraws the characters that change. """
		self.screen_lock = threading.Lock()
		self.url = "https://claude.ai/code"
		self.started = threading.Event()
		""" Set once Remote Control prints the session's URL, when the session is ready for prompts. """
		threading.Thread(target=self.read_output, daemon=True).start()

	def read_output(self) -> None:
		""" Renders the terminal's output, read continuously so the session never blocks on a full pipe. """
		stream = pyte.Stream(self.screen)
		while self.pty.isalive():
			try:
				output = self.pty.read(4096)
			except EOFError:
				return
			with self.screen_lock:
				stream.feed(output)
			if not self.started.is_set() and (match := SESSION_URL.search(self.text())):
				self.url = match.group()
				self.started.set()

	def plan_usage(self) -> str:
		""" The plan's limits as `/usage` shows them, read before any prompt since keys typed while its panel is open land in it. """
		self.pty.write("/usage")
		time.sleep(PASTE_DELAY_MS / 1000)
		self.pty.write("\r")
		deadline = time.monotonic() + 15
		while not (match := PLAN_USAGE.search(self.text())) and time.monotonic() < deadline:
			time.sleep(0.2)
		self.pty.write("\x1b")
		if not match:
			return "unknown, /usage did not show it"
		return (
			f"{match['window']}% of the 5-hour window, resets {match['window_reset']}; "
			f"{match['week']}% of the week, resets {match['week_reset']}"
		)

	def text(self) -> str:
		with self.screen_lock:
			return "\n".join(self.screen.display)

	def on_hook(self, event: JsonDict) -> None:
		if event["session_id"] != self.id:
			self.id = event["session_id"]
			SESSION_ID.write_text(self.id)

	def send(self, prompt: str) -> None:
		self.pty.write(prompt)
		QTimer.singleShot(PASTE_DELAY_MS, partial(self.pty.write, "\r"))

	def open(self) -> None:
		webbrowser.open(self.url)

	def close(self) -> None:
		""" Kills Claude Code outright: on a clean exit, Remote Control archives the session, which drops it from claude.ai's list. """
		kill = ["taskkill", "/F", "/T", "/PID", str(self.pty.pid)]
		subprocess.run(kill, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)


# Functions
def system_prompt(additions: str) -> str:
	""" Text for `--append-system-prompt-file`: `SYSTEM_PROMPT`, then the user's additions when there are any.

	>>> system_prompt("\\n") == SYSTEM_PROMPT
	True
	>>> system_prompt("Mes jeux sont dans E:/Games.\\n").removeprefix(SYSTEM_PROMPT)
	'\\nMes jeux sont dans E:/Games.'
	"""
	return f"{SYSTEM_PROMPT}\n{additions.strip()}" if additions.strip() else SYSTEM_PROMPT

