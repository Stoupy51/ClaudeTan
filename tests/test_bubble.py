""" The speech bubble's text, scrolled when it is long. """
# Imports
from itertools import pairwise

import numpy as np
from numpy.typing import NDArray
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from claudetan.overlay.bubble import SCROLL_DELAY_S, Bubble


# Functions
def test_a_long_text_moves_a_little_on_every_frame_instead_of_jumping_a_pixel_at_a_time(app: QApplication) -> None:
	bubble = Bubble()
	bubble.say("Je préfère ne pas enquêter sur cette personne. " * 12, now=0.0)
	bubble.revealed = 1e9

	def frame(now: float) -> NDArray[np.int_]:
		image = QImage(300, 260, QImage.Format.Format_ARGB32)
		image.fill(0xFFFFFFFF)
		painter = QPainter(image)
		painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
		bubble.paint(painter, now, bottom=250)
		painter.end()
		pixels = np.frombuffer(image.constBits(), np.uint8).reshape(260, image.bytesPerLine())
		return pixels[110:230].astype(np.int_)

	# 4 ms of scrolling is a twentieth of a pixel: text drawn at whole pixels stays frozen for several frames, then jumps
	start = SCROLL_DELAY_S + 1.0
	frames = [frame(start + step * 0.004) for step in range(10)]
	assert min(np.abs(after - before).sum() for before, after in pairwise(frames)) > 1000

