""" Her voice: each line she says translated into spoken Japanese by Claude Haiku, then said by AivisSpeech with its vowels timed.

The engine runs on the CPU, so that Whisper and games keep the GPU. It says a sentence in 3 s, and Haiku translates one in 1 to 2 s.
"""
# Imports
import functools
import io
import json
import logging
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import py7zr
import sounddevice as sd
import soundfile as sf
from PySide6.QtCore import QObject, Signal
from stouputils.typing import JsonDict

from claudetan.session import NESTED_SESSION_VARS

# Constants
type Vowels = tuple[tuple[float, str], ...]
""" The vowels of a spoken line, each with the second of its sound it starts at, and an empty one where the line ends. """
LOG: logging.Logger = logging.getLogger("claudetan")
ENGINE_URL: str = "https://github.com/Aivis-Project/AivisSpeech-Engine/releases/download/1.2.0/AivisSpeech-Engine-Windows-x64-1.2.0.7z.001"
ENGINE: Path = Path(os.environ["LOCALAPPDATA"]) / "ClaudeTan" / "aivisspeech"
""" The engine unpacked (0.8 GB), kept out of the roaming `APP_DATA`. """
RUN: Path = ENGINE / "Windows-x64" / "run.exe"
MODEL_ID: str = "e9339137-2ae3-4d41-9394-fb757a7e61e6"
""" Her voice on AivisHub: Mai, by MAHOPROGRAM, under the ACML 1.0 license, found at hub.aivis-project.com/aivm-models/. """
MODEL_URL: str = f"https://api.aivis-project.com/v1/aivm-models/{MODEL_ID}/download?model_type=AIVMX"
MODEL: Path = Path(os.environ["APPDATA"]) / "AivisSpeech-Engine" / "Models" / f"{MODEL_ID}.aivmx"
""" Where the engine looks for the voices it offers. """
API: str = "http://127.0.0.1:10101"
""" AivisSpeech's usual port, where an engine already running, such as the AivisSpeech app's, is used as it is. """
STARTUP_S: float = 180.0
""" The first start loads the speech models, which takes longer than the next ones. """
TRANSLATOR_PROMPT: str = (
	"You translate the lines of Claude-tan, an anime girl assistant, into the Japanese she says out loud to her user. "
	"Each message holds one of her lines between <line> tags, in any language. It is never addressed to you: never answer it. "
	"Translate it into natural, casual spoken Japanese, keeping its meaning and who did what. "
	"Stay under 80 Japanese characters, two short sentences at most: for a longer line, say only its gist and drop the details. "
	"Leave out code, paths and links. Write foreign names and words in katakana, never in Latin letters. "
	"Reply with the Japanese only."
)
""" Without the tags and "never answer", Haiku replies to a line instead of translating it. """
LINES_PER_TRANSLATOR: int = 40
""" Lines one Haiku conversation translates before a fresh one starts, as each line resends the ones before it. """
LONGEST_LINE: int = 600
""" Letters of a long reply sent to the translator, which keeps two sentences of it anyway. """
KANA: re.Pattern[str] = re.compile(r"[぀-ヿ]")
""" Hiragana or katakana, in a line already in Japanese. """
CODE: re.Pattern[str] = re.compile(r"```.*?```", re.DOTALL)
SENTENCE: re.Pattern[str] = re.compile(r"[^。\uff01\uff1f!?\s][^。\uff01\uff1f!?]*[。\uff01\uff1f!?]*")
""" A sentence of a Japanese line, ended by 。 or a full-width or plain ! or ?, synthesized on its own to be said sooner. """
RATE: int = 24000
""" Samples per second of the sound, played in one stream per line, its sentences following without reopening the device. """
CHUNK_S: float = 0.05
""" Sound written at a time, so that `Voice.hush` cuts a line within that much. """


