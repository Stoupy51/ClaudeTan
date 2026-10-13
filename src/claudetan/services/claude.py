""" What Claude Code reports about the hidden session and the plan, read by running `claude -p` on its own slash commands. """
# Imports
import os
import re
import subprocess

from claudetan.config import ROOT
from claudetan.session import NESTED_SESSION_VARS, SESSION_ID

# Constants
PLAN_USAGE: re.Pattern[str] = re.compile(
	r"Current session: (?P<window>\d+)% used\W+resets (?P<window_reset>[^\n]*)\n"
	r"Current week \(all models\): (?P<week>\d+)% used\W+resets (?P<week_reset>[^\n]*)",
)
""" The two limits `/usage` prints, each followed by when it resets, such as "Oct 19, 12am (Europe/Paris)". """
CONTEXT: re.Pattern[str] = re.compile(r"\*\*Model:\*\* (?P<model>\S+)\s+\*\*Tokens:\*\* (?P<tokens>[^\n]*?)\s*\n")
""" The model and the size of the conversation `/context` prints, such as "107.6k / 1m (11%)". """


# Functions
def plan_usage() -> str:
	""" How much of the 5-hour window and of the week the subscription has used. """
	match = PLAN_USAGE.search(panel("/usage"))
	if not match:
		return "Je n'ai pas réussi à lire ton usage."
	return (
		f"{match['window']} % de la fenêtre de 5 heures (renouvelée {match['window_reset']}), "
		f"{match['week']} % de la semaine (renouvelée {match['week_reset']})."
	)


def context() -> str:
	""" How full the context of the hidden session is. """
	if not SESSION_ID.exists():
		return "Il n'y a pas encore de conversation."
	match = CONTEXT.search(panel("/context", "--resume", SESSION_ID.read_text(), "--fork-session"))
	return f"Contexte de {match['model']} : {match['tokens']}." if match else "Je n'ai pas réussi à lire le contexte."


def panel(command: str, *options: str) -> str:
	""" What `claude` prints for the slash command, which a fresh process answers in about 3 s without a model call. """
	env = {name: value for name, value in os.environ.items() if name not in NESTED_SESSION_VARS}
	run = subprocess.run(
		["claude", "-p", command, "--no-session-persistence", *options], cwd=ROOT, env=env, capture_output=True, text=True,
		encoding="utf-8", timeout=30, creationflags=subprocess.CREATE_NO_WINDOW,
	)
	return run.stdout

