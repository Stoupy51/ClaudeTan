""" What happens in the demo video and when. """
# Imports
from dataclasses import dataclass, field

from stouputils.typing import JsonDict

from claudechan.overlay.bubble import TYPING_S, TYPING_SPEED

# Constants
WHISPER_S: float = 0.2
""" How long after the end of a sentence Whisper hands it over. """
JAPANESE_REQUEST: str = "自己紹介してくれる?"
JAPANESE_REPLY: tuple[str, ...] = (
	"はじめまして、クロードたんです!",
	"日本語でも大丈夫ですよ。",
)
""" Her reply streamed in two pieces, whatever the language of the video: Claude answers in the one it is asked in. """
CAPTURE: str = "C:/Users/you/Pictures/Screenshots/Capture 2026-10-13 14-32-05.png"


# Classes
@dataclass(frozen=True)
class Chapter:
	title: str
	subtitle: str


@dataclass(frozen=True)
class Words:
	""" Everything the user says and the video writes. """
	language: str
	""" Whisper's code of the language, which her own lines follow. """
	tagline: str
	outro: str
	you: str
	""" The caption's name for the user. """
	chapters: tuple[Chapter, ...]
	question: str
	""" Said in one breath with the word that sends it. """
	reply: tuple[str, ...]
	""" The answer to `question`, streamed in pieces. """
	spoken_reply: str
	""" `reply` in the spoken Japanese her translator gives, the line her voice says, as each `spoken_` field is for its line. """
	cleanup: str
	cleanup_tool: str
	yes: str
	cleaned: str
	dark_mode: str
	handed_off: str
	dark_mode_done: str
	tests: str
	tests_done: str
	spoken_cleaned: str
	spoken_handed_off: str
	spoken_dark_mode_done: str
	spoken_tests_done: str


@dataclass(frozen=True)
class Speak:
	""" The user says the text, which Whisper hears in `language` once it is said. """
	text: str
	language: str


@dataclass(frozen=True)
class Hook:
	""" The hidden session posts a hook event, as Claude Code does while it works. """
	event: JsonDict


@dataclass(frozen=True)
class Leave:
	""" Her dismiss timer runs out, cut short where the video would otherwise wait for the whole reading time. """


@dataclass(frozen=True)
class Read:
	""" The video holds still while the viewer reads the bubble she shows, for `reading_s` of it, and while her voice speaks. """
	longer_s: float = 0.0
	""" Held on top, for a line the viewer also listens to. """


@dataclass(frozen=True)
class Drag:
	""" The mouse long-presses her, or her pill while it is up, and drags it `by` desktop pixels in `seconds`. """
	by: tuple[float, float]
	seconds: float


@dataclass(frozen=True)
class Tune:
	""" The mouse opens her tray menu, slides the volume to `volume`, and clicks away from the menu, which takes 3 s. """
	volume: float


@dataclass(frozen=True)
class Frame:
	""" The camera eases slowly to this view of the desktop and holds it, whatever moves in it, until the next one. """
	center: tuple[float, float]
	zoom: float
	spring: float = 2.2
	""" Softer than the camera's usual pull, so that it settles in about 2 s. """


@dataclass(frozen=True)
class Title:
	""" The chapter card, numbered from 1. """
	number: int
	chapter: Chapter


@dataclass(frozen=True)
class Outro:
	pass


type Cue = Speak | Hook | Leave | Read | Drag | Tune | Frame | Title | Outro


@dataclass
class Timeline:
	""" The cues in order, each one `now` seconds into the video, which `say` moves forward and each `Read` played pushes back. """
	now: float = 0.0
	cues: list[tuple[float, Cue]] = field(default_factory=list[tuple[float, Cue]])

	def cue(self, cue: Cue, then: float = 0.0) -> None:
		self.cues.append((self.now, cue))
		self.now += then

	def say(self, text: str, language: str, then: float = 0.5) -> None:
		""" The user says the text, and the next cue comes once Whisper has handed it over and `then` more seconds. """
		self.cue(Speak(text, language), then=speaking_s(text) + WHISPER_S + then)

	def hook(self, name: str, then: float, **fields: object) -> None:
		self.cue(Hook({"hook_event_name": name, **fields}), then=then)

	def stream(self, pieces: tuple[str, ...], message_id: str, every: float) -> None:
		""" The session's reply typed in, one piece every `every` seconds, then its Stop. """
		for i, piece in enumerate(pieces):
			self.hook("MessageDisplay", then=every, message_id=message_id, delta=piece, final=i == len(pieces) - 1)
		self.hook("Stop", then=0.0, last_assistant_message="".join(pieces))


# Functions
def speaking_s(text: str) -> float:
	""" How long the user takes to say the text.

	>>> round(speaking_s("Hey Claire."), 2)
	0.45
	"""
	return 0.2 + 0.0225 * length(text)


