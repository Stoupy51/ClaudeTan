""" The menu of her tray icon, on the warm paper of her bubble, which slides out by the icon and fades away once a row is picked. """
# Imports
import ctypes
from collections.abc import Callable
from dataclasses import dataclass
from typing import override

from PySide6.QtCore import (
	QAbstractAnimation,
	QEasingCurve,
	QEvent,
	QPoint,
	QPointF,
	QRect,
	QRectF,
	Qt,
	QTimer,
	QVariantAnimation,
	Signal,
)
from PySide6.QtGui import (
	QCloseEvent,
	QColor,
	QCursor,
	QFont,
	QGuiApplication,
	QHideEvent,
	QKeyEvent,
	QLinearGradient,
	QMouseEvent,
	QPainter,
	QPainterPath,
	QPaintEvent,
	QPen,
	QWheelEvent,
)
from PySide6.QtWidgets import QWidget

from claudetan.overlay.bubble import BUTTON_RADIUS, GOLD, INK, paint_button, paint_paper, paint_shadow, paint_tag, paint_twinkles
from claudetan.overlay.effects import ACCENT

# Constants
WIDTH: float = 252.0
MARGIN: float = 22.0
""" Room around the paper for its shadow, its name tag and its slide. """
TOP: float = 18.0
""" Room under the name tag straddling the top edge. """
ROW: float = 34.0
GAP: float = 11.0
""" Height between two sections, a thin line running across it. """
SHOW_MS: int = 170
SLIDE_PX: float = 10.0
""" How far the menu slides in from the icon it opens by. """
HOVER_MS: int = 120
ICONS: str = "Segoe MDL2 Assets"
MUTED: QColor = QColor(INK.red(), INK.green(), INK.blue(), 150)
TRACK_LEFT: float = 92.0
""" Where the slider's track starts, from the left of its row, past its icon and label. """
VOLUME_STEP: float = 0.05
""" Share of the slider one notch of the mouse wheel moves. """
WATCH_MS: int = 30
""" How often the mouse buttons are read while the menu is up, to close it on a click anywhere else. """
MOUSE_BUTTONS: tuple[int, ...] = (0x01, 0x02, 0x04)
""" The virtual keys of the left, right and middle mouse buttons. """


# Classes
@dataclass(frozen=True)
class Entry:
	""" A row that does something, the menu closing as it does. """
	label: str
	glyph: str
	""" Its icon, a character of the Segoe MDL2 Assets font. """
	run: Callable[[], None]


@dataclass
class Slider:
	""" A row with a slider, whose `value`, from 0 to 1 by hundredths, the menu moves as it is dragged. """
	label: str
	glyph: str
	value: float
	changed: Callable[[float], None]


@dataclass
class Switch:
	""" A row with a switch, which the menu flips on a click. """
	label: str
	glyph: str
	on: bool
	toggled: Callable[[bool], None]


type Row = Entry | Slider | Switch


