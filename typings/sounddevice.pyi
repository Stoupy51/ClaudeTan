from collections.abc import Callable
from types import TracebackType
from typing import Self

import numpy as np

class CallbackFlags: ...

class InputStream:
	def __init__(
		self,
		samplerate: float | None = None,
		blocksize: int | None = None,
		device: int | str | None = None,
		channels: int | None = None,
		dtype: str | None = None,
		callback: Callable[[np.ndarray[tuple[int, int], np.dtype[np.float32]], int, object, CallbackFlags], None] | None = None,
	) -> None: ...
	def __enter__(self) -> Self: ...
	def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None: ...

def play(data: np.ndarray[tuple[int], np.dtype[np.float32]], samplerate: float | None = None) -> None: ...
