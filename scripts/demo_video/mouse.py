""" The mouse of the demo video: where its pointer goes and when its button is down, on the video's clock. """
# Imports
from dataclasses import dataclass

from PySide6.QtCore import QPointF


# Classes
@dataclass(frozen=True)
class Move:
	""" The pointer going to `to` in `seconds`, its button down all the way when `held`. """
	to: QPointF
	seconds: float
	held: bool


@dataclass(frozen=True)
class Gesture:
	""" Moves made one after the other from `origin`, starting at the second `start` of the video. """
	start: float
	origin: QPointF
	moves: tuple[Move, ...]

	def at(self, now: float) -> tuple[QPointF, bool]:
		""" Where the pointer is at `now`, easing in and out of each move, and whether its button is down. """
		start, origin = self.start, self.origin
		for move in self.moves:
			if now < start + move.seconds:
				progress = (now - start) / move.seconds
				return origin + (move.to - origin) * (progress * progress * (3 - 2 * progress)), move.held
			start, origin = start + move.seconds, move.to
		return origin, False

	def end(self) -> float:
		return self.start + sum(move.seconds for move in self.moves)

