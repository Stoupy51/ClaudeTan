""" How large the session's conversation is, read from its transcript to decide whether a compaction is worth it. """
# Imports
import json
from pathlib import Path

from claudetan.session import context_tokens


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

