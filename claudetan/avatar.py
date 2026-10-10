""" Claude-tan on screen: the sprite overlay with her speech bubble, the pill she shrinks to during long tasks, and her chimes.

A click on her or on the pill opens the Remote Control session, a long press on her lets you drag her somewhere else.
"""
# Imports
import html
import math
import random
import re
from pathlib import Path
from typing import override

import numpy as np
import sounddevice as sd
from PySide6.QtCore import (
	QEasingCurve,
	QElapsedTimer,
	QParallelAnimationGroup,
	QPoint,
	QPointF,
	QPropertyAnimation,
	QRect,
	QRectF,
	QSettings,
	Qt,
	QTimer,
	Signal,
)
from PySide6.QtGui import (
	QBrush,
	QColor,
	QConicalGradient,
	QFont,
	QGuiApplication,
	QHideEvent,
	QLinearGradient,
	QMouseEvent,
	QPainter,
	QPainterPath,
	QPaintEvent,
	QPen,
	QPixmap,
	QShowEvent,
	QTextDocument,
)
from PySide6.QtWidgets import QWidget

from claudetan.config import ROOT
from claudetan.effects import Spark, burst, glow, mote

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
CELEBRATIONS: frozenset[str] = frozenset({"happy", "present", "thanks"})
""" Expressions she greets with a burst of sparks. """
FRAME_MS: int = 16
CROSSFADE_S: float = 0.18
POP_S: float = 0.45
BUBBLE_POP_S: float = 0.25
BREATH_S: float = 3.8
""" Period of her breathing, a slight swell of the sprite from its bottom edge. """
TYPING_SPEED: float = 70.0
""" Characters per second the bubble's text appears at. """
MOTE_EVERY_S: float = 0.7
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
		self.halo = glow(round(0.75 * self.sprite_width), round(0.7 * SPRITE_HEIGHT), ratio)
		self.clock = QElapsedTimer()
		self.clock.start()
		self.previous_frame = ""
		""" Frame fading out under `frame` for `CROSSFADE_S` after `changed_at`. """
		self.changed_at = -1.0
		self.popped_at = -1.0
		self.bubble_at = -1.0
		self.revealed = 0.0
		""" How many characters of the bubble are typed so far. """
		self.document = QTextDocument()
		""" The bubble's text laid out, kept between frames while `typed` is unchanged. """
		self.document.setDefaultFont(QFont("Segoe UI", 11))
		self.document.setDocumentMargin(0)
		self.document.setTextWidth(BUBBLE_WIDTH - 48)
		self.typed = ("", -1)
		self.sparks: list[Spark] = []
		self.next_mote = 0.0
		self.last_tick = 0.0
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
		self.ticker = QTimer(self)
		self.ticker.setInterval(FRAME_MS)
		self.ticker.timeout.connect(self.tick)
		self.schedule_blink()

	def set_expression(self, expression: str, *, talking: bool = False, bubble: str = "") -> None:
		now = self.now()
		if expression != self.expression:
			self.previous_frame = self.frame
			self.changed_at = now
			if expression in CELEBRATIONS and self.isVisible():
				self.sparks += burst(self.face_center(), now, count=18)
		self.expression = expression
		self.frame = expression
		text = shorten(bubble)
		# A reply streamed in pieces keeps typing where it was, any other text starts over
		if not (self.bubble and text.startswith(self.bubble)):
			self.revealed = 0.0
			self.bubble_at = now
		self.bubble = text
		if talking and expression in TALK_FRAMES:
			self.mouth.start()
		else:
			self.mouth.stop()
		self.update()

	def pop_in(self) -> None:
		if not self.isVisible():
			self.setWindowOpacity(0)
			self.move(self.home() + QPoint(0, 40))
			self.popped_at = self.now()
			self.sparks = burst(self.face_center(), self.popped_at, count=14)
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
		blink = f"{self.expression}_blink"
		if self.frame == self.expression and blink in self.sprites and not self.mouth.isActive():
			self.frame = blink
			self.update()
			QTimer.singleShot(130, self.open_eyes)
		self.schedule_blink()

	def open_eyes(self) -> None:
		if self.frame.endswith("_blink"):
			self.frame = self.expression
			self.update()

	def flap(self) -> None:
		self.frame = random.choice([f for f in TALK_FRAMES[self.expression] if f != self.frame])
		self.update()

	def now(self) -> float:
		return self.clock.elapsed() / 1000

	def face_center(self) -> QPointF:
		return QPointF(self.sprite_left + self.sprite_width / 2, SPRITE_TOP + FACE_Y * SPRITE_HEIGHT)

	@override
	def showEvent(self, event: QShowEvent) -> None:
		self.last_tick = self.now()
		self.ticker.start()

	@override
	def hideEvent(self, event: QHideEvent) -> None:
		self.ticker.stop()
		self.sparks.clear()

	def tick(self) -> None:
		now = self.now()
		self.revealed = min(len(self.bubble), self.revealed + TYPING_SPEED * (now - self.last_tick))
		self.last_tick = now
		if now >= self.next_mote:
			left, top = self.sprite_left + 0.2 * self.sprite_width, SPRITE_TOP + 0.15 * SPRITE_HEIGHT
			self.sparks.append(mote(QRectF(left, top, 0.6 * self.sprite_width, 0.6 * SPRITE_HEIGHT), now))
			self.next_mote = now + MOTE_EVERY_S
		self.sparks = [spark for spark in self.sparks if spark.alive(now)]
		self.update()

	@override
	def paintEvent(self, event: QPaintEvent) -> None:
		painter = QPainter(self)
		painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
		now = self.now()
		breath = math.sin(2 * math.pi * now / BREATH_S)
		painter.setOpacity(0.8 + 0.2 * breath)
		center = self.face_center() + QPointF(0, 0.1 * SPRITE_HEIGHT)
		painter.drawPixmap(center - QPointF(self.halo.width(), self.halo.height()) / (2 * self.halo.devicePixelRatio()), self.halo)
		painter.setOpacity(1)
		self.paint_sprite(painter, now, breath)
		for spark in self.sparks:
			spark.paint(painter, now)
		if self.bubble:
			self.paint_bubble(painter, now)

	def paint_sprite(self, painter: QPainter, now: float, breath: float) -> None:
		""" The sprite popping up from its bottom edge, breathing, and fading in over the previous frame after a change. """
		scale = (0.92 + 0.08 * overshoot(min(1.0, (now - self.popped_at) / POP_S))) * (1 + 0.006 * breath)
		anchor = QPointF(self.sprite_left + self.sprite_width / 2, SPRITE_TOP + SPRITE_HEIGHT)
		painter.save()
		painter.translate(anchor)
		painter.scale(scale, scale)
		painter.translate(-anchor)
		top_left = QPointF(self.sprite_left, SPRITE_TOP)
		fade = min(1.0, (now - self.changed_at) / CROSSFADE_S)
		if fade < 1 and self.previous_frame:
			painter.setOpacity(1 - fade * fade)
			painter.drawPixmap(top_left, self.sprites[self.previous_frame])
			painter.setOpacity(fade)
		painter.drawPixmap(top_left, self.sprites[self.frame])
		painter.restore()

	def paint_bubble(self, painter: QPainter, now: float) -> None:
		""" Speech bubble with her name tag, the text typed in place so that words never jump to the next line. """
		shown = round(self.revealed)
		if self.typed != (self.bubble, shown):
			self.typed = (self.bubble, shown)
			self.document.setHtml(
				f'<span style="color: #30221c">{html.escape(self.bubble[:shown])}</span>'
				f'<span style="color: rgba(0, 0, 0, 0)">{html.escape(self.bubble[shown:])}</span>',
			)
		height = self.document.size().height()
		# Growing upward from just above her hands keeps the finger of `point` and the wave of `hello` in sight
		bottom = SPRITE_TOP + FACE_Y * SPRITE_HEIGHT - 26
		box = QRectF(8, max(18.0, bottom - height - 26), BUBBLE_WIDTH - 20, height + 26)
		shape = QPainterPath()
		shape.addRoundedRect(box, 14, 14)
		tail = QPainterPath()
		tail.moveTo(box.right() - 4, box.bottom() - 34)
		tail.lineTo(box.right() + 18, box.bottom() - 22)
		tail.lineTo(box.right() - 4, box.bottom() - 18)
		shape = shape.united(tail)

		appeared = min(1.0, (now - self.bubble_at) / BUBBLE_POP_S)
		tip = QPointF(box.right() + 18, box.bottom() - 22)
		painter.save()
		painter.setOpacity(min(1.0, 3 * appeared))
		painter.translate(tip)
		painter.scale(0.85 + 0.15 * overshoot(appeared), 0.85 + 0.15 * overshoot(appeared))
		painter.translate(-tip)
		painter.setPen(Qt.PenStyle.NoPen)
		for offset, alpha in ((5.0, 10), (3.0, 14), (1.5, 18)):
			painter.setBrush(QColor(70, 30, 15, alpha))
			painter.drawPath(shape.translated(0, offset))
		fill = QLinearGradient(box.topLeft(), box.bottomLeft())
		fill.setColorAt(0, QColor(255, 253, 249, 250))
		fill.setColorAt(1, QColor(255, 240, 230, 250))
		painter.setPen(QPen(ACCENT, 1.5))
		painter.setBrush(fill)
		painter.drawPath(shape)
		self.paint_name_tag(painter, box)
		painter.translate(box.left() + 14, box.top() + 14)
		self.document.drawContents(painter)
		painter.restore()

	def paint_name_tag(self, painter: QPainter, box: QRectF) -> None:
		painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
		tag = QRectF(box.left() + 12, box.top() - 10, painter.fontMetrics().horizontalAdvance("Claude-tan") + 18, 19)
		fill = QLinearGradient(tag.topLeft(), tag.topRight())
		fill.setColorAt(0, ACCENT)
		fill.setColorAt(1, QColor(240, 150, 100))
		painter.setPen(Qt.PenStyle.NoPen)
		painter.setBrush(fill)
		painter.drawRoundedRect(tag, 9.5, 9.5)
		painter.setPen(QColor(255, 255, 255))
		painter.drawText(tag, Qt.AlignmentFlag.AlignCenter, "Claude-tan")

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
		# A comet: bright at the head of the arc, fading out along its tail
		sweep = QConicalGradient(ring.center(), self.angle)
		sweep.setColorAt(0, QColor(226, 96, 58))
		sweep.setColorAt(0.12, ACCENT)
		sweep.setColorAt(0.31, QColor(ACCENT.red(), ACCENT.green(), ACCENT.blue(), 0))
		painter.setPen(QPen(QBrush(sweep), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
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


def overshoot(t: float) -> float:
	""" Ease-out that passes its target by about 10% before settling, for things that pop up.

	>>> round(overshoot(0.0), 6), overshoot(1.0), round(max(overshoot(i / 100) for i in range(101)), 2)
	(0.0, 1.0, 1.1)
	"""
	return 1 + 2.70158 * (t - 1) ** 3 + 1.70158 * (t - 1) ** 2


def chime(*notes: float) -> None:
	""" A short bell arpeggio of the given frequencies in Hz, played without blocking. """
	t = np.arange(int(0.4 * CHIME_RATE)) / CHIME_RATE
	step = int(0.08 * CHIME_RATE)
	wave = np.zeros(step * (len(notes) - 1) + len(t), np.float32)
	for i, note in enumerate(notes):
		wave[i * step:i * step + len(t)] += np.sin(2 * np.pi * note * t) * np.exp(-8 * t)
	sd.play(0.15 * wave, CHIME_RATE)

