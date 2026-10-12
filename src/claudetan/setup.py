""" One-time setup, run with `uv run claudetan-setup`: prepares Whisper, records the owner's voice, then readies Claude Code. """
# Imports
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import stouputils as stp

from claudetan.audio import RATE, Audio, load_whisper, microphone, utterances
from claudetan.config import ROOT
from claudetan.console import enable_colors
from claudetan.voiceprint import VOICEPRINT, embed

# Constants
VOICE_SAMPLE: str = (
	"Hé Claude, fais une capture de l'écran deux, puis mets la musique en pause. "
	"Ensuite, regarde les messages d'Artyu et corrige sa PR avant la réunion de demain matin. "
	"Quand c'est fini, transcris la réunion et range les fichiers dans mes documents."
)
""" Read aloud once by the owner, long and varied enough for a reliable voiceprint. """


# Functions
def main() -> None:
	enable_colors()
	stp.progress("Downloading Whisper (1.6 GB the first time) and running it once on the GPU...")
	segments, _ = load_whisper().transcribe(np.zeros(RATE, np.float32), language="en")
	list(segments)
	stp.info("Whisper runs on the GPU")
	if not VOICEPRINT.exists():
		stp.progress("So that only you can command her, read this aloud into your microphone until it stops you (about 15 s):")
		stp.info(VOICE_SAMPLE)
		VOICEPRINT.parent.mkdir(parents=True, exist_ok=True)
		np.save(VOICEPRINT, embed(record_speech(seconds=15.0)))
		stp.info("Your voice is recorded")

	if not shutil.which("claude"):
		stp.warning(f"Install Claude Code, then run this setup again: {stp.CYAN}https://code.claude.com/docs/en/setup")
		return
	if not signed_in():
		stp.progress("Claude Code opens its sign-in page: sign in with your Claude Pro or Max account.")
		subprocess.run(["claude", "auth", "login"])
	# The decision stays with the user: Claude Code shows its own dialog, and records the answer in a file it keeps rewriting
	if not trusted():
		stp.progress('Claude Code opens and asks whether you trust this folder: pick "Yes, I trust this folder", then type /exit')
		subprocess.run(["claude"], cwd=ROOT)

	if signed_in() and trusted():
		stp.info(f"Claude Code is ready. Start the app with: {stp.CYAN}uv run claudetan")
	else:
		stp.warning("Claude Code is not signed in or does not trust this folder yet: run this setup again.")


def record_speech(seconds: float) -> Audio:
	""" The sentences said into the microphone, stopped once they add up to `seconds`. """
	sentences = utterances(microphone(), pause_s=60.0)
	said: list[Audio] = []
	while sum(map(len, said)) < seconds * RATE:
		speech = next(sentences)
		if speech is not None and speech.ended:
			said.append(speech.audio)
	return np.concatenate(said)


def signed_in() -> bool:
	""" Whether Claude Code is signed in with a Claude subscription, which the app needs instead of an API key. """
	status = json.loads(subprocess.run(["claude", "auth", "status"], capture_output=True, text=True).stdout)
	return status.get("authMethod") == "claude.ai"


def trusted() -> bool:
	""" Whether the user has told Claude Code it may work in this repository. """
	projects = json.loads((Path.home() / ".claude.json").read_text(encoding="utf-8")).get("projects", {})
	return bool(projects.get(ROOT.as_posix(), {}).get("hasTrustDialogAccepted"))

