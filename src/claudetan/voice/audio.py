""" Sound coming in: the microphone and the PC's own output, cut into sentences by Silero VAD for Whisper. """
# Imports
import functools
import queue
from collections.abc import Iterator
from dataclasses import dataclass

import ctranslate2
import numpy as np
import soundcard as sc
import sounddevice as sd
from faster_whisper import WhisperModel
from faster_whisper.vad import get_vad_model

# Constants
type Audio = np.ndarray[tuple[int], np.dtype[np.float32]]
RATE: int = 16000
FRAME: int = 512
""" Samples per VAD step, the window Silero expects at 16 kHz (32 ms). """
EARLY_CHECK_FRAMES: int = 40
""" Length (1.3 s) at which a sentence still being spoken is transcribed once, so she reacts to the wake phrase before it ends. """
GPU: bool = ctranslate2.get_cuda_device_count() > 0
""" Whether an NVIDIA GPU runs Whisper. The CPU, 30 times slower, runs a smaller model, and only after the wake phrase. """


# Classes
@dataclass(frozen=True)
class Speech:
	audio: Audio
	ended: bool
	""" False for the opening of a sentence still being spoken. """


# Functions
@functools.cache
def load_whisper() -> WhisperModel:
	""" Whisper, shared by every caller and downloaded from Hugging Face on the first call: 1.6 GB on the GPU, 0.5 GB on the CPU.

	On the CPU, `small` takes 4 s a sentence where `large-v3-turbo` takes 20, and `base` mistakes French for other languages.
	"""
	if GPU:
		return WhisperModel("large-v3-turbo", device="cuda", compute_type="int8_float16")
	return WhisperModel("small", device="cpu", compute_type="int8")


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


def pc_sound() -> Iterator[Audio]:
	""" What the default speakers play, captured by WASAPI loopback at the microphone's rate, silence included. """
	loopback = sc.get_microphone(sc.default_speaker().name, include_loopback=True)
	# WASAPI records garbage on a single channel, so both are recorded and averaged
	with loopback.recorder(samplerate=RATE, channels=2, blocksize=FRAME) as recorder:
		while True:
			yield recorder.record(numframes=FRAME).mean(axis=1)

