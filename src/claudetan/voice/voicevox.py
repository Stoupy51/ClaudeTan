""" Her voice: each line she says translated into spoken Japanese by Claude Haiku, then said by VOICEVOX with its vowels timed.

The engine runs on the CPU, so that Whisper and games keep the GPU. It says a sentence in 1.7 s, and Haiku translates one in 1 to 2 s.
"""
# Imports
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
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import sounddevice as sd
import soundfile as sf
from PySide6.QtCore import QObject, Signal
from stouputils.typing import JsonDict

from claudetan.session import NESTED_SESSION_VARS

# Constants
type Vowels = tuple[tuple[float, str], ...]
""" The vowels of a spoken line, each with the second of its sound it starts at, and an empty one where the line ends. """
LOG: logging.Logger = logging.getLogger("claudetan")
ENGINE_URL: str ="https://github.com/VOICEVOX/voicevox_engine/releases/download/0.25.2/voicevox_engine-windows-cpu-0.25.2.vvpp"
ENGINE: Path = Path(os.environ["LOCALAPPDATA"]) / "ClaudeTan" / "voicevox"
""" The engine unpacked (2.1 GB), kept out of the roaming `APP_DATA`. """
API: str = "http://127.0.0.1:50021"
""" VOICEVOX's usual port, where an engine already running, such as the VOICEVOX app's, is used as it is. """
STARTUP_S: float = 60.0
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
""" Samples per second of VOICEVOX's sound, played in one stream per line, its sentences following without reopening the device. """
CHUNK_S: float = 0.05
""" Sound written at a time, so that `Voice.hush` cuts a line within that much. """


# Classes
class Voice(QObject):
	""" Says her lines one at a time on a thread of its own. """
	started = Signal(object)
	""" The `Vowels` of the line her voice starts saying. """

	def __init__(self, style: int | None) -> None:
		""" Readies the engine with the voice of `style` and the translator, or leaves them to her first line when None. """
		super().__init__()
		self.lines: queue.Queue[tuple[str, int]] = queue.Queue()
		self.hushed = threading.Event()
		self.engine: subprocess.Popen[bytes] | None = None
		self.translator: subprocess.Popen[str] | None = None
		self.translated = 0
		threading.Thread(target=self.run, args=(style,), daemon=True).start()

	def say(self, text: str, style: int) -> None:
		""" Says the text in the VOICEVOX style, once the line before it is said. A line still waiting is dropped for it. """
		self.lines.put((text, style))

	def hush(self) -> None:
		""" Stops the line being said and drops those waiting. """
		with self.lines.mutex:
			self.lines.queue.clear()
		self.hushed.set()

	def close(self) -> None:
		for process in (self.engine, self.translator):
			if process:
				process.kill()

	def run(self, style: int | None) -> None:
		if style is not None:
			self.engine = None if engine_answers() else start_engine()
			post(f"/initialize_speaker?speaker={style}")
			self.translator = start_translator()
		while True:
			text, style = self.lines.get()
			if not self.lines.empty():
				continue
			self.hushed.clear()
			japanese = text if KANA.search(text) else self.translate(CODE.sub("", text)[:LONGEST_LINE])
			# VOICEVOX spells out Latin letters, so a line Haiku left untranslated is not said
			if not KANA.search(japanese):
				LOG.warning("Not said, left untranslated: %s", japanese)
			elif not self.hushed.is_set():
				LOG.info("Said: %s", japanese)
				self.speak(japanese, style)

	def translate(self, text: str) -> str:
		""" The text in spoken Japanese, by a Haiku conversation kept open: a line does not wait the 4 s `claude` takes to start. """
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
		return next((event["result"] for event in results if event["type"] == "result"), "")

	def speak(self, japanese: str, style: int) -> None:
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
					if self.hushed.is_set():
						synthesizer.shutdown(cancel_futures=True)
						return
					stream.write(sound[start:start + chunk])


# Functions
def vowels(query: JsonDict) -> Vowels:
	""" When each vowel of an `audio_query` starts in its sound, the pause after a phrase being one too.

	>>> vowels({"speedScale": 2.0, "prePhonemeLength": 0.1, "accent_phrases": [
	... 	{"moras": [{"consonant_length": 0.1, "vowel": "a", "vowel_length": 0.2}],
	... 	"pause_mora": {"vowel": "pau", "vowel_length": 0.4}},
	... 	{"moras": [{"consonant_length": None, "vowel": "N", "vowel_length": 0.2}], "pause_mora": None},
	... ]})
	((0.1, 'a'), (0.2, 'pau'), (0.4, 'N'), (0.5, ''))
	"""
	at = query["prePhonemeLength"]
	timed: list[tuple[float, str]] = []
	for phrase in query["accent_phrases"]:
		for mora in [*phrase["moras"], *([phrase["pause_mora"]] if phrase["pause_mora"] else [])]:
			at += mora.get("consonant_length") or 0.0
			timed.append((round(at / query["speedScale"], 3), mora["vowel"]))
			at += mora["vowel_length"]
	return (*timed, (round(at / query["speedScale"], 3), ""))


def synthesize(japanese: str, style: int) -> tuple[Vowels, bytes]:
	""" The vowels and the WAV sound of the text said in the VOICEVOX style. """
	query = post(f"/audio_query?{urllib.parse.urlencode({'text': japanese, 'speaker': style})}")
	return vowels(json.loads(query)), post(f"/synthesis?speaker={style}", query)


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
	if not (ENGINE / "run.exe").exists():
		install_engine()
	engine = subprocess.Popen(
		[str(ENGINE / "run.exe"), "--port", API.rsplit(":", 1)[-1]],
		stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW,
	)
	deadline = time.monotonic() + STARTUP_S
	while not engine_answers() and time.monotonic() < deadline:
		time.sleep(0.5)
	return engine


def install_engine() -> None:
	""" Downloads the engine (1.9 GB) and unpacks it into `ENGINE`, the package being a zip file. """
	package = ENGINE.with_suffix(".vvpp")
	package.parent.mkdir(parents=True, exist_ok=True)
	with urllib.request.urlopen(ENGINE_URL) as response, package.open("wb") as file:
		shutil.copyfileobj(response, file)
	with zipfile.ZipFile(package) as archive:
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

