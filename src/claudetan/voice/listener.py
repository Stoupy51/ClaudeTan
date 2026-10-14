""" The microphone's sentences, transcribed by Whisper and reduced to the requests spoken to her. """
# Imports
import re
import threading
import time
from collections.abc import Iterator

from PySide6.QtCore import QObject, Signal

from claudetan import i18n
from claudetan.actions import route
from claudetan.config import Config
from claudetan.voice.audio import GPU, RATE, Audio, Speech, load_whisper, utterances
from claudetan.voice.wake import spot_wake

# Constants
SENTENCES: re.Pattern[str] = re.compile(r"(?<=[.!?])\s+")
""" Whisper punctuates a pause, so a word said after one starts a sentence of its own even when the voice detector kept both. """
FOLLOW_UP_S: float = 8.0
""" How long a lone wake phrase keeps her listening for the command. """


# Classes
class Listener(QObject):
	""" Runs the microphone pipeline on its own thread and reports to the Qt thread through its signals. """
	woke = Signal()
	dictated = Signal(str)
	""" The request so far, while she waits for the rest of it. """
	heard = Signal(str)
	""" A request started after the wake phrase or alone within `FOLLOW_UP_S` of it.

	It ends with its done phrase, a pause, or at once when it is the phrase of a local action.
	"""
	cancelled = Signal()
	answered = Signal(bool)
	""" The user allowed (True) or refused (False) the permission request she is asking about. """

	def __init__(self, config: Config) -> None:
		super().__init__()
		self.config = config
		self.loaded = threading.Event()
		self.awake_until = 0.0
		self.asking = False
		""" Set from the Qt thread while a permission request waits: a bare yes or no then answers it. """
		self.request: list[str] = []
		""" Sentences of the request being dictated. Both are touched only by the microphone thread. """

	def run(self, frames: Iterator[Audio]) -> None:
		whisper = load_whisper()
		if not GPU:
			frames = spot_wake(frames, self.wake)
		self.loaded.set()
		for speech in utterances(frames, self.config.pause_s):
			if speech is None:
				self.send()
				continue
			if not self.transcribes(speech):
				continue
			segments, info = whisper.transcribe(
				speech.audio, language=self.config.language, beam_size=1, condition_on_previous_text=False,
			)
			self.hear(" ".join(segment.text.strip() for segment in segments), info.language, ended=speech.ended)

	def hear(self, text: str, language: str, *, ended: bool) -> None:
		""" Acts on a sentence Whisper heard in `language`, which her lines then follow when the sentence was meant for her. """
		if self.asking and ended and (verdict := self.verdict(text)) is not None:
			i18n.heard = language
			self.answered.emit(verdict)
			return

		match = self.config.wake.match(text)
		if match:
			i18n.heard = language
			self.wake()

		command = match.group(1) if match else text
		if ended and command and (self.request or time.monotonic() < self.awake_until):
			i18n.heard = language
			for part in SENTENCES.split(command):
				self.add(part)
			self.awake_until = 0.0

	def wake(self) -> None:
		""" She is called, by the wake phrase Whisper heard or the one `spot_wake` caught in the sound before Whisper had it. """
		if time.monotonic() > self.awake_until:
			self.woke.emit()
		self.awake_until = time.monotonic() + FOLLOW_UP_S

	def transcribes(self, speech: Speech) -> bool:
		""" Whether Whisper hears the sentence: any on the GPU, only the ended ones that start while she listens on the CPU. """
		if GPU:
			return True
		started = time.monotonic() - len(speech.audio) / RATE
		return speech.ended and (self.asking or bool(self.request) or started < self.awake_until)

	def verdict(self, text: str) -> bool | None:
		if self.config.allow.fullmatch(text):
			return True
		return False if self.config.deny.fullmatch(text) else None

	def add(self, sentence: str) -> None:
		self.request.append(sentence)
		request = " ".join(self.request)
		if self.config.cancel_alone.fullmatch(sentence) or self.config.cancel.search(request):
			self.request = []
			self.cancelled.emit()
		elif self.config.done_alone.fullmatch(sentence):
			self.request.pop()
			self.send()
		elif self.config.done.search(request):
			self.request = [self.config.done.sub("", request)]
			self.send()
		elif route(request):
			self.send()
		else:
			self.dictated.emit(request)

	def send(self) -> None:
		request = " ".join(self.request)
		self.request = []
		if request:
			self.heard.emit(request)

