""" Requests she carries out herself, without the Claude session, when the whole request is one of their phrases. """
# Imports
import re
from collections.abc import Callable
from ctypes import windll
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtGui import QGuiApplication

from claudetan.voice.meeting import Meeting


# Classes
@dataclass(frozen=True)
class Action:
	""" Something she does on the computer when the whole request matches `phrases`, ignoring case. """
	name: str
	phrases: str
	run: Callable[[re.Match[str]], str]
	""" Carries the action out and returns what she says about it. """


# Constants
VK_MENU, VK_F10 = 0x12, 0x79
VK_MUTE = 0xAD
KEY_UP: int = 0x0002
""" `KEYEVENTF_KEYUP`, the flag of a key release for `keybd_event`. """
CURLY_APOSTROPHE: str = chr(0x2019)
""" The apostrophe Whisper sometimes writes, turned into a straight one before matching phrases. """
MEETING: Meeting = Meeting()
""" The one meeting transcription, started and stopped by voice. """
SCREENS: dict[str, int] = {"1": 1, "un": 1, "one": 1, "2": 2, "deux": 2, "two": 2, "3": 3, "trois": 3, "three": 3}
""" Screen numbers as Whisper may write them. """
ACTIONS: list[Action] = [
	Action(
		name="screenshot",
		phrases=r"(?:fais une |prends une |take a )?(?:capture|screenshot)(?: d'écran)?"
		r"(?: (?:de |of )?(?:l' ?écran|screen|monitor)(?: (?P<screen>[1-3]|un|deux|trois|one|two|three))?)?",
		run=lambda match: screenshot(SCREENS[(match["screen"] or "1").lower()]),
	),
	Action(
		name="meeting_start",
		phrases=r"(?:lance|démarre|commence) (?:la |une )?(?:re)?transcription(?: de la réunion)?|transcris(?: la réunion)?"
		r"|(?:start )?(?:transcribing|transcribe)(?: the meeting)?|start (?:a |the )?transcription",
		run=lambda _: MEETING.start(),
	),
	Action(
		name="meeting_stop",
		phrases=r"(?:arrête|stoppe|termine|coupe) (?:la )?(?:re)?transcription|stop (?:the )?(?:transcription|transcribing)",
		run=lambda _: MEETING.stop(),
	),
	Action(
		name="stop_all",
		phrases=r"(?:stop|arrête|stoppe|annule)(?: (?:tout|ça|everything|it))?(?: (?:maintenant|now))?",
		run=lambda _: "J'arrête tout, je repars de zéro.",
	),
	Action(
		name="clip",
		phrases=r"(?:enregistre|clippe|clip|save)(?: (?:ça|ca|ce moment|les dernières minutes|that|it|the replay))?",
		run=lambda _: press(VK_MENU, VK_F10, said="J'ai appuyé sur Alt+F10 pour ShadowPlay."),
	),
	Action(
		name="mute",
		phrases=r"coupe le son|(?:re)?mets le son|mute|unmute",
		run=lambda _: press(VK_MUTE, said="C'est fait."),
	),
]
""" Every action, tried in order. The lambdas call functions defined below. """


# Functions
def route(request: str) -> tuple[Action, re.Match[str]] | None:
	""" The action whose phrases are the whole request, with the punctuation around it, and its match.

	>>> route("Capture l'écran 2.")[0].name, route("Capture l'écran 2.")[1]["screen"]
	('screenshot', '2')
	>>> route("Coupe le son !")[0].name
	'mute'
	>>> route("Arrête la transcription.")[0].name
	'meeting_stop'
	>>> route("Mets pause, puis ouvre Spotify.") is None
	True
	"""
	words = request.strip(" .,;:!?").replace(CURLY_APOSTROPHE, "'")
	return next(((action, match) for action in ACTIONS if (match := re.fullmatch(action.phrases, words, re.IGNORECASE))), None)


def screenshot(screen: int) -> str:
	""" Saves the screen, counted from 1 as Qt orders them, in the Screenshots folder of the user's pictures. """
	screens = QGuiApplication.screens()
	if screen > len(screens):
		return f"Je ne vois que {len(screens)} écran{'s' * (len(screens) > 1)}."
	folder = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)) / "Screenshots"
	folder.mkdir(parents=True, exist_ok=True)
	path = folder / f"Capture {datetime.now():%Y-%m-%d %H-%M-%S}.png"
	screens[screen - 1].grabWindow(0).save(str(path))
	return f"Capture de l'écran {screen} enregistrée dans {folder}."


def press(*keys: int, said: str) -> str:
	""" Presses the keys together and returns `said`. """
	for key in keys:
		windll.user32.keybd_event(key, 0, 0, 0)
	for key in reversed(keys):
		windll.user32.keybd_event(key, 0, KEY_UP, 0)
	return said

