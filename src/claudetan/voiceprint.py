""" The owner's voice, recorded once by the setup: only sentences in that voice may wake her or ask her something. """
# Imports
import functools
import logging
import urllib.request
from pathlib import Path

import numpy as np
import sherpa_onnx as so

from claudetan.audio import RATE, Audio
from claudetan.config import APP_DATA

# Constants
VOICEPRINT: Path = APP_DATA / "voiceprint.npy"
""" The owner's voice embedding, of unit length. Deleting it lets anyone command her until the setup records it again. """
MODEL: Path = APP_DATA / "wespeaker_en_voxceleb_resnet34_LM.onnx"
""" WeSpeaker ResNet34 trained on VoxCeleb's many languages (26 MB), downloaded from the models sherpa-onnx publishes. """
MODEL_URL: str = f"https://huggingface.co/csukuangfj/speaker-embedding-models/resolve/main/{MODEL.name}"
LOG: logging.Logger = logging.getLogger("claudetan")


# Functions
def is_owner(audio: Audio, threshold: float) -> bool:
	""" Whether the owner said it, as a cosine similarity of at least `threshold` with the voiceprint, or anyone without one. """
	voiceprint = owner()
	if voiceprint is None:
		return True
	similarity = float(embed(audio) @ voiceprint)
	LOG.info("Voice similarity: %.2f", similarity)
	return similarity >= threshold


@functools.cache
def owner() -> np.ndarray[tuple[int], np.dtype[np.float32]] | None:
	return np.load(VOICEPRINT) if VOICEPRINT.exists() else None


def embed(audio: Audio) -> np.ndarray[tuple[int], np.dtype[np.float32]]:
	""" The voice of `audio`, at `RATE`, as a unit vector. """
	stream = extractor().create_stream()
	stream.accept_waveform(RATE, audio)
	stream.input_finished()
	vector = np.array(extractor().compute(stream), np.float32)
	return vector / np.linalg.norm(vector)


@functools.cache
def extractor() -> so.SpeakerEmbeddingExtractor:
	""" The embedding model on the CPU, downloaded on the first call. """
	if not MODEL.exists():
		partial = MODEL.with_suffix(".part")
		urllib.request.urlretrieve(MODEL_URL, partial)
		partial.replace(MODEL)
	return so.SpeakerEmbeddingExtractor(so.SpeakerEmbeddingExtractorConfig(model=str(MODEL)))

