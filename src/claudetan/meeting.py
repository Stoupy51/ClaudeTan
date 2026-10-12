""" A meeting transcribed until it is stopped: the PC's sound and the microphone, each on its own thread, into one text file. """
# Imports
import itertools
import threading
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QStandardPaths

from claudetan.audio import Audio, load_whisper, microphone, pc_sound, utterances


# Classes
class Meeting:
	""" The transcription in progress, if any. Its file gets one line per sentence, with the time and who said it. """

	def __init__(self) -> None:
		self.path = Path()
		self.running = threading.Event()
		self.writing = threading.Lock()

	def start(self) -> str:
		if self.running.is_set():
			return f"Je transcris déjà dans {self.path.name}."
		folder = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)) / "Transcriptions"
		folder.mkdir(parents=True, exist_ok=True)
		self.path = folder / f"Réunion {datetime.now():%Y-%m-%d %H-%M}.txt"
		self.running.set()
		for speaker, frames in (("Moi", microphone), ("PC", pc_sound)):
			threading.Thread(target=self.transcribe, args=(speaker, frames()), daemon=True).start()
		return f"Je transcris le son du PC et ton micro dans {self.path}."

	def stop(self) -> str:
		if not self.running.is_set():
			return "Je ne transcris rien en ce moment."
		self.running.clear()
		return f"Transcription enregistrée dans {self.path}." if self.path.exists() else "Je n'ai rien entendu."

	def transcribe(self, speaker: str, frames: Iterator[Audio]) -> None:
		whisper = load_whisper()
		# Sentences end on their own, so the pauses `utterances` reports mean nothing here
		for speech in utterances(itertools.takewhile(lambda _: self.running.is_set(), frames), pause_s=60.0):
			if speech is None or not speech.ended:
				continue

			segments, _ = whisper.transcribe(speech.audio, beam_size=1, condition_on_previous_text=False)
			text = " ".join(segment.text.strip() for segment in segments)
			if not text:
				continue
			with self.writing, self.path.open("a", encoding="utf-8") as file:
				file.write(f"[{datetime.now():%H:%M:%S}] {speaker} : {text}\n")

