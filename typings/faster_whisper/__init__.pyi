from collections.abc import Iterable

import numpy as np

class Segment:
	start: float
	end: float
	text: str

class TranscriptionInfo:
	language: str
	language_probability: float

class WhisperModel:
	def __init__(self, model_size_or_path: str, device: str = "auto", compute_type: str = "default") -> None: ...
	def transcribe(
		self,
		audio: np.ndarray[tuple[int], np.dtype[np.float32]],
		language: str | None = None,
		beam_size: int = 5,
		condition_on_previous_text: bool = True,
	) -> tuple[Iterable[Segment], TranscriptionInfo]: ...
