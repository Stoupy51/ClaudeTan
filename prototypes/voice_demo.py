""" Voice demo: prints what the app's listener hears, from the microphone or from a 16 kHz mono recording.

Run with `uv run prototypes/voice_demo.py`, or pass `--wav file.wav` to replay a recording.
`--spotter` runs only the wake phrase spotter the app uses without an NVIDIA GPU, and counts what it catches:
say "Hey Claire" a few times to the microphone, or replay an hour of a video without it to count false alarms,
converted with `ffmpeg -i video.mp4 -ac 1 -ar 16000 video.wav`.
"""
# Imports
import argparse
from collections import deque
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import soundfile as sf

from claudechan.config import Config
from claudechan.voice.audio import FRAME, RATE, Audio, microphone
from claudechan.voice.listener import Listener
from claudechan.voice.wake import spot_wake


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
	parser.add_argument("--spotter", action="store_true", help="run only the wake phrase spotter of a computer without NVIDIA GPU")
	args = parser.parse_args()
	clock = [0.0]
	frames = timed(recording(args.wav) if args.wav else microphone(), clock)
	if args.spotter:
		spotted: list[float] = []

		def spot() -> None:
			spotted.append(clock[0])
			print(f"{clock[0]:6.2f}s spotted", flush=True)

		print("Listening for the wake phrase only...", flush=True)
		deque(spot_wake(frames, spot), maxlen=0)
		print(f"Spotted {len(spotted)} times in {clock[0] / 60:.1f} min")
		return

	config = Config.load()

	def heard(text: str) -> None:
		print(f"{clock[0]:6.2f}s heard: {text}", flush=True)

	listener = Listener(config)
	listener.woke.connect(lambda: print(f"{clock[0]:6.2f}s woke", flush=True))
	listener.heard.connect(heard)
	print("Listening... say « Hey Claire, ... »", flush=True)
	listener.run(frames)


if __name__ == "__main__":
	main()

