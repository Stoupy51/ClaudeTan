""" The actions as tools of a local MCP server over HTTP, which the hidden session connects to. """
# Imports
import json
import threading
from concurrent.futures import Future
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, override

from PySide6.QtCore import QObject, Signal, SignalInstance

from claudetan.actions import ACTIONS, Action, find
from claudetan.session import JsonDict

# Constants
CALL_TIMEOUT_S: float = 30.0
""" How long a tool call waits for the Qt thread to run its action. """


# Classes
class ActionServer(QObject):
	""" Answers the session's MCP requests, relaying each tool call to the Qt thread, where actions must run. """
	called = Signal(Action, dict, Future)
	""" An action to run with its arguments, and the future its text is set on. """

	def __init__(self) -> None:
		super().__init__()
		relay = self.called

		class Handler(BaseHTTPRequestHandler):
			def do_POST(self) -> None:
				response = answer(json.loads(self.rfile.read(int(self.headers["Content-Length"]))), relay)
				body = b"" if response is None else json.dumps(response).encode()
				self.send_response(202 if response is None else 200)
				self.send_header("Content-Type", "application/json")
				self.send_header("Content-Length", str(len(body)))
				self.end_headers()
				self.wfile.write(body)

			def do_GET(self) -> None:
				self.send_error(405)

			@override
			def log_message(self, format: str, *args: Any) -> None:
				pass

		server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
		self.url = f"http://127.0.0.1:{server.server_port}"
		threading.Thread(target=server.serve_forever, daemon=True).start()


# Functions
def answer(request: JsonDict, relay: SignalInstance) -> JsonDict | None:
	""" The JSON-RPC response to a request, None for a notification. """
	if "id" not in request:
		return None

	result: JsonDict
	match request["method"]:
		case "initialize":
			result = {
				"protocolVersion": request["params"]["protocolVersion"],
				"capabilities": {"tools": {}},
				"serverInfo": {"name": "claudetan", "version": "1"},
			}
		case "tools/list":
			result = {"tools": [tool(action) for action in ACTIONS]}
		case "tools/call":
			result = call(request["params"], relay)
		case "ping":
			result = {}
		case method:
			return {"jsonrpc": "2.0", "id": request["id"], "error": {"code": -32601, "message": f"Unknown method {method}"}}
	return {"jsonrpc": "2.0", "id": request["id"], "result": result}


def tool(action: Action) -> JsonDict:
	properties = {name: {"type": "string", "description": text} for name, text in action.parameters.items()}
	return {"name": action.name, "description": action.description, "inputSchema": {"type": "object", "properties": properties}}


def call(params: JsonDict, relay: SignalInstance) -> JsonDict:
	action = find(params["name"])
	arguments = {name: str(value) for name, value in params.get("arguments", {}).items()}
	text: Future[str] = Future()
	relay.emit(action, arguments, text)
	try:
		return {"content": [{"type": "text", "text": text.result(CALL_TIMEOUT_S)}]}
	except TimeoutError:
		return {"content": [{"type": "text", "text": f"{action.name} did not answer"}], "isError": True}

