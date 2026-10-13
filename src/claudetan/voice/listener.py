""" The microphone's sentences, transcribed by Whisper and reduced to the requests spoken to her. """
# Imports
import re
import threading
import time
from collections.abc import Iterator

from PySide6.QtCore import QObject, Signal

from claudetan.actions import route
from claudetan.config import Config
from claudetan.voice.audio import Audio, load_whisper, utterances

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
		self.loaded.set()
		for speech in utterances(frames, self.config.pause_s):
			if speech is None:
				self.send()
				continue
			segments, _ = whisper.transcribe(
				speech.audio, language=self.config.language, beam_size=1, condition_on_previous_text=False,
			)
			self.hear(" ".join(segment.text.strip() for segment in segments), ended=speech.ended)

	def hear(self, text: str, *, ended: bool) -> None:
		if self.asking and ended and (verdict := self.verdict(text)) is not None:
			self.answered.emit(verdict)
			return

		match = self.config.wake.match(text)
		if match:
			if time.monotonic() > self.awake_until:
				self.woke.emit()
			self.awake_until = time.monotonic() + FOLLOW_UP_S

		command = match.group(1) if match else text
		if ended and command and (self.request or time.monotonic() < self.awake_until):
			for part in SENTENCES.split(command):
				self.add(part)
			self.awake_until = 0.0

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

