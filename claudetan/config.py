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
ROOT: Path = Path(__file__).resolve().parent.parent
""" The ClaudeTan repository, which the app runs from. """
APP_DATA: Path = Path(os.environ["APPDATA"]) / "ClaudeTan"
DEFAULTS: Path = Path(__file__).with_name("config.toml")
USER_CONFIG: Path = APP_DATA / "config.toml"


# Classes
@dataclass(frozen=True)
class Config:
	language: str | None
	""" Whisper language code, None to detect it on each sentence. """
	wake: re.Pattern[str]
	prompt: str
	""" The user's additions to the system prompt of the hidden session. """

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
			prompt=values["prompt"],
		)