class Menu(QWidget):
	""" A window of rows in sections, above her own, which closes on its cross, on Escape, and on a click anywhere else.

	It is no Qt popup: Qt closes a popup when the app loses the focus, which an app opened from its tray icon never had.
	"""
	closed = Signal()
	""" The menu faded out. """

	def __init__(self, sections: list[list[Row]]) -> None:
		flags = Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
		super().__init__(None, flags | Qt.WindowType.NoDropShadowWindowHint)
		self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
		self.setMouseTracking(True)
		self.rows: list[tuple[Row, QRectF]] = []
		self.lines: list[float] = []
		""" Heights of the lines between sections. """
		y = MARGIN + TOP
		for index, section in enumerate(sections):
			if index:
				self.lines.append(y + GAP / 2)
				y += GAP
			for row in section:
				self.rows.append((row, QRectF(MARGIN + 6, y, WIDTH - 12, ROW)))
				y += ROW
		self.box = QRectF(MARGIN, MARGIN, WIDTH, y + 8 - MARGIN)
		self.resize(round(WIDTH + 2 * MARGIN), round(self.box.bottom() + MARGIN))
		self.cross = QPointF(self.box.right() - 6, self.box.top() + 2)
		""" The center of its close button, straddling the top edge as her bubble's does. """
		self.rise = 1.0
		""" Which way the menu slides in: 1 up out of an icon below it, -1 down out of one above it. """
		self.hovered: int | None = None
		self.sliding: tuple[Slider, QRectF] | None = None
		""" The slider being dragged, with its row. """
		self.highlight = QRectF()
		""" Where the hover's tint is drawn, gliding from row to row, empty while no row is hovered. """
		self.flipped: Switch | None = None
		self.pressed = False
		""" Whether the button went down on the menu, so that the release of the right click that opened it picks nothing. """
		self.mouse_was_down = False
		self.watch = QTimer(self, interval=WATCH_MS)
		self.watch.timeout.connect(self.watch_mouse)

		self.appear = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=SHOW_MS)
		self.appear.setEasingCurve(QEasingCurve.Type.OutCubic)
		self.appear.valueChanged.connect(self.update)
		self.appear.finished.connect(self.hide_if_faded)
		self.glide = QVariantAnimation(self, duration=HOVER_MS)
		self.glide.setEasingCurve(QEasingCurve.Type.OutCubic)
		self.glide.valueChanged.connect(self.on_glide)
		self.flip = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=HOVER_MS)
		""" The knob of `flipped` sliding to its other side. """
		self.flip.setEasingCurve(QEasingCurve.Type.OutCubic)
		self.flip.valueChanged.connect(self.update)

	def toggle_by(self, anchor: QRect) -> None:
		""" Slides the menu out of `anchor`, the icon's place on the screen, above it or below it when the top is too close.

		The menu closes instead while it is up, as the click on the icon that opened it closes it again.
		"""
		if self.isVisible():
			self.close()
			return
		area = (QGuiApplication.screenAt(anchor.center()) or QGuiApplication.primaryScreen()).availableGeometry()
		self.move(self.place(anchor, area))
		self.show()
		self.raise_()
		self.activateWindow()
		self.mouse_was_down = mouse_down()
		self.watch.start()
		self.appear.setDirection(QAbstractAnimation.Direction.Forward)
		if self.appear.state() != QAbstractAnimation.State.Running:
			self.appear.start()

	def place(self, anchor: QRect, area: QRect) -> QPoint:
		""" Where the menu goes by `anchor`, its paper kept inside `area`, the free part of a screen. It sets `rise`. """
		left = min(max(anchor.center().x() - WIDTH / 2, area.left() + 4), area.right() - WIDTH - 4)
		top = anchor.top() - 8 - self.box.height()
		self.rise = 1.0 if top >= area.top() else -1.0
		if self.rise < 0:
			top = min(anchor.bottom() + 8, area.bottom() - self.box.height() - 4)
		return QPoint(round(left - MARGIN), round(top - MARGIN))

	@override
	def closeEvent(self, event: QCloseEvent) -> None:
		""" Fades the menu out instead of closing it at once. """
		event.ignore()
		self.appear.setDirection(QAbstractAnimation.Direction.Backward)
		if self.appear.state() != QAbstractAnimation.State.Running:
			self.appear.start()

	def hide_if_faded(self) -> None:
		if self.appear.direction() == QAbstractAnimation.Direction.Backward:
			self.hide()

	def watch_mouse(self) -> None:
		""" Closes the menu when a mouse button goes down away from it, on another app, on the desktop or on her. """
		down = mouse_down()
		if down and not self.mouse_was_down and not self.box.contains(self.mapFromGlobal(QCursor.pos().toPointF())):
			self.close()
		self.mouse_was_down = down

	@override
	def keyPressEvent(self, event: QKeyEvent) -> None:
		if event.key() == Qt.Key.Key_Escape:
			self.close()

	@override
	def changeEvent(self, event: QEvent) -> None:
		if event.type() == QEvent.Type.ActivationChange and self.isVisible() and not self.isActiveWindow():
			self.close()

	@override
	def hideEvent(self, event: QHideEvent) -> None:
		self.watch.stop()
		self.hover(None)
		self.sliding = None
		self.pressed = False
		self.closed.emit()

	@override
	def mouseMoveEvent(self, event: QMouseEvent) -> None:
		if self.sliding:
			self.slide(*self.sliding, event.position().x())
			return
		self.hover(self.row_at(event.position()))

	@override
	def leaveEvent(self, event: QEvent) -> None:
		if not self.sliding:
			self.hover(None)

	@override
	def mousePressEvent(self, event: QMouseEvent) -> None:
		""" Drags a slider, or closes the menu on its cross or on its transparent margin. """
		point = event.position()
		if not self.box.contains(point) or (point - self.cross).manhattanLength() <= 1.4 * BUTTON_RADIUS:
			self.close()
			return
		self.pressed = True
		index = self.row_at(event.position())
		if index is not None and isinstance(row := self.rows[index][0], Slider):
			self.sliding = (row, self.rows[index][1])
			self.slide(*self.sliding, event.position().x())

	@override
	def mouseReleaseEvent(self, event: QMouseEvent) -> None:
		pressed, self.pressed = self.pressed, False
		if self.sliding or not pressed:
			self.sliding = None
			return
		index = self.row_at(event.position())
		match self.rows[index][0] if index is not None else None:
			case Entry() as entry:
				entry.run()
				self.close()
			case Switch() as switch:
				switch.on = not switch.on
				switch.toggled(switch.on)
				self.flipped = switch
				self.flip.start()
			case _:
				pass

	@override
	def wheelEvent(self, event: QWheelEvent) -> None:
		index = self.row_at(event.position())
		if index is not None and isinstance(row := self.rows[index][0], Slider):
			self.set_value(row, row.value + VOLUME_STEP * event.angleDelta().y() / 120)

	def row_at(self, point: QPointF) -> int | None:
		return next((index for index, (_, rect) in enumerate(self.rows) if rect.contains(point)), None)

	def hover(self, index: int | None) -> None:
		""" Glides the tint to the row at `index`, or takes it off for None. """
		if index == self.hovered:
			return
		self.hovered = index
		self.glide.stop()
		if index is None or self.highlight.isEmpty():
			self.highlight = QRectF() if index is None else self.rows[index][1]
			self.update()
			return
		self.glide.setStartValue(self.highlight)
		self.glide.setEndValue(self.rows[index][1])
		self.glide.start()

	def on_glide(self, rect: QRectF) -> None:
		self.highlight = rect
		self.update()

	def slide(self, slider: Slider, rect: QRectF, x: float) -> None:
		track = slider_track(rect)
		self.set_value(slider, (x - track.left()) / track.width())

	def set_value(self, slider: Slider, value: float) -> None:
		value = round(100 * min(1.0, max(0.0, value))) / 100
		if value != slider.value:
			slider.value = value
			slider.changed(value)
			self.update()

	@override
	def paintEvent(self, event: QPaintEvent) -> None:
		painter = QPainter(self)
		painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
		shown = float(self.appear.currentValue())
		painter.setOpacity(shown)
		painter.translate(0, self.rise * SLIDE_PX * (1 - shown))
		shape = QPainterPath()
		shape.addRoundedRect(self.box, 16, 16)
		paint_shadow(painter, shape)
		paint_paper(painter, shape, self.box, now=0.0)
		paint_twinkles(painter, self.box, now=0.0)
		paint_tag(painter, self.box, now=0.0)
		paint_button(painter, self.cross, hide=False)

		painter.setPen(QPen(QColor(ACCENT.red(), ACCENT.green(), ACCENT.blue(), 45), 1))
		for y in self.lines:
			painter.drawLine(QPointF(self.box.left() + 18, y), QPointF(self.box.right() - 18, y))
		if not self.highlight.isEmpty():
			tint = QLinearGradient(self.highlight.topLeft(), self.highlight.topRight())
			tint.setColorAt(0, QColor(ACCENT.red(), ACCENT.green(), ACCENT.blue(), 46))
			tint.setColorAt(1, QColor(GOLD.red(), GOLD.green(), GOLD.blue(), 30))
			painter.setPen(Qt.PenStyle.NoPen)
			painter.setBrush(tint)
			painter.drawRoundedRect(self.highlight, 10, 10)
		for index, (row, rect) in enumerate(self.rows):
			self.paint_row(painter, row, rect, hovered=index == self.hovered)

	def paint_row(self, painter: QPainter, row: Row, rect: QRectF, *, hovered: bool) -> None:
		painter.setPen(ACCENT if hovered else MUTED)
		painter.setFont(QFont(ICONS, 11))
		painter.drawText(QRectF(rect.left() + 6, rect.top(), 24, rect.height()), Qt.AlignmentFlag.AlignCenter, row.glyph)
		painter.setPen(INK)
		painter.setFont(QFont("Segoe UI", 10))
		painter.drawText(rect.adjusted(38, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, row.label)
		match row:
			case Slider():
				paint_slider(painter, slider_track(rect), row.value)
				painter.setPen(MUTED)
				painter.setFont(QFont("Segoe UI", 9))
				right = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
				painter.drawText(rect.adjusted(0, 0, -8, 0), right, f"{row.value:.0%}")
			case Switch():
				flipping = row is self.flipped and self.flip.state() == QAbstractAnimation.State.Running
				knob = float(self.flip.currentValue()) if flipping else 1.0
				paint_switch(painter, QRectF(rect.right() - 46, rect.center().y() - 9, 36, 18), knob if row.on else 1 - knob)
			case Entry():
				pass


# Functions
def mouse_down() -> bool:
	""" Whether a mouse button is down, wherever the cursor is, which Qt only tells of its own windows. """
	return any(ctypes.windll.user32.GetAsyncKeyState(button) & 0x8000 for button in MOUSE_BUTTONS)


def slider_track(row: QRectF) -> QRectF:
	return QRectF(row.left() + TRACK_LEFT, row.center().y() - 2, row.width() - TRACK_LEFT - 46, 4)


def paint_slider(painter: QPainter, track: QRectF, value: float) -> None:
	""" A rounded track filled from its left up to `value`, from 0 to 1, with a knob there. """
	painter.setPen(Qt.PenStyle.NoPen)
	painter.setBrush(QColor(INK.red(), INK.green(), INK.blue(), 34))
	painter.drawRoundedRect(track, 2, 2)
	filled = QLinearGradient(track.topLeft(), track.topRight())
	filled.setColorAt(0, ACCENT)
	filled.setColorAt(1, GOLD)
	painter.setBrush(filled)
	painter.drawRoundedRect(QRectF(track.left(), track.top(), track.width() * value, track.height()), 2, 2)
	knob = QPointF(track.left() + track.width() * value, track.center().y())
	painter.setPen(QPen(ACCENT, 1.6))
	painter.setBrush(QColor(255, 253, 249))
	painter.drawEllipse(knob, 7, 7)


def paint_switch(painter: QPainter, track: QRectF, on: float) -> None:
	""" A pill whose knob sits on its right and fills it with the accent at `on` 1, on its left at 0. """
	radius = track.height() / 2
	painter.setPen(Qt.PenStyle.NoPen)
	painter.setBrush(QColor(INK.red(), INK.green(), INK.blue(), 46))
	painter.drawRoundedRect(track, radius, radius)
	painter.save()
	painter.setOpacity(painter.opacity() * on)
	painter.setBrush(ACCENT)
	painter.drawRoundedRect(track, radius, radius)
	painter.restore()
	knob = QPointF(track.left() + radius + (track.width() - 2 * radius) * on, track.center().y())
	painter.setBrush(QColor(255, 253, 249))
	painter.drawEllipse(knob, radius - 3, radius - 3)

