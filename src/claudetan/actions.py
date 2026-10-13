""" What she does on the computer: said aloud as the phrases of an action, or called by the session as an MCP tool. """
# Imports
import re
from collections.abc import Callable, Mapping
from ctypes import windll
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtGui import QGuiApplication

from claudetan.config import Config
from claudetan.services import discord, programs, weather
from claudetan.services.alarms import Alarms
from claudetan.voice.meeting import Meeting


# Classes
@dataclass(frozen=True)
class Action:
	""" Something she does on the computer: the whole request matches `phrases`, or the session calls the tool `name`. """
	name: str
	description: str
	""" What the session reads to choose the tool. """
	run: Callable[[Mapping[str, str | None]], str]
	""" Carries the action out and returns what she says about it. """
	phrases: str = ""
	""" Its named groups are the arguments the request gives. Empty for a tool only the session calls. """
	parameters: Mapping[str, str] = field(default_factory=dict[str, str])
	""" Each argument the action takes, with what it is. """


# Constants
VK_MENU, VK_F10 = 0x12, 0x79
VK_MUTE = 0xAD
KEY_UP: int = 0x0002
""" `KEYEVENTF_KEYUP`, the flag of a key release for `keybd_event`. """
CURLY_APOSTROPHE: str = chr(0x2019)
""" The apostrophe Whisper sometimes writes, turned into a straight one before matching phrases. """
ALARMS: Alarms = Alarms()
""" The timers set by voice or by the session. """
MEETING: Meeting = Meeting()
""" The one meeting transcription, started and stopped by voice. """
UNITS: dict[str, int] = {"s": 1, "m": 60, "h": 3600}
""" Seconds in a unit of time, by its first letter. """
SCREENS: dict[str, int] = {"1": 1, "un": 1, "one": 1, "2": 2, "deux": 2, "two": 2, "3": 3, "trois": 3, "three": 3}
""" Screen numbers as Whisper may write them. """
MODELS: tuple[str, ...] = ("opus", "sonnet", "haiku")
""" The models of `/model` she switches to by name. """
ACTIONS: list[Action] = [
	Action(
		name="screenshot",
		description="Saves a screenshot of one screen in the Screenshots folder of the user's pictures.",
		phrases=r"(?:fais une |prends une |take a )?(?:capture|screenshot)(?: d'écran)?"
		r"(?: (?:de |of )?(?:l' ?écran|screen|monitor)(?: (?P<screen>[1-3]|un|deux|trois|one|two|three))?)?",
		run=lambda arguments: screenshot(SCREENS[(arguments.get("screen") or "1").lower()]),
		parameters={"screen": "Screen number from 1, 1 by default."},
	),
	Action(
		name="meeting_start",
		description="Writes what the PC plays and the microphone hears into a file of the Transcriptions folder, until meeting_stop.",
		phrases=r"(?:lance|démarre|commence) (?:la |une )?(?:re)?transcription(?: de la réunion)?|transcris(?: la réunion)?"
		r"|(?:start )?(?:transcribing|transcribe)(?: the meeting)?|start (?:a |the )?transcription",
		run=lambda _: MEETING.start(),
	),
	Action(
		name="meeting_stop",
		description="Stops the transcription started by meeting_start and says where its file is.",
		phrases=r"(?:arrête|stoppe|termine|coupe) (?:la )?(?:re)?transcription|stop (?:the )?(?:transcription|transcribing)",
		run=lambda _: MEETING.stop(),
	),
	Action(
		name="stop_all",
		description="Stops the running request, its agents and the queued ones, and restarts this session. Only if the user asks.",
		phrases=r"(?:stop|arrête|stoppe|annule)(?: (?:tout|ça|everything|it))?(?: (?:maintenant|now))?",
		run=lambda _: "J'arrête tout, je repars de zéro.",
	),
	Action(
		name="clip",
		description="Saves the last minutes of the game with ShadowPlay, by pressing Alt+F10.",
		phrases=r"(?:enregistre|clippe|clip|save)(?: (?:ça|ca|ce moment|les dernières minutes|that|it|the replay))?",
		run=lambda _: press(VK_MENU, VK_F10, said="J'ai appuyé sur Alt+F10 pour ShadowPlay."),
	),
	Action(
		name="model",
		description="Switches the model this session answers with, once the current request is done.",
		phrases=r"(?:passe|bascule|switch|mets-toi)(?: en| sur| to)?(?: mode)? (?P<model>" + "|".join(MODELS) + ")",
		run=lambda arguments: f"Je passe en {model}." if (model := chosen_model(arguments)) else f"Choisis {', '.join(MODELS)}.",
		parameters={"model": f"One of {', '.join(MODELS)}."},
	),
	Action(
		name="timer",
		description="Rings after a while, with a sound and a message, and says what the timer is for when given.",
		phrases=r"(?:(?:mets|lance|démarre|règle|programme|set|start) )?(?:un |a )?(?:minuteur|timer)(?: de| pour| of| for)?"
		r" (?P<amount>\d+(?:[.,]\d+)?) ?(?P<unit>secondes?|sec|s|minutes?|min|heures?|h)?",
		run=lambda arguments: set_timer(arguments["amount"] or "0", arguments.get("unit") or "m", arguments.get("label") or ""),
		parameters={
			"amount": "How long, as a number.", "unit": "seconds, minutes or hours, minutes by default.", "label": "What it is for.",
		},
	),
	Action(
		name="weather",
		description="The weather now and for the day in a city, the one of the config when none is given.",
		phrases=r"(?:(?:quelle est|donne-moi|dis-moi) )?(?:la météo|the weather|quel temps (?:fait-il|il fait))"
		r"(?: (?:à|a|de|pour|sur|in|at) (?P<city>.+))?",
		run=lambda arguments: forecast(arguments.get("city") or ""),
		parameters={"city": "Name of the city, the one of the config by default."},
	),
	Action(
		name="launch_program",
		description="Opens a program installed on the computer, found by part of its name as the Start menu shows it.",
		run=lambda arguments: programs.launch(arguments["name"] or ""),
		parameters={"name": "Part of the program's name, such as Spotify or Discord."},
	),
	Action(
		name="discord_messages",
		description="Reads the last direct messages the user exchanged with a person on Discord. It never sends anything.",
		phrases=r"(?:lis|montre|affiche)(?:-moi| moi)? (?:les )?(?:derniers )?(?:messages|mp) (?:de |d'|avec )(?P<person>.+)",
		run=lambda arguments: discord_messages(arguments["person"] or "", int(arguments.get("count") or 10)),
		parameters={"person": "Part of the person's Discord name.", "count": "How many messages, 10 by default."},
	),
	Action(
		name="mute",
		description="Mutes the PC's sound, or unmutes it when it is muted.",
		phrases=r"coupe le son|(?:re)?mets le son|mute|unmute",
		run=lambda _: press(VK_MUTE, said="C'est fait."),
	),
]
""" Every action, tried in order. The lambdas call functions defined below. """


