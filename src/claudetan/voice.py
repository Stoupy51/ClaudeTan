""" The microphone, cut into sentences by Silero VAD and transcribed by Whisper, reduced to the commands spoken to her. """
# Imports
import queue
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
from faster_whisper.vad import get_vad_model
from PySide6.QtCore import QObject, Signal

from claudetan.actions import route
from claudetan.config import Config

# Constants
type Audio = np.ndarray[tuple[int], np.dtype[np.float32]]
RATE: int = 16000
FRAME: int = 512
""" Samples per VAD step, the window Silero expects at 16 kHz (32 ms). """
EARLY_CHECK_FRAMES: int = 40
""" Length (1.3 s) at which a sentence still being spoken is transcribed once, so she reacts to the wake phrase before it ends. """
FOLLOW_UP_S: float = 8.0
""" How long a lone wake phrase keeps her listening for the command. """


# Classes
@dataclass(frozen=True)
class Speech:
	audio: Audio
	ended: bool
	""" False for the opening of a sentence still being spoken. """


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

	def __init__(self, config: Config) -> None:
		super().__init__()
		self.config = config
		self.loaded = threading.Event()
		self.awake_until = 0.0
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
		match = self.config.wake.match(text)
		if match:
			if time.monotonic() > self.awake_until:
				self.woke.emit()
			self.awake_until = time.monotonic() + FOLLOW_UP_S

		command = match.group(1) if match else text
		if ended and command and (self.request or time.monotonic() < self.awake_until):
			self.add(command)
			self.awake_until = 0.0

	def add(self, sentence: str) -> None:
		self.request.append(sentence)
		request = " ".join(self.request)
		if self.config.cancel.search(request):
			self.request = []
			self.cancelled.emit()
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


# Functions
def load_whisper() -> WhisperModel:
	""" Whisper on the GPU, downloaded from Hugging Face on the first call (1.6 GB). """
	return WhisperModel("large-v3-turbo", device="cuda", compute_type="int8_float16")


def microphone() -> Iterator[Audio]:
	frames: queue.Queue[Audio] = queue.Queue()
	with sd.InputStream(
		samplerate=RATE, channels=1, dtype="float32", blocksize=FRAME,
		callback=lambda data, _count, _time, _status: frames.put(data[:, 0].copy()),
	):
		while True:
			yield frames.get()


def utterances(frames: Iterator[Audio], pause_s: float) -> Iterator[Speech | None]:
	""" Sentences cut out of the frames: one starts after 250 ms above the threshold and ends after 800 ms of silence or 15 s.

	Each sentence reaching `EARLY_CHECK_FRAMES` is also yielded once before it ends, and None once `pause_s` pass without a voice.
	"""
	speech: list[Audio] = []
	for window, voiced, silent in voice_activity(frames):
		if speech:
			speech.append(window[-1])
		elif voiced >= 8:
			speech = list(window)
		elif silent == round(pause_s * RATE / FRAME):
			yield None
			continue
		else:
			continue

		ended = silent >= 25 or len(speech) >= 15 * RATE // FRAME
		if ended or len(speech) == EARLY_CHECK_FRAMES:
			yield Speech(audio=np.concatenate(speech), ended=ended)
		if ended:
			speech = []


def voice_activity(frames: Iterator[Audio]) -> Iterator[tuple[list[Audio], int, int]]:
	""" Each frame at the end of the half second before it, with how many frames in a row Silero VAD found voiced and silent. """
	vad = get_vad_model()
	window: list[Audio] = []
	voiced = silent = 0
	for frame in frames:
		window = [*window[-15:], frame]
		probability = float(vad(np.concatenate(window))[-1])
		voiced = voiced + 1 if probability > 0.5 else 0
		silent = silent + 1 if probability < 0.35 else 0
		yield window, voiced, silent

