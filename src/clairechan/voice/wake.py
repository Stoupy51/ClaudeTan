""" The wake phrase spotted in the sound by a small model, so that a computer without an NVIDIA GPU runs Whisper only after it. """
# Imports
import io
import tarfile
import urllib.request
from collections.abc import Callable, Iterator
from pathlib import Path

import sherpa_onnx

from clairechan.config import APP_DATA
from clairechan.voice.audio import RATE, Audio

# Constants
MODEL_URL: str = (
	"https://github.com/k2-fsa/sherpa-onnx/releases/download/kws-models/sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01.tar.bz2"
)
""" A keyword spotter trained on English speech, which spots any phrase written in its tokens: 2.5 % of one core while it listens. """
MODEL: Path = APP_DATA / "wake"
CHECKPOINT: str = "epoch-12-avg-2-chunk-16-left-64.int8.onnx"
FILES: tuple[str, ...] = ("tokens.txt", f"encoder-{CHECKPOINT}", f"decoder-{CHECKPOINT}", f"joiner-{CHECKPOINT}")
""" The files of the archive the spotter needs, kept in `MODEL`. """
WORD_START: str = chr(0x2581)
""" The mark SentencePiece puts on a token that starts a word, written `_` in `PRONUNCIATIONS`. """
PRONUNCIATIONS: tuple[str, ...] = (
	"_HE Y _C LA I RE", "_HE Y _C LA IR", "_HE Y _C LA RE", "_HA Y _C LA IR",
	"_HE _C LE R", "_E H _C LE R", "_A Y _C LE R", "_A _C LE R", "_A _C LA IR", "_HE _C LA IR",
)
""" "Hey Claire" in the model's tokens, as English and French speakers say it: a French "Hé Claire" sounds like "a cler" to it. """


# Functions
def spot_wake(frames: Iterator[Audio], woke: Callable[[], None]) -> Iterator[Audio]:
	""" The frames passed on as they come, `woke` called as soon as one ends the wake phrase, before the sentence does. """
	spotter = load_spotter()
	stream = spotter.create_stream()
	for frame in frames:
		stream.accept_waveform(RATE, frame)
		while spotter.is_ready(stream):
			spotter.decode_stream(stream)
			if spotter.get_result(stream):
				spotter.reset_stream(stream)
				woke()
		yield frame


def load_spotter() -> sherpa_onnx.KeywordSpotter:
	""" The spotter, its model downloaded on the first call (18 MB, of which 5 MB are kept). """
	if not all((MODEL / name).exists() for name in FILES):
		download_model()
	keywords = MODEL / "keywords.txt"
	keywords.write_text("\n".join(pronunciation.replace("_", WORD_START) for pronunciation in PRONUNCIATIONS), encoding="utf-8")
	return sherpa_onnx.KeywordSpotter(
		tokens=str(MODEL / "tokens.txt"), encoder=str(MODEL / f"encoder-{CHECKPOINT}"), decoder=str(MODEL / f"decoder-{CHECKPOINT}"),
		joiner=str(MODEL / f"joiner-{CHECKPOINT}"), keywords_file=str(keywords), num_threads=1,
	)


def download_model() -> None:
	MODEL.mkdir(parents=True, exist_ok=True)
	with urllib.request.urlopen(MODEL_URL) as response, tarfile.open(fileobj=io.BytesIO(response.read()), mode="r:bz2") as archive:
		for member in archive.getmembers():
			name = Path(member.name).name
			if name in FILES and (file := archive.extractfile(member)):
				(MODEL / name).write_bytes(file.read())

