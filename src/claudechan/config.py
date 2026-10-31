""" User settings: the defaults shipped next to this module, overridden by the keys set in the user's copy. """
# Imports
import os
import re
import shutil
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from PySide6.QtCore import QStandardPaths

# Constants
ROOT: Path = Path(__file__).resolve().parents[2]
""" The ClaudeChan repository, which the app runs from. """
APP_DATA: Path = Path(os.environ["APPDATA"]) / "ClaudeChan"
DEFAULTS: Path = Path(__file__).with_name("config.toml")
USER_CONFIG: Path = APP_DATA / "config.toml"
LOG_FILE: Path = APP_DATA / "claudechan.log"
CRASH_FILE: Path = APP_DATA / "crash.log"
""" Where a crash in native code writes the stack of each thread, which `LOG_FILE` cannot catch. """
SCREENSHOTS: Path = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)) / "Screenshots"
""" Where her screenshots go, a folder the session reads without asking. """


# Classes
@dataclass(frozen=True)
class Config:
	language: str | None
	""" Whisper language code, None to detect it on each sentence. """
	wake: re.Pattern[str]
	pause_s: float
	""" Silence after which a spoken request is sent. """
	done: re.Pattern[str]
	""" Last words that send a spoken request at once, with the punctuation around them. """
	done_alone: re.Pattern[str]
	""" Words that send a spoken request when they make a sentence of their own, after a pause. """
	done_hints: tuple[str, str]
	""" The words of `done_alone` she tells the user to say, in English then in French: its first and its last. """
	cancel: re.Pattern[str]
	""" Last words that drop a spoken request, with the punctuation around them. """
	cancel_alone: re.Pattern[str]
	""" Words that drop a spoken request when they make a sentence of their own. """
	city: str
	""" Where the weather is for when no city is named. """
	allow: re.Pattern[str]
	""" Whole sentences that allow a permission request she asks about. """
	deny: re.Pattern[str]
	""" Whole sentences that refuse it. """
	apps: dict[str, str]
	""" What she may do in each application's windows, "read" or "act", by the file name of its program in lower case. """
	prompt: str
	""" The user's additions to the system prompt of the hidden session. """
	model: str
	""" Model of the hidden session, as `claude --model` takes it. """
	agent_model: str
	""" Model of the agent the session hands complicated requests to. """
	commit_changes: bool
	""" Whether the session commits its changes to the app's code itself, rather than leaving them for the user to review. """
	avatar_zoom: float
	""" Size of Claire and her pill, 1 for their default size. """
	text_zoom: float
	""" Size of her speech bubble and its text, 1 for their default size. """
	typing_speed: float
	""" Letters per second her bubble types a short text at. """
	voice: bool
	""" Whether she says her replies aloud, in Japanese. """
	voice_style: int
	""" The AivisSpeech voice she says them in, by its style id. """
	volume: float
	""" How loud her voice is, from 0 to 1. """

	@classmethod
	def load(cls) -> Self:
		""" The settings, after copying the defaults to `USER_CONFIG` on the first run so the user has a file to edit. """
		if not USER_CONFIG.exists():
			APP_DATA.mkdir(parents=True, exist_ok=True)
			shutil.copyfile(DEFAULTS, USER_CONFIG)
		values = tomllib.loads(DEFAULTS.read_text(encoding="utf-8")) | tomllib.loads(USER_CONFIG.read_text(encoding="utf-8"))
		return cls(
			language=None if values["language"] == "auto" else values["language"],
			wake=re.compile(values["wake"], re.IGNORECASE),
			pause_s=values["pause_s"],
			done=re.compile(rf"\W*(?:\b(?:{values['done']})|[,.!?;:]\s*(?:{values['done_alone']}))\W*$", re.IGNORECASE),
			done_alone=re.compile(rf"\W*(?:{values['done_alone']})\W*", re.IGNORECASE),
			done_hints=(values["done_alone"].split("|")[0], values["done_alone"].split("|")[-1]),
			cancel_alone=re.compile(rf"\W*(?:{values['cancel_alone']})\W*", re.IGNORECASE),
			cancel=re.compile(rf"\W*\b(?:{values['cancel']})\W*$", re.IGNORECASE),
			city=values["city"],
			allow=re.compile(rf"\W*(?:{values['allow']})\W*", re.IGNORECASE),
			deny=re.compile(rf"\W*(?:{values['deny']})\W*", re.IGNORECASE),
			apps={program.lower(): level for program, level in values["apps"].items()},
			prompt=values["prompt"],
			model=values["model"],
			agent_model=values["agent_model"],
			commit_changes=values["commit_changes"],
			avatar_zoom=values["avatar_zoom"],
			text_zoom=values["text_zoom"],
			typing_speed=values["typing_speed"],
			voice=values["voice"],
			voice_style=values["voice_style"],
			volume=values["volume"],
		)


def save_volume(volume: float, path: Path = USER_CONFIG) -> None:
	""" Writes the `volume` key of the user's config, adding it when the file predates it. """
	text, replaced = re.subn(r"^volume\s*=.*$", f"volume = {volume:.2f}", path.read_text(encoding="utf-8"), flags=re.MULTILINE)
	if not replaced:
		text = f"{text.rstrip()}\n\nvolume = {volume:.2f}\n"
	path.write_text(text, encoding="utf-8")

