""" Overlay spike: the avatar pops up in the bottom-right corner, plays through her expressions, blinks and moves her mouth.

A click opens the Remote Control session, a long press lets you drag her somewhere else.
Run with `uv run prototypes/overlay_demo.py`, close with a right click.
"""
# Imports
import random
import sys
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, override

from PySide6.QtCore import QEasingCurve, QParallelAnimationGroup, QPoint, QPropertyAnimation, QRectF, QSettings, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QMouseEvent, QPainter, QPainterPath, QPaintEvent, QPixmap
from PySide6.QtWidgets import QApplication, QWidget

# Constants
ASSETS: Path = Path(__file__).resolve().parent.parent / "assets" / "claude"
SPRITE_HEIGHT: int = 400
""" Display height of the idle pose; every sprite gets the same scale so her face never jumps. """
BUBBLE_WIDTH: int = 250
SPRITE_TOP: int = 24
FACE_Y: float = 0.49
""" Vertical position of the face center in the sprites, as a fraction of the idle sprite height. """
LONG_PRESS_MS: int = 200
CLICK_SLOP: int = 6
""" Pixels the cursor may travel during a press that still counts as a click. """
REMOTE_URL: str = "https://claude.ai/code"
""" The real app opens the URL of the session it hosts, read from the hidden Claude Code terminal. """
TALK_FRAMES: dict[str, tuple[str, ...]] = {
	"idle": ("idle", "idle_talk_wide", "idle_talk_o"),
	"hello": ("hello", "hello_o"),
}
""" Mouth frames of the poses that can talk. """


# Classes
@dataclass(frozen=True)
class Beat:
	""" One step of the demo loop. """
	expression: str
	bubble: str
	duration_ms: int
	talking: bool = False


class Avatar(QWidget):
	def __init__(self) -> None:
		super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
		self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
		self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
		ratio = QGuiApplication.primaryScreen().devicePixelRatio()
		scale = SPRITE_HEIGHT * ratio / QPixmap(str(ASSETS / "idle.png")).height()
		self.sprites: dict[str, QPixmap] = {}
		for path in ASSETS.glob("*.png"):
			source = QPixmap(str(path))
			size = (round(source.width() * scale), round(source.height() * scale))
			pixmap = source.scaled(*size, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
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
		self.bubble = bubble
		if talking and expression in TALK_FRAMES:
			self.mouth.start()
		else:
			self.mouth.stop()
		self.update()

	def pop_in(self) -> None:
		saved = QSettings("ClaudeAssist", "overlay").value("pos")
		area = QGuiApplication.primaryScreen().availableGeometry()
		target = saved if isinstance(saved, QPoint) else QPoint(area.right() - self.width(), area.bottom() - self.height())
		self.setWindowOpacity(0)
		self.move(target + QPoint(0, 40))
		self.show()
		self.animate(target, 1.0)

	def pop_out(self) -> None:
		self.animate(self.pos() + QPoint(0, 40), 0.0).finished.connect(self.hide)

	def animate(self, position: QPoint, opacity: float) -> QParallelAnimationGroup:
		group = QParallelAnimationGroup(self)
		for prop, end in ((b"pos", position), (b"windowOpacity", opacity)):
			animation = QPropertyAnimation(self, prop, self)
			animation.setDuration(260)
			animation.setEndValue(end)
			animation.setEasingCurve(QEasingCurve.Type.OutCubic)
			group.addAnimation(animation)
		group.start(QParallelAnimationGroup.DeletionPolicy.DeleteWhenStopped)
		return group

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
		text = painter.boundingRect(QRectF(0, 0, BUBBLE_WIDTH - 36, 400), Qt.TextFlag.TextWordWrap, self.bubble)
		box = QRectF(8, SPRITE_TOP + FACE_Y * SPRITE_HEIGHT - 70 - text.height() / 2, BUBBLE_WIDTH - 20, text.height() + 24)
		path = QPainterPath()
		path.addRoundedRect(box, 14, 14)
		tail = QPainterPath()
		tail.moveTo(box.right() - 4, box.top() + 18)
		tail.lineTo(box.right() + 18, box.top() + 30)
		tail.lineTo(box.right() - 4, box.top() + 34)
		painter.setPen(QColor(217, 119, 87))
		painter.setBrush(QColor(255, 250, 244, 240))
		painter.drawPath(path.united(tail))
		painter.setPen(QColor(40, 30, 25))
		painter.drawText(box.adjusted(14, 12, -14, -12), Qt.TextFlag.TextWordWrap, self.bubble)

	@override
	def mousePressEvent(self, event: QMouseEvent) -> None:
		if event.button() == Qt.MouseButton.RightButton:
			QApplication.quit()
			return
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
			webbrowser.open(REMOTE_URL)
		elif self.dragging:
			self.dragging = False
			self.unsetCursor()
			QSettings("ClaudeAssist", "overlay").setValue("pos", self.pos())
		self.press_offset = None

	def start_drag(self) -> None:
		self.dragging = True
		self.setCursor(Qt.CursorShape.ClosedHandCursor)


class Demo:
	BEATS: ClassVar[list[Beat]] = [
		Beat(expression="hello",           bubble="Coucou ! Tu m'as appelée ?",                duration_ms=2600, talking=True),
		Beat(expression="idle",            bubble="",                                          duration_ms=3000),
		Beat(expression="idle",            bubble="Je regarde ça tout de suite...",            duration_ms=3200, talking=True),
		Beat(expression="closeup_curious", bubble="Hmm, laisse-moi réfléchir.",                duration_ms=2400),
		Beat(expression="present",         bubble="Voilà, c'est fait !",                       duration_ms=2200),
		Beat(expression="please",          bubble="J'ai besoin de ton accord pour continuer.", duration_ms=3000),
		Beat(expression="thanks",          bubble="Merci !",                                   duration_ms=1800),
		Beat(expression="surprised",       bubble="Oh !",                                      duration_ms=1500),
		Beat(expression="happy",           bubble="",                                          duration_ms=1800),
		Beat(expression="point",           bubble="Clique sur moi pour ouvrir la session.",    duration_ms=3000),
	]

	def __init__(self, avatar: Avatar) -> None:
		self.avatar = avatar
		self.step = 0

	def next(self) -> None:
		if self.step == len(self.BEATS):
			self.step = 0
			self.avatar.pop_out()
			QTimer.singleShot(1500, self.restart)
			return
		beat = self.BEATS[self.step]
		self.avatar.set_expression(beat.expression, talking=beat.talking, bubble=beat.bubble)
		self.step += 1
		QTimer.singleShot(beat.duration_ms, self.next)

	def restart(self) -> None:
		self.avatar.pop_in()
		self.next()


# Functions
def main() -> None:
	app = QApplication(sys.argv)
	demo = Demo(Avatar())
	demo.restart()
	sys.exit(app.exec())


if __name__ == "__main__":
	main()

