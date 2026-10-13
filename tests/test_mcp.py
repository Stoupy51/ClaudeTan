""" The actions offered to the session as MCP tools. """
# Imports
import json
import urllib.request
from concurrent.futures import Future, ThreadPoolExecutor

from PySide6.QtWidgets import QApplication

from claudetan.actions import ACTIONS, Action
from claudetan.mcp import ActionServer
from claudetan.session import JsonDict


# Functions
def post(server: ActionServer, method: str, params: dict[str, object]) -> JsonDict:
	body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
	with urllib.request.urlopen(urllib.request.Request(server.url, body, {"Content-Type": "application/json"})) as response:
		return json.load(response)["result"]


def test_every_action_is_a_tool_and_a_call_runs_it_with_its_arguments(app: QApplication) -> None:
	server = ActionServer()
	def run(action: Action, arguments: dict[str, str], text: Future[str]) -> None:
		text.set_result(f"{action.name} {arguments}")
	server.called.connect(run)

	with ThreadPoolExecutor() as pool:
		listed = pool.submit(post, server, "tools/list", {})
		called = pool.submit(post, server, "tools/call", {"name": "screenshot", "arguments": {"screen": 2}})
		while not (listed.done() and called.done()):
			app.processEvents()

	assert [tool["name"] for tool in listed.result()["tools"]] == [action.name for action in ACTIONS]
	result = called.result()
	assert result["content"] == [{"type": "text", "text": "screenshot {'screen': '2'}"}]

