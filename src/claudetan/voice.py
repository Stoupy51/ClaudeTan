""" The microphone, cut into sentences by Silero VAD and transcribed by Whisper, reduced to the commands spoken to her. """
# Imports
import queue
import re
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
from faster_whisper.vad import get_vad_model
from PySide6.QtCore import QObject, Signal

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
	heard = Signal(str)
	""" A command, said after the wake phrase or alone within `FOLLOW_UP_S` of it. """

	def __init__(self, language: str | None, wake: re.Pattern[str]) -> None:
		super().__init__()
		self.language = language
		self.wake = wake
		self.loaded = threading.Event()

	def run(self, frames: Iterator[Audio]) -> None:
		whisper = load_whisper()
		self.loaded.set()
		awake_until = 0.0
		for speech in utterances(frames):
			segments, _ = whisper.transcribe(speech.audio, language=self.language, beam_size=1, condition_on_previous_text=False)
			text = " ".join(segment.text.strip() for segment in segments)
			match = self.wake.match(text)
			if match:
				if time.monotonic() > awake_until:
					self.woke.emit()
				awake_until = time.monotonic() + FOLLOW_UP_S

			command = match.group(1) if match else text
			if speech.ended and command and time.monotonic() < awake_until:
				self.heard.emit(command)
				awake_until = 0.0


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


def utterances(frames: Iterator[Audio]) -> Iterator[Speech]:
	""" Sentences cut out of the frames: one starts after 250 ms above the threshold and ends after 800 ms of silence or 15 s.

	Each sentence reaching `EARLY_CHECK_FRAMES` is also yielded once before it ends.
	"""
	vad = get_vad_model()
	window: list[Audio] = []
	speech: list[Audio] = []
	voiced = silent = 0
	for frame in frames:
		window = [*window[-15:], frame]
		probability = float(vad(np.concatenate(window))[-1])
		voiced = voiced + 1 if probability > 0.5 else 0
		silent = silent + 1 if probability < 0.35 else 0
		if speech:
			speech.append(frame)
		elif voiced >= 8:
			speech = list(window)
		else:
			continue

		ended = silent >= 25 or len(speech) >= 15 * RATE // FRAME
		if ended or len(speech) == EARLY_CHECK_FRAMES:
			yield Speech(audio=np.concatenate(speech), ended=ended)
		if ended:
			speech = []

