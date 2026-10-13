""" What happens in the demo video and when, written once and played in each language the video is made in. """
# Imports
from dataclasses import dataclass, field

from stouputils.typing import JsonDict

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
	""" Everything the user says and the video writes, in the language of one video. """
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
	cleanup: str
	cleanup_tool: str
	yes: str
	cleaned: str
	dark_mode: str
	dark_mode_task: str
	handed_off: str
	dark_mode_done: str
	abroad: str
	""" Whisper's code of the other language, which the user switches to once. """
	weather_abroad: str


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
	""" The video holds still while the viewer reads the bubble she shows, for `reading_s` of it. """


@dataclass(frozen=True)
class Title:
	""" The chapter card, numbered from 1. """
	number: int
	chapter: Chapter


@dataclass(frozen=True)
class Outro:
	pass


type Cue = Speak | Hook | Leave | Read | Title | Outro


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

	>>> round(speaking_s("Hey Claude."), 2)
	0.62
	"""
	return 0.2 + 0.038 * length(text)


def reading_s(text: str) -> float:
	""" How long a bubble stays up: 25 characters a second, read as it types, and 3.2 s at most, enough to get the gist of a long one.

	>>> round(reading_s("Thanks!"), 2), reading_s(200 * "a")
	(1.08, 3.2)
	"""
	return min(3.2, 0.8 + length(text) / 25)


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
	play.cue(Leave(), then=0.6)
	play.cue(Outro(), then=2.4)
	return play


def ask_out_loud(play: Timeline, words: Words) -> None:
	play.cue(Title(1, words.chapters[0]), then=0.2)
	play.say(words.question, words.language, then=0.1)
	play.hook("UserPromptSubmit", then=0.7)
	play.hook("PreToolUse", then=0.9, tool_name="mcp__claudetan__screenshot", tool_input={"screen": 1})
	play.stream(words.reply, message_id="reply", every=0.2)
	play.cue(Read())


def permission_by_voice(play: Timeline, words: Words) -> None:
	play.cue(Title(2, words.chapters[1]), then=0.2)
	play.say(words.cleanup, words.language, then=0.1)
	play.hook("UserPromptSubmit", then=0.7)
	tool_input = {"command": "rm -r build", "description": words.cleanup_tool}
	play.hook("PermissionRequest", then=0.0, tool_name="Bash", tool_input=tool_input)
	play.cue(Read())
	play.say(words.yes, words.language, then=1.0)
	play.hook("Stop", then=0.0, last_assistant_message=words.cleaned)
	play.cue(Read())


def background_work(play: Timeline, words: Words) -> None:
	play.cue(Title(3, words.chapters[2]), then=0.2)
	play.say(words.dark_mode, words.language, then=0.1)
	play.hook("UserPromptSubmit", then=0.7)
	play.hook("PreToolUse", then=0.9, tool_name="Agent", tool_input={"description": words.dark_mode_task})
	play.hook("SubagentStart", then=0.1, agent_id="dark-mode", agent_type="worker")
	play.hook("Stop", then=0.0, last_assistant_message=words.handed_off)
	play.cue(Read())
	play.cue(Leave(), then=1.4)
	play.hook("SubagentStop", then=0.1, agent_id="dark-mode", agent_type="worker", last_assistant_message=words.dark_mode_done)
	play.hook("UserPromptSubmit", then=0.3, prompt="<task-notification>")
	play.hook("Stop", then=0.0, last_assistant_message=words.dark_mode_done)
	play.cue(Read())


def any_language(play: Timeline, words: Words) -> None:
	play.cue(Title(4, words.chapters[3]), then=0.2)
	play.say(words.weather_abroad, words.abroad, then=0.0)
	play.cue(Read())
	play.say(f"Hey Claude, {JAPANESE_REQUEST} Done.", "ja", then=0.1)
	play.hook("UserPromptSubmit", then=0.6)
	play.stream(JAPANESE_REPLY, message_id="japanese", every=0.25)
	play.cue(Read())

