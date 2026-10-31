""" Her voice in the demo video: each sentence she says, synthesized once by AivisSpeech and kept in `voice/` for every render. """
# Imports
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf
from stouputils.typing import JsonDict

from claudechan.overlay.avatar import CHIME_RATE
from claudechan.voice.speech import API, SENTENCE, Vowels, engine_answers, synthesize

# Constants
CLIPS: Path = Path(__file__).with_name("voice")
VOWELS: Path = CLIPS / "vowels.json"
""" The vowels of each clip, by its file name, next to the sentence it says. """


# Classes
@dataclass(frozen=True)
class Clip:
	sound: np.ndarray[tuple[int], np.dtype[np.float32]]
	""" At `CHIME_RATE`, the rate of the soundtrack. """
	vowels: Vowels


# Functions
def clips(japanese: str, style: int) -> list[Clip]:
	""" The sentences of the line, said one after the other as `Voice.speak` says them, in the engine's style.

	Raises:
		SystemExit: A sentence was never synthesized, and no engine answers at `API` to do it.
	"""
	known: dict[str, JsonDict] = json.loads(VOWELS.read_text("utf-8")) if VOWELS.exists() else {}
	said: list[Clip] = []
	for sentence in SENTENCE.findall(japanese):
		name = f"{hashlib.sha1(f'{style} {sentence}'.encode()).hexdigest()[:10]}.wav"
		if name not in known:
			if not engine_answers():
				raise SystemExit(f"Start AivisSpeech on {API}, as her voice does in the app, to synthesize: {sentence}")
			vowels, wav = synthesize(sentence, style)
			CLIPS.mkdir(exist_ok=True)
			(CLIPS / name).write_bytes(wav)
			known[name] = {"sentence": sentence, "vowels": vowels}
			VOWELS.write_text(json.dumps(known, ensure_ascii=False, indent="\t") + "\n", "utf-8")
		sound, rate = sf.read(CLIPS / name, dtype="float32")
		seconds = np.arange(round(len(sound) * CHIME_RATE / rate)) / CHIME_RATE
		resampled = np.interp(seconds, np.arange(len(sound)) / rate, sound).astype(np.float32)
		said.append(Clip(resampled, tuple((at, vowel) for at, vowel in known[name]["vowels"])))
	return said

