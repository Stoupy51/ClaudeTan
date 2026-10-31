""" What Claude Code reports about the hidden session and the plan, read by running `claude -p` on its own slash commands. """
# Imports
import os
import re
import subprocess

from claudechan.config import ROOT
from claudechan.i18n import tr
from claudechan.report import Report, Slice
from claudechan.session import NESTED_SESSION_VARS, SESSION_ID

# Constants
PLAN_USAGE: re.Pattern[str] = re.compile(
	r"Current session: (?P<window>\d+)% used\W+resets (?P<window_reset>[^\n]*)\n"
	r"Current week \(all models\): (?P<week>\d+)% used\W+resets (?P<week_reset>[^\n]*)",
)
""" The two limits `/usage` prints, each followed by when it resets, such as "Oct 19, 12am (Europe/Paris)". """
CONTEXT: re.Pattern[str] = re.compile(r"\*\*Model:\*\* (?P<model>\S+)\s+\*\*Tokens:\*\* (?P<tokens>[^\n]*?)\s*\n")
""" The model and the size of the conversation `/context` prints, such as "107.6k / 1m (11%)". """
SHARES: re.Pattern[str] = re.compile(r"^\| (?P<name>[^|]+?) \| (?P<tokens>\d\S*) \| (?P<share>\S+) \|$", re.MULTILINE)
""" A row of the table of what fills the context, such as "| Messages | 290.6k | 29.1% |". """
CATEGORIES: dict[str, str] = {
	"System prompt": "Prompt", "System tools": "Outils", "MCP tools": "Outils MCP",
	"MCP server instructions": "Consignes MCP", "Memory files": "Mémoire", "Skills": "Skills", "Messages": "Messages",
	"Autocompact buffer": "Compactage", "Free space": "Libre",
}
""" The categories of `/context` in French, which English shows as `/context` names them. """
MAGNITUDES: dict[str, int] = {"k": 1000, "m": 1_000_000}
""" What the suffix of a number of tokens multiplies it by. """


# Functions
def plan_usage() -> str:
	""" How much of the 5-hour window and of the week the subscription has used, one limit per line. """
	match = PLAN_USAGE.search(panel("/usage"))
	if not match:
		return tr("I couldn't read your usage.", "Je n'ai pas réussi à lire ton usage.")
	window_reset, week_reset = without_zone(match["window_reset"]), without_zone(match["week_reset"])
	return tr(
		f"Claude plan\n5-hour window: {match['window']}% used, resets {window_reset}"
		f"\nWeek: {match['week']}% used, resets {week_reset}",
		f"Forfait Claude\nFenêtre de 5 h : {match['window']}\u00a0% utilisés, renouvelée {window_reset}"
		f"\nSemaine : {match['week']}\u00a0% utilisés, renouvelée {week_reset}",
	)


def context() -> Report:
	""" How full the context of the hidden session is, then what fills it from the largest to the smallest, the free space last. """
	if not SESSION_ID.exists():
		return Report(tr("There is no conversation yet.", "Il n'y a pas encore de conversation."), ())
	output = panel("/context", "--resume", SESSION_ID.read_text(), "--fork-session")
	match = CONTEXT.search(output)
	if not match:
		return Report(tr("I couldn't read the context.", "Je n'ai pas réussi à lire le contexte."), ())
	shares = output.split("### Estimated usage by category")[-1].split("###")[0]
	rows = sorted(
		(row for row in SHARES.finditer(shares) if "deferred" not in row["name"]),
		key=lambda row: (row["name"] == "Free space", -tokens(row["tokens"])),
	)
	slices = tuple(
		Slice(
			key=row["name"], label=tr(row["name"], CATEGORIES.get(row["name"], row["name"])),
			amount=tr(row["tokens"], french(row["tokens"])), share=tr(row["share"], french(row["share"])),
			fraction=float(row["share"].rstrip("%")) / 100,
		)
		for row in rows
	)
	english = f"Context: {match['tokens']}\nModel: {match['model']}"
	return Report(tr(english, french(f"Contexte : {match['tokens']}\nModèle : {match['model']}")), slices)


def tokens(amount: str) -> float:
	""" A number of tokens as `/context` writes it.

	>>> tokens("2.4k"), tokens("671"), tokens("1m")
	(2400.0, 671.0, 1000000.0)
	"""
	return float(amount.rstrip("km")) * MAGNITUDES.get(amount[-1], 1)


def french(text: str) -> str:
	""" The decimal commas and the unbreakable space before the percent sign of French.

	>>> french("29.1%") == "29,1" + chr(0xA0) + "%"
	True
	"""
	return re.sub(r"(\d)%", r"\1" + chr(0xA0) + "%", text.replace(".", ","))


def without_zone(date: str) -> str:
	""" A reset date without its time zone.

	>>> without_zone("Oct 19, 12am (Europe/Paris)")
	'Oct 19, 12am'
	"""
	return re.sub(r" \([^)]*\)$", "", date)


def panel(command: str, *options: str) -> str:
	""" What `claude` prints for the slash command, which a fresh process answers in about 3 s without a model call. """
	env = {name: value for name, value in os.environ.items() if name not in NESTED_SESSION_VARS}
	run = subprocess.run(
		["claude", "-p", command, "--no-session-persistence", *options], cwd=ROOT, env=env, capture_output=True, text=True,
		encoding="utf-8", timeout=30, creationflags=subprocess.CREATE_NO_WINDOW,
	)
	return run.stdout

