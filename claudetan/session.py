""" The hidden Claude Code session: what it is told about itself, and the hook events it posts to the app. """
# Imports
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, override

from PySide6.QtCore import QObject, Signal

from claudetan.config import ROOT, USER_CONFIG

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


# Functions
def system_prompt(additions: str) -> str:
	""" Text for `--append-system-prompt`: `SYSTEM_PROMPT`, then the user's additions when there are any.

	>>> system_prompt("\\n") == SYSTEM_PROMPT
	True
	>>> system_prompt("Mes jeux sont dans E:/Games.\\n").removeprefix(SYSTEM_PROMPT)
	'\\nMes jeux sont dans E:/Games.'
	"""
	return f"{SYSTEM_PROMPT}\n{additions.strip()}" if additions.strip() else SYSTEM_PROMPT

