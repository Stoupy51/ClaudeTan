""" Voice demo: prints what the app's listener hears, from the microphone or from a 16 kHz mono recording.

Run with `uv run prototypes/voice_demo.py`, or pass `--wav file.wav` to replay a recording.
"""
# Imports
import argparse
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import soundfile as sf

from claudetan.config import Config
from claudetan.voice.audio import FRAME, RATE, Audio, microphone
from claudetan.voice.listener import Listener


# Functions
def recording(path: Path) -> Iterator[Audio]:
	audio = np.concatenate([sf.read(path, dtype="float32")[0], np.zeros(RATE * 2, np.float32)])
	for start in range(0, len(audio) - FRAME, FRAME):
		yield audio[start:start + FRAME]


def timed(frames: Iterator[Audio], clock: list[float]) -> Iterator[Audio]:
	""" The frames, writing into `clock[0]` the second of audio each one ends at. """
	for count, frame in enumerate(frames, start=1):
		clock[0] = count * FRAME / RATE
		yield frame


def main() -> None:
	parser = argparse.ArgumentParser()
	parser.add_argument("--wav", type=Path)
	args = parser.parse_args()

	config = Config.load()
	clock = [0.0]

	def heard(text: str) -> None:
		print(f"{clock[0]:6.2f}s heard: {text}", flush=True)

	listener = Listener(config)
	listener.woke.connect(lambda: print(f"{clock[0]:6.2f}s woke", flush=True))
	listener.heard.connect(heard)
	print("Listening... say « Hey Claude, ... »", flush=True)
	listener.run(timed(recording(args.wav) if args.wav else microphone(), clock))


if __name__ == "__main__":
	main()

