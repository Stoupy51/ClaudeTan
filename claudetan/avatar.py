""" Claude-tan on screen: the sprite overlay with her speech bubble, the pill she shrinks to during long tasks, and her chimes.

A click on her or on the pill opens the Remote Control session, a long press on her lets you drag her somewhere else.
"""
# Imports
import random
import re
from pathlib import Path
from typing import override

import numpy as np
import sounddevice as sd
from PySide6.QtCore import (
	QEasingCurve,
	QParallelAnimationGroup,
	QPoint,
	QPropertyAnimation,
	QRect,
	QRectF,
	QSettings,
	Qt,
	QTimer,
	Signal,
)
from PySide6.QtGui import QColor, QFont, QGuiApplication, QHideEvent, QMouseEvent, QPainter, QPainterPath, QPaintEvent, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from claudetan.config import ROOT

# Constants
ASSETS: Path = ROOT / "assets" / "claude"
SPRITE_HEIGHT: int = 400
""" Display height of the sprites, which all share one canvas with her eyes on the same pixels. """
BUBBLE_WIDTH: int = 250
BUBBLE_CHARS: int = 220
""" Longest text the bubble shows, the full reply staying readable in the session. """
SPRITE_TOP: int = 24
FACE_Y: float = 0.49
""" Vertical position of the face center in the sprites, as a fraction of the sprite height. """
FACE: QRect = QRect(300, 160, 240, 240)
""" Square around her face on the sprite canvas, cropped for the pill and the tray icon. """
PILL_SIZE: int = 64
ACCENT: QColor = QColor(217, 119, 87)
LONG_PRESS_MS: int = 200
CLICK_SLOP: int = 6
""" Pixels the cursor may travel during a press that still counts as a click. """
TALK_FRAMES: dict[str, tuple[str, ...]] = {
	"idle": ("idle", "idle_talk_open", "idle_talk_o", "idle_talk_wide"),
	"hello": ("hello", "hello_talk_open", "hello_talk_o", "hello_talk_wide"),
}
""" Mouth frames of the poses that can talk. """
CHIME_RATE: int = 44100


