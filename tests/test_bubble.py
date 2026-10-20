""" The speech bubble's text, scrolled when it is long. """
# Imports
from itertools import pairwise

import numpy as np
from numpy.typing import NDArray
from PySide6.QtCore import QPointF
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from claudetan.overlay.bubble import FADE_CHARS, SCROLL_DELAY_S, SLICE_COLORS, TYPING_S, Bubble
from claudetan.report import Report, Slice


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



def test_a_report_shows_a_bar_and_a_colored_row_for_each_slice(app: QApplication) -> None:
	bubble = Bubble()
	slices = (Slice("Messages", "Messages", "6k", "60%", 0.6), Slice("Free space", "Free space", "4k", "40%", 0.4))
	bubble.say(Report("Context: 10k", slices), now=0.0)
	bubble.lay_out()
	html = bubble.document.toHtml()
	assert SLICE_COLORS["Messages"] in html
	assert SLICE_COLORS["Free space"] in html
	assert bubble.text == "Context: 10k\nMessages: 6k (60%)\nFree space: 4k (40%)"


def test_a_short_text_shows_at_once_and_a_long_one_within_the_typing_time(app: QApplication) -> None:
	short, long = Bubble(), Bubble()
	short.say("Yes?", now=0.0)
	long.say("a" * 300, now=0.0)
	short.type(0.3)
	long.type(TYPING_S / 2)
	assert short.revealed == len(short.text) + FADE_CHARS
	assert long.revealed < len(long.text)

	long.type(TYPING_S / 2)
	assert long.revealed >= len(long.text)


def test_a_link_in_the_text_is_found_under_the_point_it_was_drawn_at(app: QApplication) -> None:
	bubble = Bubble()
	bubble.say("Open https://claude.ai/code now", now=0.0)
	bubble.revealed = 1e9
	image = QImage(420, 200, QImage.Format.Format_ARGB32)
	painter = QPainter(image)
	bubble.paint(painter, now=1.0, bottom=150)
	painter.end()
	row = bubble.text_area.top() + 8
	assert bubble.link_at(QPointF(bubble.text_area.left() + 100, row)) == "https://claude.ai/code"
	assert bubble.link_at(QPointF(bubble.text_area.left() + 2, row)) == ""

