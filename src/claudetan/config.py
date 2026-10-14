""" User settings: the defaults shipped next to this module, overridden by the keys set in the user's copy. """
# Imports
import os
import re
import shutil
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Self

# Constants
ROOT: Path = Path(__file__).resolve().parents[2]
""" The ClaudeTan repository, which the app runs from. """
APP_DATA: Path = Path(os.environ["APPDATA"]) / "ClaudeTan"
DEFAULTS: Path = Path(__file__).with_name("config.toml")
USER_CONFIG: Path = APP_DATA / "config.toml"
LOG_FILE: Path = APP_DATA / "claudetan.log"


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
	discord_token: str
	""" Token of the user's Discord account, empty until they put it there. """
	prompt: str
	""" The user's additions to the system prompt of the hidden session. """
	model: str
	""" Model of the hidden session, as `claude --model` takes it. """
	agent_model: str
	""" Model of the agent the session hands complicated requests to. """
	avatar_zoom: float
	""" Size of Claude-tan and her pill, 1 for their default size. """
	text_zoom: float
	""" Size of her speech bubble and its text, 1 for their default size. """
	typing_speed: float
	""" Letters per second her bubble types a short text at. """

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
			done=re.compile(rf"\W*\b(?:{values['done']})\W*$", re.IGNORECASE),
			done_alone=re.compile(rf"\W*(?:{values['done_alone']})\W*", re.IGNORECASE),
			done_hints=(values["done_alone"].split("|")[0], values["done_alone"].split("|")[-1]),
			cancel_alone=re.compile(rf"\W*(?:{values['cancel_alone']})\W*", re.IGNORECASE),
			cancel=re.compile(rf"\W*\b(?:{values['cancel']})\W*$", re.IGNORECASE),
			city=values["city"],
			allow=re.compile(rf"\W*(?:{values['allow']})\W*", re.IGNORECASE),
			deny=re.compile(rf"\W*(?:{values['deny']})\W*", re.IGNORECASE),
			discord_token=values["discord_token"],
			prompt=values["prompt"],
			model=values["model"],
			agent_model=values["agent_model"],
			avatar_zoom=values["avatar_zoom"],
			text_zoom=values["text_zoom"],
			typing_speed=values["typing_speed"],
		)