# Classes
class Avatar(QWidget):
	clicked = Signal()

	def __init__(self) -> None:
		super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
		self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
		self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
		ratio = QGuiApplication.primaryScreen().devicePixelRatio()
		self.sprites: dict[str, QPixmap] = {}
		for path in ASSETS.glob("*.png"):
			pixmap = QPixmap(str(path)).scaledToHeight(round(SPRITE_HEIGHT * ratio), Qt.TransformationMode.SmoothTransformation)
			pixmap.setDevicePixelRatio(ratio)
			self.sprites[path.stem] = pixmap
		self.sprite_width = round(self.sprites["idle"].width() / ratio)
		self.sprite_left = BUBBLE_WIDTH - round(0.3 * self.sprite_width)
		self.resize(self.sprite_left + self.sprite_width, SPRITE_TOP + SPRITE_HEIGHT)

		self.expression = "idle"
		self.frame = "idle"
		self.bubble = ""
		self.press_offset: QPoint | None = None
		self.press_origin = QPoint()
		self.dragging = False
		self.settings = QSettings("ClaudeTan", "overlay")

		self.motion = QPropertyAnimation(self, b"pos")
		self.fade = QPropertyAnimation(self, b"windowOpacity")
		self.slide = QParallelAnimationGroup(self)
		for animation in (self.motion, self.fade):
			animation.setDuration(260)
			animation.setEasingCurve(QEasingCurve.Type.OutCubic)
			self.slide.addAnimation(animation)
		self.slide.finished.connect(self.hide_if_faded)

		self.long_press = QTimer(self)
		self.long_press.setSingleShot(True)
		self.long_press.setInterval(LONG_PRESS_MS)
		self.long_press.timeout.connect(self.start_drag)
		self.blink = QTimer(self)
		self.blink.setSingleShot(True)
		self.blink.timeout.connect(self.close_eyes)
		self.mouth = QTimer(self)
		self.mouth.setInterval(110)
		self.mouth.timeout.connect(self.flap)
		self.schedule_blink()

	def set_expression(self, expression: str, *, talking: bool = False, bubble: str = "") -> None:
		self.expression = expression
		self.frame = expression
		self.bubble = shorten(bubble)
		if talking and expression in TALK_FRAMES:
			self.mouth.start()
		else:
			self.mouth.stop()
		self.update()

	def pop_in(self) -> None:
		if not self.isVisible():
			self.setWindowOpacity(0)
			self.move(self.home() + QPoint(0, 40))
			self.show()
		self.slide_to(self.home(), 1.0)

	def pop_out(self) -> None:
		if self.isVisible():
			self.slide_to(self.home() + QPoint(0, 40), 0.0)

	def home(self) -> QPoint:
		""" Where she stands: where she was last dropped while that screen is plugged in, else the main screen's bottom-right corner.

		The fallback is never saved, so she goes back to the other screen as soon as it returns.
		"""
		saved = self.settings.value("pos")
		if isinstance(saved, QPoint) and QGuiApplication.screenAt(saved + self.rect().center()):
			return saved
		area = QGuiApplication.primaryScreen().availableGeometry()
		return QPoint(area.right() - self.width(), area.bottom() - self.height())

	def slide_to(self, position: QPoint, opacity: float) -> None:
		self.slide.stop()
		self.motion.setEndValue(position)
		self.fade.setEndValue(opacity)
		self.slide.start()

	def hide_if_faded(self) -> None:
		if self.fade.endValue() == 0.0:
			self.hide()

	def schedule_blink(self) -> None:
		self.blink.start(random.randint(2500, 6000))

	def close_eyes(self) -> None:
		if self.frame == "idle" and not self.mouth.isActive():
			self.frame = "idle_blink"
			self.update()
			QTimer.singleShot(130, self.open_eyes)
		self.schedule_blink()

	def open_eyes(self) -> None:
		if self.frame == "idle_blink":
			self.frame = "idle"
			self.update()

	def flap(self) -> None:
		self.frame = random.choice([f for f in TALK_FRAMES[self.expression] if f != self.frame])
		self.update()

	@override
	def paintEvent(self, event: QPaintEvent) -> None:
		painter = QPainter(self)
		painter.setRenderHint(QPainter.RenderHint.Antialiasing)
		painter.drawPixmap(QPoint(self.sprite_left, SPRITE_TOP), self.sprites[self.frame])
		if self.bubble:
			self.paint_bubble(painter)

	def paint_bubble(self, painter: QPainter) -> None:
		painter.setFont(QFont("Segoe UI", 11))
		text = painter.boundingRect(QRectF(0, 0, BUBBLE_WIDTH - 48, 400), Qt.TextFlag.TextWordWrap, self.bubble)
		# Growing upward from just above her hands keeps the finger of `point` and the wave of `hello` in sight
		bottom = SPRITE_TOP + FACE_Y * SPRITE_HEIGHT - 26
		box = QRectF(8, max(4.0, bottom - text.height() - 24), BUBBLE_WIDTH - 20, text.height() + 24)
		path = QPainterPath()
		path.addRoundedRect(box, 14, 14)
		tail = QPainterPath()
		tail.moveTo(box.right() - 4, box.bottom() - 34)
		tail.lineTo(box.right() + 18, box.bottom() - 22)
		tail.lineTo(box.right() - 4, box.bottom() - 18)
		painter.setPen(ACCENT)
		painter.setBrush(QColor(255, 250, 244, 240))
		painter.drawPath(path.united(tail))
		painter.setPen(QColor(40, 30, 25))
		painter.drawText(box.adjusted(14, 12, -14, -12), Qt.TextFlag.TextWordWrap, self.bubble)

	@override
	def mousePressEvent(self, event: QMouseEvent) -> None:
		self.press_origin = event.globalPosition().toPoint()
		self.press_offset = self.press_origin - self.pos()
		self.long_press.start()

	@override
	def mouseMoveEvent(self, event: QMouseEvent) -> None:
		cursor = event.globalPosition().toPoint()
		if self.dragging and self.press_offset is not None:
			self.move(cursor - self.press_offset)
		elif self.long_press.isActive() and (cursor - self.press_origin).manhattanLength() > CLICK_SLOP:
			self.long_press.stop()

	@override
	def mouseReleaseEvent(self, event: QMouseEvent) -> None:
		if self.long_press.isActive():
			self.long_press.stop()
			self.clicked.emit()
		elif self.dragging:
			self.dragging = False
			self.unsetCursor()
			self.settings.setValue("pos", self.pos())
		self.press_offset = None

	def start_drag(self) -> None:
		self.dragging = True
		self.setCursor(Qt.CursorShape.ClosedHandCursor)


