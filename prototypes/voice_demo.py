""" Voice spike: microphone, Silero VAD utterances, Whisper on the GPU, then the command that follows the wake phrase.

Run with `uv run prototypes/voice_demo.py`, or pass `--wav file.wav` to replay a 16 kHz mono recording through the same pipeline.
"""
# Imports
import argparse
import queue
import re
import time
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf
from faster_whisper import WhisperModel
from faster_whisper.vad import get_vad_model

# Constants
type Audio = np.ndarray[tuple[int], np.dtype[np.float32]]
RATE: int = 16000
FRAME: int = 512
""" Samples per VAD step, the window Silero expects at 16 kHz (32 ms). """
WAKE: re.Pattern[str] = re.compile(r"^\W*(?:hey|hé|he|eh|et|dis|ok|okay)\W+(?:claude|clode|clod|clodo|clown)\b[\s,.!?]*(.*)", re.IGNORECASE)
""" Wake phrase at the start of an utterance as Whisper spells it, "Hé Claude" often coming out as "Et Claude".

Group 1 is the command said in the same breath.
"""
FOLLOW_UP_S: float = 8.0
""" How long a lone wake phrase keeps her listening for the command. """


# Functions
def microphone() -> Iterator[Audio]:
	frames: queue.Queue[Audio] = queue.Queue()
	with sd.InputStream(
		samplerate=RATE, channels=1, dtype="float32", blocksize=FRAME,
		callback=lambda data, _count, _time, _status: frames.put(data[:, 0].copy()),
	):
		while True:
			yield frames.get()


def recording(path: Path) -> Iterator[Audio]:
	audio = np.concatenate([sf.read(path, dtype="float32")[0], np.zeros(RATE * 2, np.float32)])
	for start in range(0, len(audio) - FRAME, FRAME):
		yield audio[start:start + FRAME]


def utterances(frames: Iterator[Audio]) -> Iterator[Audio]:
	""" Group frames into utterances: speech starts after 250 ms above the threshold and ends after 800 ms of silence or 15 s. """
	vad = get_vad_model()
	window: list[Audio] = []
	speech: list[Audio] = []
	voiced = silent = 0
	for frame in frames:
		window = [*window[-15:], frame]
		probability = float(vad(np.concatenate(window))[-1])
		if not speech:
			voiced = voiced + 1 if probability > 0.5 else 0
			if voiced >= 8:
				speech, silent = list(window), 0
			continue
		speech.append(frame)
		silent = silent + 1 if probability < 0.35 else 0
		if silent >= 25 or len(speech) >= 15 * RATE // FRAME:
			yield np.concatenate(speech)
			speech, voiced = [], 0


def main() -> None:
	parser = argparse.ArgumentParser()
	parser.add_argument("--wav", type=Path)
	parser.add_argument("--lang", default=None, help="fr, en, or nothing to detect it per utterance")
	parser.add_argument("--model", default="large-v3-turbo")
	args = parser.parse_args()

	whisper = WhisperModel(args.model, device="cuda", compute_type="int8_float16")
	print("Listening... say « Hey Claude, ... »", flush=True)
	awake_until = 0.0
	for audio in utterances(recording(args.wav) if args.wav else microphone()):
		started = time.monotonic()
		segments, info = whisper.transcribe(audio, language=args.lang, beam_size=1, condition_on_previous_text=False)
		text = " ".join(segment.text.strip() for segment in segments)
		took = f"{time.monotonic() - started:.2f}s {info.language}"

		if (match := WAKE.match(text)) and match.group(1):
			print(f"COMMAND ({took}): {match.group(1)}", flush=True)
		elif match:
			print(f"WAKE ({took}): j'écoute...", flush=True)
			awake_until = time.monotonic() + FOLLOW_UP_S
		elif time.monotonic() < awake_until:
			print(f"COMMAND ({took}): {text}", flush=True)
			awake_until = 0.0
		else:
			print(f"ignored ({took}): {text}", flush=True)


if __name__ == "__main__":
	main()

