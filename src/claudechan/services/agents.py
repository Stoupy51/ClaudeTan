""" What the session's tool calls and its background agents do, the agents read from the transcripts Claude Code keeps. """
# Imports
import json
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from stouputils.typing import JsonDict

from claudechan.i18n import tr
from claudechan.services import desktop
from claudechan.session import SESSION_ID

# Constants
PROJECTS: Path = Path.home() / ".claude" / "projects"
""" Where Claude Code keeps the transcripts of every session, under a folder per project. """
RECENT_S: int = 6 * 3600
""" The agents that did nothing for longer than this are left out. """
ACTIVE_S: int = 180
""" An agent that did nothing for this long is not running any more, or stuck. """
MAX_AGENTS: int = 3
HANDBACK: str = "SubagentHandback"
""" The tool an agent ends with, to hand its report back. """


# Functions
def progress() -> str:
	""" Where the background agents of the session stand: what each is, how long it runs, how many tool calls it made and the last. """
	folders = PROJECTS.glob(f"*/{SESSION_ID.read_text()}/subagents")
	now = time.time()
	transcripts = sorted(
		(path for folder in folders for path in folder.glob("agent-*.jsonl") if now - path.stat().st_mtime < RECENT_S),
		key=lambda path: path.stat().st_mtime, reverse=True,
	)[:MAX_AGENTS]
	if not transcripts:
		return tr("No agent worked on this session lately.", "Aucun agent n'a travaillé récemment sur cette session.")
	return "\n".join(describe_agent(path, now) for path in transcripts)


def describe_agent(transcript: Path, now: float) -> str:
	""" One line about an agent: its task, running or finished, its age, its tool calls and what it did last. """
	meta: JsonDict = json.loads(transcript.with_suffix(".meta.json").read_text(encoding="utf-8"))
	rows: list[JsonDict] = [json.loads(line) for line in transcript.read_text(encoding="utf-8").splitlines()]
	answers = [row["message"] for row in rows if row["type"] == "assistant"]
	calls = [block for answer in answers for block in answer["content"] if block["type"] == "tool_use"]
	finished = answers[-1].get("stop_reason") == "end_turn" or (bool(calls) and calls[-1]["name"] == HANDBACK)
	idle_s = now - transcript.stat().st_mtime
	started = datetime.fromisoformat(next(row["timestamp"] for row in rows if "timestamp" in row))
	age_min = round((now - started.timestamp()) / 60)
	silent = tr("silent for ", "silencieux depuis ") + f"{round(idle_s / 60)} min"
	state = tr("finished", "terminé") if finished else tr("running", "en cours") if idle_s < ACTIVE_S else silent
	last = describe_tool(calls[-1]["name"], calls[-1]["input"]) if calls else "-"
	return tr(
		f"{meta['description']}: {state}, {age_min} min, {len(calls)} tool calls, last: {last}.",
		f"{meta['description']} : {state}, {age_min} min, {len(calls)} appels d'outils, dernier : {last}.",
	)


def describe_tool(name: str, tool_input: JsonDict) -> str:
	""" What a tool call does, in a few words for the bubble.

	>>> describe_tool("Edit", {"file_path": "D:/repo/claudechan/app.py", "old_string": "a", "new_string": "b"})
	'edits app.py'
	>>> describe_tool("Bash", {"command": "git status", "description": "Show working tree status"})
	'Show working tree status'
	>>> describe_tool("mcp__claudechan__screenshot", {"screen": 2})
	'screenshot'
	"""
	match name:
		case "Read":
			return tr("reads ", "lit ") + Path(tool_input["file_path"]).name
		case "Write":
			return tr("writes ", "écrit ") + Path(tool_input["file_path"]).name
		case "Edit" | "MultiEdit":
			return tr("edits ", "modifie ") + Path(tool_input["file_path"]).name
		case "Bash" | "PowerShell":
			return tool_input.get("description") or tr("runs ", "lance ") + tool_input["command"][:60]
		case "Grep" | "Glob":
			return tr("searches ", "cherche ") + tool_input["pattern"]
		case "WebSearch":
			return tr(f'searches the web for "{tool_input["query"]}"', f"cherche « {tool_input['query']} » sur le web")
		case "WebFetch":
			return tr("reads ", "lit ") + urlparse(str(tool_input["url"])).netloc
		case "Agent" | "Task":
			return tr("hands off a task: ", "confie une tâche : ") + tool_input["description"]
		case "AskUserQuestion":
			return tool_input["questions"][0]["question"]
		case "mcp__claudechan__press" | "mcp__claudechan__fill" if element := desktop.ELEMENTS.get(str(tool_input["element"])):
			verb = tr("presses ", "appuie sur ") if name.endswith("press") else tr("fills ", "remplit ")
			return f"{verb}{element.label} ({Path(element.app).stem})"
		case _:
			return name.rsplit("__", 1)[-1]

