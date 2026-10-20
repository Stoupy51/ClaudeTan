""" Claude-tan on screen: the sprite overlay with her speech bubble, the pill she shrinks to during long tasks, and her chimes.

A click on her or on the pill opens the Remote Control session, a long press on her lets you drag her somewhere else.
"""
# Imports
import math
import random
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
	QUrl,
	Signal,
)
from PySide6.QtGui import (
	QBrush,
	QColor,
	QConicalGradient,
	QDesktopServices,
	QGuiApplication,
	QHideEvent,
	QMouseEvent,
	QPainter,
	QPainterPath,
	QPaintEvent,
	QPen,
	QPixmap,
	QShowEvent,
	QWheelEvent,
)
from PySide6.QtWidgets import QWidget

from claudetan.config import ROOT
from claudetan.overlay.bubble import WIDTH as BUBBLE_WIDTH, Bubble
from claudetan.overlay.effects import ACCENT, Spark, burst, glow, mote, overshoot
from claudetan.report import Report
from claudetan.voice.speech import Vowels

# Constants
ASSETS: Path = ROOT / "assets" / "claude"
SPRITE_HEIGHT: int = 400
""" Display height of the sprites, which all share one canvas with her eyes on the same pixels. """
SPRITE_TOP: int = 24
FACE_Y: float = 0.49
""" Vertical position of the face center in the sprites, as a fraction of the sprite height. """
FACE: QRect = QRect(300, 160, 240, 240)
""" Square around her face on the sprite canvas, cropped for the pill and the tray icon. """
PILL_SIZE: int = 64
LONG_PRESS_MS: int = 200
CLICK_SLOP: int = 6
""" Pixels the cursor may travel during a press that still counts as a click. """
WHEEL_STEP: float = 40.0
""" Pixels of text one notch of the mouse wheel scrolls. """
READ_S: float = 3.0
""" How long the end of a text stays still under the wheel before she leaves. """
TALK_FRAMES: dict[str, tuple[str, ...]] = {
	"idle": ("idle_talk_open", "idle_talk_o", "idle_talk_wide"),
	"hello": ("hello_talk_open", "hello_talk_wide"),
}
""" Open mouths of the poses that can talk, one picked at random and held for a whole reply. """
MOUTHS: dict[str, str] = {"a": "wide", "i": "open", "u": "o", "e": "open", "o": "o"}
""" The open mouth of each vowel her voice says, `open` where a pose lacks it. Any other sound, such as a pause or "n", closes it. """
CELEBRATIONS: frozenset[str] = frozenset({"happy", "present", "thanks"})
""" Expressions she greets with a burst of sparks. """
FRAME_MS: int = 16
CROSSFADE_S: float = 0.18
POP_S: float = 0.45
BREATH_S: float = 3.8
""" Period of her breathing, a slight swell of the sprite from its bottom edge. """
MOTE_EVERY_S: float = 0.7
CHIME_RATE: int = 44100


