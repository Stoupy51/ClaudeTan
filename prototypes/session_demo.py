""" Session spike: a hidden `claude --remote-control` in a pseudo terminal, driven by typed prompts and followed through HTTP hooks.

Type a prompt and press Enter to send it, as the voice pipeline will. Open the printed URL on your phone to watch the same session.
Run with `uv run prototypes/session_demo.py`, quit with Ctrl+C.
"""
# Imports
import json
import os
import re
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, override

from winpty import PtyProcess

# Constants
SESSION_NAME: str = "Claude Assist"
HOOK_EVENTS: tuple[str, ...] = (
	"UserPromptSubmit", "PreToolUse", "PostToolUse", "Notification", "PermissionRequest", "MessageDisplay", "Stop", "StopFailure",
)
SESSION_URL: re.Pattern[str] = re.compile(r"https://claude\.ai/code/session_\w+")
NESTED_SESSION_VARS: tuple[str, ...] = (
	"CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_CHILD_SESSION",
	"CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_MESSAGING_TOKEN", "CLAUDE_PID",
)
""" Set when this runs inside another Claude Code session; the hosted `claude` refuses to start nested while they are present. """
PASTE_DELAY_S: float = 0.4
""" Pause between the text and Enter, so the TUI takes the text as one paste before submitting it. """


# Classes
class HookHandler(BaseHTTPRequestHandler):
	def do_POST(self) -> None:
		event: dict[str, Any] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
		print(describe(event), flush=True)
		self.send_response(200)
		self.send_header("Content-Type", "application/json")
		self.end_headers()
		self.wfile.write(b"{}")

	@override
	def log_message(self, format: str, *args: Any) -> None:
		pass


class Session:
	def __init__(self, cwd: Path) -> None:
		server = ThreadingHTTPServer(("127.0.0.1", 0), HookHandler)
		threading.Thread(target=server.serve_forever, daemon=True).start()
		url = f"http://127.0.0.1:{server.server_port}"
		hooks = {name: [{"hooks": [{"type": "http", "url": f"{url}/{name}", "timeout": 5}]}] for name in HOOK_EVENTS}
		settings = Path(tempfile.gettempdir()) / "claude_assist_hooks.json"
		settings.write_text(json.dumps({"hooks": hooks}), encoding="utf-8")

		env = {k: v for k, v in os.environ.items() if k not in NESTED_SESSION_VARS}
		# chcp 65001: without it the pseudo console feeds Claude Code accented letters in cp850
		claude = ["claude", "--remote-control", SESSION_NAME, "--settings", str(settings)]
		argv = ["cmd.exe", "/c", "chcp", "65001", ">nul", "&&", *claude]
		self.pty = PtyProcess.spawn(argv, cwd=str(cwd), env=env, dimensions=(50, 200))
		self.url = ""
		self.output = ""
		threading.Thread(target=self.read_output, daemon=True).start()

	def read_output(self) -> None:
		trusted = False
		while self.pty.isalive():
			try:
				self.output = (self.output + self.pty.read(4096))[-50_000:]
			except EOFError:
				return
			if not trusted and "trust" in self.output.lower():
				trusted = True
				self.pty.write("\r")
			if not self.url and (match := SESSION_URL.search(self.output)):
				self.url = match.group()

	def send(self, prompt: str) -> None:
		self.pty.write(prompt)
		time.sleep(PASTE_DELAY_S)
		self.pty.write("\r")

	def close(self) -> None:
		self.send("/exit")
		time.sleep(2)
		if self.pty.isalive():
			self.pty.terminate(force=True)


# Functions
def describe(event: dict[str, Any]) -> str:
	name: str = event["hook_event_name"]
	match name:
		case "UserPromptSubmit":
			return f"[thinking]   prompt received: {event['prompt']}"
		case "PreToolUse":
			return f"[working]    {event['tool_name']} {json.dumps(event['tool_input'], ensure_ascii=False)[:120]}"
		case "PermissionRequest" | "Notification":
			return f"[asking]     {event.get('message') or event.get('tool_name')}"
		case "MessageDisplay":
			return f"[talking]    {event['delta'].strip()[:200]}"
		case "Stop":
			return f"[done]       {event['last_assistant_message'][:200]}"
		case _:
			return f"[{name}]"


def main() -> None:
	session = Session(Path.cwd())
	deadline = time.monotonic() + 60
	while not session.url and time.monotonic() < deadline:
		time.sleep(0.25)
	print(f"Remote Control: {session.url or 'URL not found, is claude logged in with a subscription?'}", flush=True)
	try:
		for line in sys.stdin:
			if line.strip():
				session.send(line.strip())
	except KeyboardInterrupt:
		pass
	session.close()


if __name__ == "__main__":
	main()

