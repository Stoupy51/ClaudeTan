""" How large the session's conversation is, read from its transcript to decide whether a compaction is worth it. """
# Imports
import json
import urllib.request
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from PySide6.QtWidgets import QApplication

from claudetan.session import HookServer, context_tokens


# Functions
def test_context_size_is_read_from_the_last_reply_until_a_compaction(tmp_path: Path) -> None:
	usage = {"input_tokens": 2, "cache_read_input_tokens": 120_000, "cache_creation_input_tokens": 3000}
	reply = {"type": "assistant", "message": {"role": "assistant", "usage": usage}}
	transcript = tmp_path / "session.jsonl"
	transcript.write_text("\n".join(json.dumps(entry) for entry in [reply, {"type": "last-prompt"}]), encoding="utf-8")
	assert context_tokens(transcript) == 123_002

	boundary = {"type": "system", "subtype": "compact_boundary"}
	transcript.write_text("\n".join(json.dumps(entry) for entry in [reply, boundary, {"type": "user"}]), encoding="utf-8")
	assert context_tokens(transcript) == 0


def test_a_permission_request_waits_for_the_spoken_answer_and_returns_it(app: QApplication) -> None:
	server = HookServer()
	def answer(verdict: Future[bool]) -> None:
		verdict.set_result(False)
	server.asked.connect(answer)

	def post(event: str) -> bytes:
		body = json.dumps({"hook_event_name": event}).encode()
		with urllib.request.urlopen(urllib.request.Request(server.url, body)) as response:
			return response.read()

	with ThreadPoolExecutor() as pool:
		asked, other = pool.submit(post, "PermissionRequest"), pool.submit(post, "Stop")
		while not (asked.done() and other.done()):
			app.processEvents()

	assert json.loads(asked.result())["hookSpecificOutput"]["decision"]["behavior"] == "deny"
	assert other.result() == b""