# Classes
class Avatar(QWidget):
	clicked = Signal()
	closed = Signal()
	""" The cross of her bubble was clicked. """
	hidden = Signal()
	""" The dash of her bubble was clicked. """
	read = Signal()
	""" The text was scrolled to its end, left there for `READ_S`, and her voice is done. """

	def __init__(self, zoom: float = 1.0, text_zoom: float = 1.0) -> None:
		""" The overlay, with her drawn `zoom` times and her bubble `text_zoom` times their default size. """
		super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
		self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
		self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
		self.lay_out(zoom, text_zoom)
		self.expression = "idle"
		self.frame = "idle"
		self.bubble = Bubble()
		self.clock = QElapsedTimer()
		self.clock.start()
		self.speech: tuple[float, Vowels] | None = None
		""" When her voice started the line it is saying, and its vowels. """
		self.previous_frame = ""
		""" Frame fading out under `frame` for `CROSSFADE_S` after `changed_at`. """
		self.changed_at = -1.0
		self.popped_at = -1.0
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
		self.ticker = QTimer(self)
		self.ticker.setInterval(FRAME_MS)
		self.ticker.timeout.connect(self.tick)
		self.schedule_blink()

	def lay_out(self, zoom: float, text_zoom: float) -> None:
		self.zoom = zoom
		self.text_zoom = text_zoom
		# Pixmaps hold as many pixels as they cover once zoomed, so they stay sharp
		ratio = QGuiApplication.primaryScreen().devicePixelRatio() * zoom
		self.sprites: dict[str, QPixmap] = {}
		for path in ASSETS.glob("*.png"):
			pixmap = QPixmap(str(path)).scaledToHeight(round(SPRITE_HEIGHT * ratio), Qt.TransformationMode.SmoothTransformation)
			pixmap.setDevicePixelRatio(ratio)
			self.sprites[path.stem] = pixmap
		self.sprite_width = round(self.sprites["idle"].width() / ratio)
		# In her own coordinates, which `zoom` scales: the bubble, scaled apart, overlaps her by a third of her width
		self.sprite_left = max(0.0, text_zoom * BUBBLE_WIDTH / zoom - 0.3 * self.sprite_width)
		self.halo = glow(round(0.75 * self.sprite_width), round(0.7 * SPRITE_HEIGHT), ratio)
		self.resize(round(zoom * (self.sprite_left + self.sprite_width)), round(zoom * (SPRITE_TOP + SPRITE_HEIGHT)))

	def set_zoom(self, zoom: float, text_zoom: float) -> None:
		""" Lays her and her bubble out again, her bottom-right corner staying where she was dropped. """
		before = self.size()
		self.lay_out(zoom, text_zoom)
		saved = self.settings.value("pos")
		if isinstance(saved, QPoint):
			self.settings.setValue("pos", saved + QPoint(before.width() - self.width(), before.height() - self.height()))
		if self.isVisible():
			self.move(self.home())

	def set_expression(self, expression: str, *, talking: bool = False, bubble: str | Report = "") -> None:
		now = self.now()
		self.speech = None
		if expression != self.expression:
			self.previous_frame = self.frame
			self.changed_at = now
			if expression in CELEBRATIONS and self.isVisible():
				self.sparks += burst(self.face_center(), now, count=18)
		self.expression = expression
		if not talking or expression not in TALK_FRAMES:
			self.frame = expression
		elif self.frame not in TALK_FRAMES[expression]:
			self.frame = random.choice(TALK_FRAMES[expression])
		self.bubble.say(bubble, now)
		self.update()

	def speak(self, vowels: Vowels) -> None:
		""" Moves her mouth on the vowels of the line her voice starts saying, in a pose that can talk. """
		if self.expression not in TALK_FRAMES:
			self.set_expression("idle", bubble=self.bubble.report or self.bubble.text)
		self.speech = (self.now(), vowels)

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
		if self.frame == self.expression and blink in self.sprites:
			self.frame = blink
			self.update()
			QTimer.singleShot(130, self.open_eyes)
		self.schedule_blink()

	def open_eyes(self) -> None:
		if self.frame.endswith("_blink"):
			self.frame = self.expression
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
		self.bubble.type(now - self.last_tick)
		self.last_tick = now
		if self.speech:
			self.move_mouth(now - self.speech[0], self.speech[1])
		elif (since := self.bubble.read_since) is not None and now - since >= READ_S:
			self.bubble.read_since = None
			self.read.emit()
		if now >= self.next_mote:
			left, top = self.sprite_left + 0.2 * self.sprite_width, SPRITE_TOP + 0.15 * SPRITE_HEIGHT
			self.sparks.append(mote(QRectF(left, top, 0.6 * self.sprite_width, 0.6 * SPRITE_HEIGHT), now))
			self.next_mote = now + MOTE_EVERY_S
		self.sparks = [spark for spark in self.sparks if spark.alive(now)]
		self.update()

	def move_mouth(self, said: float, vowels: Vowels) -> None:
		""" Her mouth on the vowel said `said` seconds into the line, closed once the line is over. """
		vowel = next((vowel for at, vowel in reversed(vowels) if at <= said), "")
		if said >= vowels[-1][0]:
			self.speech = None
		shape = MOUTHS.get(vowel)
		mouth = f"{self.expression}_talk_{shape}"
		self.frame = (mouth if mouth in self.sprites else f"{self.expression}_talk_open") if shape else self.expression

	@override
	def paintEvent(self, event: QPaintEvent) -> None:
		painter = QPainter(self)
		painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
		painter.save()
		painter.scale(self.zoom, self.zoom)
		now = self.now()
		breath = math.sin(2 * math.pi * now / BREATH_S)
		painter.setOpacity(0.8 + 0.2 * breath)
		center = self.face_center() + QPointF(0, 0.1 * SPRITE_HEIGHT)
		painter.drawPixmap(center - QPointF(self.halo.width(), self.halo.height()) / (2 * self.halo.devicePixelRatio()), self.halo)
		painter.setOpacity(1)
		self.paint_sprite(painter, now, breath)
		for spark in self.sparks:
			spark.paint(painter, now)
		painter.restore()

		if self.bubble.text:
			painter.scale(self.text_zoom, self.text_zoom)
			# Growing upward from just above her hands keeps the finger of `thinking` and the wave of `hello` in sight
			self.bubble.paint(painter, now, bottom=self.zoom * (SPRITE_TOP + FACE_Y * SPRITE_HEIGHT - 26) / self.text_zoom)

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

	@override
	def wheelEvent(self, event: QWheelEvent) -> None:
		self.bubble.scroll(-event.angleDelta().y() / 120 * WHEEL_STEP / self.text_zoom, self.now())

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
			point = event.position() / self.text_zoom
			button = next((name for name, box in self.bubble.buttons.items() if box.contains(point)), None)
			signals = {"close": self.closed, "hide": self.hidden}
			if self.bubble.text and (link := self.bubble.link_at(point)):
				QDesktopServices.openUrl(QUrl(link))
			else:
				(signals[button] if button and self.bubble.text else self.clicked).emit()
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

	def __init__(self, zoom: float = 1.0) -> None:
		""" The pill, laid out at its default size and drawn `zoom` times larger. """
		super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
		self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
		self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
		self.set_zoom(zoom)
		self.angle = 0
		self.spin = QTimer(self)
		self.spin.setInterval(30)
		self.spin.timeout.connect(self.turn)

	def set_zoom(self, zoom: float) -> None:
		self.zoom = zoom
		self.resize(round(PILL_SIZE * zoom), round(PILL_SIZE * zoom))
		self.face = face(round(PILL_SIZE * zoom))

	def show_at(self, corner: QPoint) -> None:
		""" Shows the pill with its bottom-right corner on `corner`. """
		self.move(corner - QPoint(self.width(), self.height()))
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
		painter.scale(self.zoom, self.zoom)
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


def chime(*notes: float) -> None:
	""" Plays the bell of the notes without blocking. """
	sd.play(bell(*notes), CHIME_RATE)


def bell(*notes: float) -> np.ndarray[tuple[int], np.dtype[np.float32]]:
	""" A short bell arpeggio of the given frequencies in Hz, sampled at `CHIME_RATE`. """
	t = np.arange(int(0.4 * CHIME_RATE)) / CHIME_RATE
	step = int(0.08 * CHIME_RATE)
	wave = np.zeros(step * (len(notes) - 1) + len(t), np.float32)
	for i, note in enumerate(notes):
		wave[i * step:i * step + len(t)] += np.sin(2 * np.pi * note * t) * np.exp(-8 * t)
	return 0.15 * wave