# Functions
def route(request: str) -> tuple[Action, dict[str, str | None]] | None:
	""" The action whose phrases are the whole request, with the punctuation around it, and the arguments it gives.

	>>> route("Capture l'écran 2.")[0].name, route("Capture l'écran 2.")[1]["screen"]
	('screenshot', '2')
	>>> route("Coupe le son !")[0].name
	'mute'
	>>> route("Passe en Opus !")[0].name, route("Passe en Opus !")[1]["model"]
	('model', 'Opus')
	>>> route("Arrête la transcription.")[0].name
	'meeting_stop'
	>>> route("Mets pause, puis ouvre Spotify.") is None
	True
	"""
	words = request.strip(" .,;:!?").replace(CURLY_APOSTROPHE, "'")
	matches = ((action, re.fullmatch(action.phrases, words, re.IGNORECASE)) for action in ACTIONS)
	return next(((action, match.groupdict()) for action, match in matches if match), None)


def chosen_model(arguments: Mapping[str, str | None]) -> str | None:
	""" The model the arguments name, None when it is not one of `MODELS`.

	>>> chosen_model({"model": "Opus"}), chosen_model({"model": "gpt"})
	('opus', None)
	"""
	model = (arguments["model"] or "").lower()
	return model if model in MODELS else None


def set_timer(amount: str, unit: str, label: str) -> str:
	""" Starts a timer of `amount` of the unit starting with the letter of `unit`, and says how long it runs.

	>>> set_timer("0", "s", "")
	'Minuteur de 0 s lancé.'
	"""
	seconds = round(float(amount.replace(",", ".")) * UNITS[unit[0].lower()])
	ALARMS.start(seconds, label)
	hours, rest = divmod(seconds, 3600)
	minutes, secs = divmod(rest, 60)
	duration = " ".join(f"{value} {name}" for value, name in ((hours, "h"), (minutes, "min"), (secs, "s")) if value) or "0 s"
	return f"Minuteur de {duration} lancé."


def forecast(city: str) -> str:
	city = city or Config.load().city
	return weather.forecast(city) if city else "Dis-moi la ville, ou mets-la dans la config (city)."


def discord_messages(person: str, count: int) -> str:
	token = Config.load().discord_token
	return discord.last_messages(person, min(count, 50), token) if token else "Mets ton jeton dans la config (discord_token)."


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