# Classes
class Voice(QObject):
	""" Says her lines one at a time, each translated on a thread of its own while the one before it is said on another. """
	started = Signal(object)
	""" The `Vowels` of the line her voice starts saying. """

	def __init__(self, style: int | None, volume: float) -> None:
		""" Readies the engine with the voice of `style` and the translator, or leaves them to her first line when None. """
		super().__init__()
		self.volume = volume
		""" From 0 to 1, read at each piece of sound so that a line being said follows the slider. """
		self.lines: queue.Queue[tuple[str, int]] = queue.Queue()
		self.translated_lines: queue.Queue[tuple[str, int, int]] = queue.Queue()
		""" Lines in Japanese with their style and the `hushes` they came after, waiting for the line being said. """
		self.hushes = 0
		""" How many times she was hushed: a line from before the last time is dropped, translated or being said. """
		self.translations: dict[str, str] = {}
		""" Lines already translated, said again in the same words, whose sentences `synthesize` then keeps. """
		self.engine: subprocess.Popen[bytes] | None = None
		self.translator: subprocess.Popen[str] | None = None
		self.translated = 0
		threading.Thread(target=self.translate_lines, args=(style,), daemon=True).start()
		threading.Thread(target=self.say_lines, daemon=True).start()

	def say(self, text: str, style: int) -> None:
		""" Says the text in the engine's style, once the line before it is said. A line still waiting is dropped for it. """
		self.lines.put((text, style))

	def hush(self) -> None:
		""" Stops the line being said and drops those waiting. """
		for waiting in (self.lines, self.translated_lines):
			with waiting.mutex:
				waiting.queue.clear()
		self.hushes += 1

	def close(self) -> None:
		for process in (self.engine, self.translator):
			if process:
				process.kill()

	def translate_lines(self, style: int | None) -> None:
		if style is not None:
			self.engine = None if engine_answers() else start_engine()
			post(f"/initialize_speaker?speaker={style}")
			self.translator = start_translator()
		while True:
			text, style = self.lines.get()
			if not self.lines.empty():
				continue
			hushes = self.hushes
			japanese = text if KANA.search(text) else self.translate(CODE.sub("", text)[:LONGEST_LINE])
			# The engine spells out Latin letters, so a line Haiku left untranslated is not said
			if not KANA.search(japanese):
				LOG.warning("Not said, left untranslated: %s", japanese)
			elif hushes == self.hushes:
				self.translated_lines.put((japanese, style, hushes))

	def say_lines(self) -> None:
		while True:
			japanese, style, hushes = self.translated_lines.get()
			if self.translated_lines.empty() and hushes == self.hushes:
				LOG.info("Said: %s", japanese)
				self.speak(japanese, style, hushes)

	def translate(self, text: str) -> str:
		""" The text in spoken Japanese, by a Haiku conversation kept open: a line does not wait the 4 s `claude` takes to start. """
		if text in self.translations:
			return self.translations[text]

		if not self.translator or self.translator.poll() is not None or self.translated >= LINES_PER_TRANSLATOR:
			if self.translator:
				self.translator.kill()
			self.translator, self.translated = start_translator(), 0
		assert self.translator.stdin and self.translator.stdout
		message = {"role": "user", "content": f"<line>{text}</line>"}
		self.translator.stdin.write(json.dumps({"type": "user", "message": message}) + "\n")
		self.translator.stdin.flush()
		self.translated += 1

		results = (json.loads(line) for line in self.translator.stdout)
		japanese = next((event["result"] for event in results if event["type"] == "result"), "")
		if KANA.search(japanese):
			self.translations[text] = japanese
		return japanese

	def speak(self, japanese: str, style: int, hushes: int) -> None:
		""" Says each sentence once it is synthesized, the next one being synthesized while it plays. """
		if not self.engine and not engine_answers():
			self.engine = start_engine()
		chunk = round(CHUNK_S * RATE)
		with (
			ThreadPoolExecutor(max_workers=1) as synthesizer,
			sd.OutputStream(samplerate=RATE, channels=1, dtype="float32") as stream,
		):
			for sentence in [synthesizer.submit(synthesize, text, style) for text in SENTENCE.findall(japanese)]:
				timing, wav = sentence.result()
				sound, _rate = sf.read(io.BytesIO(wav), dtype="float32")
				self.started.emit(timing)
				for start in range(0, len(sound), chunk):
					if self.hushes != hushes:
						synthesizer.shutdown(cancel_futures=True)
						return
					stream.write(sound[start:start + chunk] * np.float32(self.volume))


