""" One-time setup, run with `uv run claudetan-setup`: prepares Whisper, then signs in to Claude Code and has it trust the repo. """
# Imports
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np

from claudetan.config import ROOT
from claudetan.voice import RATE, load_whisper


# Functions
def main() -> None:
	print("Downloading Whisper (1.6 GB the first time) and running it once on the GPU...", flush=True)
	segments, _ = load_whisper().transcribe(np.zeros(RATE, np.float32), language="en")
	list(segments)
	print("[ok]   Whisper runs on the GPU", flush=True)

	if not shutil.which("claude"):
		print("[todo] Install Claude Code, then run this setup again: https://code.claude.com/docs/en/setup")
		return
	if not signed_in():
		print("Claude Code opens its sign-in page: sign in with your Claude Pro or Max account.", flush=True)
		subprocess.run(["claude", "auth", "login"])
	# The decision stays with the user: Claude Code shows its own dialog, and records the answer in a file it keeps rewriting
	if not trusted():
		print('Claude Code opens and asks whether you trust this folder: pick "Yes, I trust this folder", then type /exit', flush=True)
		subprocess.run(["claude"], cwd=ROOT)

	if signed_in() and trusted():
		print("[ok]   Claude Code is ready. Start the app with: uv run claudetan")
	else:
		print("[todo] Claude Code is not signed in or does not trust this folder yet: run this setup again.")


def signed_in() -> bool:
	""" Whether Claude Code is signed in with a Claude subscription, which the app needs instead of an API key. """
	status = json.loads(subprocess.run(["claude", "auth", "status"], capture_output=True, text=True).stdout)
	return status.get("authMethod") == "claude.ai"


def trusted() -> bool:
	""" Whether the user has told Claude Code it may work in this repository. """
	projects = json.loads((Path.home() / ".claude.json").read_text(encoding="utf-8")).get("projects", {})
	return bool(projects.get(ROOT.as_posix(), {}).get("hasTrustDialogAccepted"))