def reading_s(text: str) -> float:
	""" How long a bubble stays up: the time it takes to type, then 22 characters a second, 3 s at most to get the gist of a long one.

	Viewers keep up with subtitles to about 20 characters a second, and start skipping words beyond.

	>>> round(reading_s("Thanks!"), 2), reading_s(200 * "a")
	(0.61, 3.0)
	"""
	return min(3.0, min(TYPING_S, length(text) / TYPING_SPEED) + 0.2 + length(text) / 22)


def length(text: str) -> int:
	""" The text's length, a Japanese character taking as long as two Latin ones to say or to read. """
	return sum(2 if ord(char) > 0x3000 else 1 for char in text)


def screenplay(words: Words) -> Timeline:
	""" The cues of the whole video, which ends at its `now`: an intro, a chapter per feature, and the outro. """
	play = Timeline(now=1.8)
	ask_out_loud(play, words)
	permission_by_voice(play, words)
	background_work(play, words)
	any_language(play, words)
	make_her_yours(play, words)
	play.cue(Leave(), then=0.4)
	play.cue(Outro(), then=2.2)
	return play


def ask_out_loud(play: Timeline, words: Words) -> None:
	play.cue(Title(1, words.chapters[0]), then=0.7)
	ask(play, words.question, words.language)
	play.hook("PreToolUse", then=0.0, tool_name="mcp__claudechan__screenshot", tool_input={"screen": 1})
	play.cue(Read())
	play.stream(words.reply, message_id="reply", every=0.2)
	play.cue(Read(longer_s=0.5))


def permission_by_voice(play: Timeline, words: Words) -> None:
	play.cue(Title(2, words.chapters[1]), then=0.7)
	ask(play, words.cleanup, words.language)
	tool_input = {"command": "rm -r build", "description": words.cleanup_tool}
	play.hook("PermissionRequest", then=0.0, tool_name="Bash", tool_input=tool_input)
	play.cue(Read())
	play.say(words.yes, words.language, then=0.7)
	play.hook("Stop", then=0.0, last_assistant_message=words.cleaned)
	play.cue(Read())


def background_work(play: Timeline, words: Words) -> None:
	play.cue(Title(3, words.chapters[2]), then=0.7)
	ask(play, words.dark_mode, words.language)
	play.hook("Stop", then=0.0, last_assistant_message=words.handed_off)
	play.cue(Read())
	# After her reply rather than before it, as it comes, so that she shrinks to the pill once instead of blinking through it
	play.hook("SubagentStart", then=1.6, agent_id="dark-mode", agent_type="worker")
	play.hook("SubagentStop", then=0.1, agent_id="dark-mode", agent_type="worker", last_assistant_message=words.dark_mode_done)
	play.hook("UserPromptSubmit", then=0.3, prompt="<task-notification>")
	play.hook("Stop", then=0.0, last_assistant_message=words.dark_mode_done)
	play.cue(Read())


def any_language(play: Timeline, words: Words) -> None:
	play.cue(Title(4, words.chapters[3]), then=0.7)
	ask(play, f"Hey Claire, {JAPANESE_REQUEST} Done.", "ja")
	play.stream(JAPANESE_REPLY, message_id="japanese", every=0.25)
	play.cue(Read())
	play.cue(Leave(), then=0.6)


def make_her_yours(play: Timeline, words: Words) -> None:
	""" She is dragged aside while she starts a background task, then her pill, and her voice is turned down from the tray.

	The camera holds wide views here, which take in her whole path, the pill and the menu, so that their moves read calmly.
	"""
	wide = Frame(center=(1152.0, 648.0), zoom=1.25)
	play.cue(wide)
	play.cue(Title(5, words.chapters[4]), then=0.7)
	play.say(words.tests, words.language, then=0.1)
	play.hook("UserPromptSubmit", then=0.2)
	play.cue(Drag(by=(-700.0, -280.0), seconds=1.6), then=1.8)
	play.cue(Frame(center=(1380.0, 776.0), zoom=1.6))
	play.hook("SubagentStart", then=0.6, agent_id="tests", agent_type="worker")
	play.cue(Drag(by=(340.0, 268.0), seconds=1.3), then=1.5)
	play.cue(Tune(volume=0.35), then=3.1)
	play.cue(wide, then=0.8)
	play.hook("SubagentStop", then=0.1, agent_id="tests", agent_type="worker", last_assistant_message=words.tests_done)
	play.hook("UserPromptSubmit", then=0.3, prompt="<task-notification>")
	play.hook("Stop", then=0.0, last_assistant_message=words.tests_done)
	play.cue(Read())


def ask(play: Timeline, request: str, language: str) -> None:
	""" The user asks, and the session takes the prompt as soon as Whisper hands it over, which the viewer then reads. """
	play.say(request, language, then=0.0)
	play.hook("UserPromptSubmit", then=0.0)
	play.cue(Read())