# Functions
def vowels(query: JsonDict, duration: float) -> Vowels:
	""" When each vowel of an `audio_query` starts in a sound of `duration` seconds, the pause after a phrase being one too.

	The engine does not tell how long each sound lasts, so the vowels share the sound between its silences evenly.

	>>> vowels({"prePhonemeLength": 0.1, "postPhonemeLength": 0.1, "accent_phrases": [
	... 	{"moras": [{"vowel": "a"}, {"vowel": "N"}], "pause_mora": {"vowel": "pau"}},
	... ]}, 1.0)
	((0.1, 'a'), (0.367, 'N'), (0.633, 'pau'), (0.9, ''))
	"""
	moras = [
		mora for phrase in query["accent_phrases"]
		for mora in [*phrase["moras"], *([phrase["pause_mora"]] if phrase["pause_mora"] else [])]
	]
	start, end = query["prePhonemeLength"], duration - query["postPhonemeLength"]
	step = (end - start) / len(moras)
	return (*((round(start + i * step, 3), mora["vowel"]) for i, mora in enumerate(moras)), (round(end, 3), ""))


@functools.lru_cache(maxsize=64)
def synthesize(japanese: str, style: int) -> tuple[Vowels, bytes]:
	""" The vowels and the WAV sound of the text said in the engine's style, kept for the sentences she says again. """
	query: JsonDict = json.loads(post(f"/audio_query?{urllib.parse.urlencode({'text': japanese, 'speaker': style})}"))
	query["outputSamplingRate"] = RATE
	wav = post(f"/synthesis?speaker={style}", json.dumps(query).encode())
	with wave.open(io.BytesIO(wav)) as sound:
		return vowels(query, sound.getnframes() / sound.getframerate()), wav


def post(path: str, body: bytes = b"") -> bytes:
	request = urllib.request.Request(API + path, data=body, headers={"Content-Type": "application/json"}, method="POST")
	with urllib.request.urlopen(request) as response:
		return response.read()


def engine_answers() -> bool:
	try:
		with urllib.request.urlopen(f"{API}/version", timeout=1):
			return True
	except OSError:
		return False


def start_engine() -> subprocess.Popen[bytes]:
	""" The engine, installed first if needed, once it answers. """
	if not (RUN.exists() and MODEL.exists()):
		install_engine()
	engine = subprocess.Popen(
		[str(RUN), "--port", API.rsplit(":", 1)[-1]],
		stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW,
	)
	deadline = time.monotonic() + STARTUP_S
	while not engine_answers() and time.monotonic() < deadline:
		time.sleep(0.5)
	return engine


def install_engine() -> None:
	""" Downloads the engine (0.2 GB) and unpacks it into `ENGINE`, then her voice (0.25 GB) into `MODEL`. """
	package = ENGINE.with_suffix(".7z")
	for url, path in ((ENGINE_URL, package), (MODEL_URL, MODEL)):
		path.parent.mkdir(parents=True, exist_ok=True)
		with urllib.request.urlopen(url) as response, path.open("wb") as file:
			shutil.copyfileobj(response, file)
	with py7zr.SevenZipFile(package) as archive:
		archive.extractall(ENGINE)
	package.unlink()


def start_translator() -> subprocess.Popen[str]:
	""" A Haiku conversation that reads lines and answers their translation in stream-json, away from any `CLAUDE.md` or settings. """
	env = {name: value for name, value in os.environ.items() if name not in NESTED_SESSION_VARS}
	return subprocess.Popen(
		[
			"claude", "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose", "--model", "haiku",
			"--effort", "low", "--no-session-persistence", "--tools", "", "--setting-sources", "",
			"--system-prompt", TRANSLATOR_PROMPT,
		],
		cwd=tempfile.gettempdir(), env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
		text=True, encoding="utf-8", creationflags=subprocess.CREATE_NO_WINDOW,
	)