class Pill(QWidget):
	""" Her face in a disc ringed by a spinning arc, shown in her place while a long task runs. """
	clicked = Signal()

	def __init__(self) -> None:
		super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
		self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
		self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
		self.resize(PILL_SIZE, PILL_SIZE)
		self.face = face(PILL_SIZE)
		self.angle = 0
		self.spin = QTimer(self)
		self.spin.setInterval(30)
		self.spin.timeout.connect(self.turn)

	def show_at(self, corner: QPoint) -> None:
		""" Shows the pill with its bottom-right corner on `corner`. """
		self.move(corner - QPoint(PILL_SIZE, PILL_SIZE))
		self.show()
		self.spin.start()

	def turn(self) -> None:
		self.angle = (self.angle - 8) % 360
		self.update()

	@override
	def hideEvent(self, event: QHideEvent) -> None:
		self.spin.stop()

	@override
	def paintEvent(self, event: QPaintEvent) -> None:
		painter = QPainter(self)
		painter.setRenderHint(QPainter.RenderHint.Antialiasing)
		ring = QRectF(4, 4, PILL_SIZE - 8, PILL_SIZE - 8)
		disc = QPainterPath()
		disc.addEllipse(ring)
		painter.setClipPath(disc)
		painter.drawPixmap(ring.toRect(), self.face)
		painter.setClipping(False)
		painter.setPen(QPen(QColor(255, 250, 244), 4))
		painter.drawEllipse(ring)
		painter.setPen(QPen(ACCENT, 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
		painter.drawArc(ring, self.angle * 16, 110 * 16)

	@override
	def mouseReleaseEvent(self, event: QMouseEvent) -> None:
		self.clicked.emit()


# Functions
def face(size: int) -> QPixmap:
	""" Her face cropped from `idle`, `size` device-independent pixels wide. """
	ratio = QGuiApplication.primaryScreen().devicePixelRatio()
	pixels = round(size * ratio)
	cropped = QPixmap(str(ASSETS / "idle.png")).copy(FACE)
	pixmap = cropped.scaled(pixels, pixels, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
	pixmap.setDevicePixelRatio(ratio)
	return pixmap


def shorten(text: str) -> str:
	""" The text as the bubble shows it: Markdown marks dropped, whitespace collapsed, cut at a word past `BUBBLE_CHARS`.

	>>> shorten("**Done**: edited `app.py`.\\n\\n- one\\n- two")
	'Done: edited app.py. one two'
	>>> shorten("word " * 100)[-12:]
	'word word...'
	"""
	plain = " ".join(re.sub(r"[*`#]|^\s*[-+] ", "", text, flags=re.MULTILINE).split())
	return plain if len(plain) <= BUBBLE_CHARS else plain[:BUBBLE_CHARS].rsplit(" ", 1)[0] + "..."


def chime(*notes: float) -> None:
	""" A short bell arpeggio of the given frequencies in Hz, played without blocking. """
	t = np.arange(int(0.4 * CHIME_RATE)) / CHIME_RATE
	step = int(0.08 * CHIME_RATE)
	wave = np.zeros(step * (len(notes) - 1) + len(t), np.float32)
	for i, note in enumerate(notes):
		wave[i * step:i * step + len(t)] += np.sin(2 * np.pi * note * t) * np.exp(-8 * t)
	sd.play(0.15 * wave, CHIME_RATE)

