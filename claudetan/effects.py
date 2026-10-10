""" Light around Claude-tan: the glow behind her and the sparks she gives off, drawn from the avatar's clock. """
# Imports
import math
import random
from dataclasses import dataclass
from functools import cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPixmap, QRadialGradient

# Constants
SPARK_COLORS: tuple[QColor, ...] = (QColor(255, 247, 222), QColor(255, 214, 150), QColor(255, 178, 128))
GLOW_COLOR: QColor = QColor(255, 150, 96)


# Classes
@dataclass(frozen=True)
class Spark:
	""" A four-pointed star flying off from its origin, slowing down and twinkling until it fades out.

	Its position follows from its age, so nothing updates it between frames.
	"""
	x: float
	y: float
	vx: float
	vy: float
	""" Initial speed, in pixels per second. """
	birth: float
	""" Second of the avatar's clock it appeared at. """
	life: float
	size: float
	color: QColor

	def alive(self, now: float) -> bool:
		return now - self.birth < self.life

	def paint(self, painter: QPainter, now: float) -> None:
		age = now - self.birth
		progress = age / self.life
		travel = age * (1 - 0.5 * progress)
		center = QPointF(self.x + self.vx * travel, self.y + self.vy * travel)
		radius = self.size * (1 - 0.35 * progress)
		opacity = math.sin(math.pi * progress) * (0.75 + 0.25 * math.sin(age * 18 + self.x))

		painter.save()
		painter.setOpacity(opacity)
		reach = 2.4 * radius
		target = QRectF(center.x() - reach, center.y() - reach, 2 * reach, 2 * reach)
		painter.drawPixmap(target, halo(self.color.rgb()), QRectF(0, 0, 64, 64))
		painter.setPen(Qt.PenStyle.NoPen)
		painter.setBrush(self.color)
		painter.drawPath(star(center, radius, angle=age * 1.5))
		painter.setBrush(QColor(255, 255, 255))
		painter.drawEllipse(center, radius * 0.22, radius * 0.22)
		painter.restore()


# Functions
def burst(center: QPointF, now: float, count: int) -> list[Spark]:
	""" Sparks thrown mostly upward from around `center`, as when she pops up or celebrates. """
	sparks: list[Spark] = []
	for _ in range(count):
		angle = random.uniform(-math.pi * 0.95, -math.pi * 0.05)
		speed = random.uniform(170, 330)
		sparks.append(Spark(
			x=center.x() + random.uniform(-50, 50), y=center.y() + random.uniform(-50, 10),
			vx=math.cos(angle) * speed, vy=math.sin(angle) * speed,
			birth=now, life=random.uniform(0.8, 1.3), size=random.uniform(5.0, 10.0),
			color=random.choice(SPARK_COLORS),
		))
	return sparks


def mote(area: QRectF, now: float) -> Spark:
	""" A small spark rising slowly from somewhere in `area`, for the glimmer around her while she stays up. """
	return Spark(
		x=random.uniform(area.left(), area.right()), y=random.uniform(area.top(), area.bottom()),
		vx=random.uniform(-8, 8), vy=random.uniform(-34, -18),
		birth=now, life=random.uniform(2.2, 3.4), size=random.uniform(1.4, 2.6),
		color=random.choice(SPARK_COLORS),
	)


@cache
def halo(rgb: int) -> QPixmap:
	""" 64 px disc of the color fading out from its center, drawn once per color since a gradient per spark is slow. """
	pixmap = QPixmap(64, 64)
	pixmap.fill(Qt.GlobalColor.transparent)
	color = QColor.fromRgb(rgb)
	gradient = QRadialGradient(QPointF(32, 32), 32)
	gradient.setColorAt(0, QColor(color.red(), color.green(), color.blue(), 150))
	gradient.setColorAt(1, QColor(color.red(), color.green(), color.blue(), 0))
	painter = QPainter(pixmap)
	painter.setPen(Qt.PenStyle.NoPen)
	painter.setBrush(gradient)
	painter.drawEllipse(QRectF(0, 0, 64, 64))
	painter.end()
	return pixmap


def star(center: QPointF, radius: float, angle: float) -> QPainterPath:
	""" Four-pointed star with thin arms, turned by `angle` radians. """
	path = QPainterPath()
	for i in range(8):
		r = radius if i % 2 == 0 else radius * 0.28
		theta = angle + i * math.pi / 4
		point = QPointF(center.x() + r * math.cos(theta), center.y() + r * math.sin(theta))
		if i == 0:
			path.moveTo(point)
		else:
			path.lineTo(point)
	path.closeSubpath()
	return path


def glow(width: int, height: int, ratio: float) -> QPixmap:
	""" Warm halo filling an ellipse of `width` x `height` device-independent pixels, fading out from its center. """
	pixmap = QPixmap(round(width * ratio), round(height * ratio))
	pixmap.setDevicePixelRatio(ratio)
	pixmap.fill(Qt.GlobalColor.transparent)
	painter = QPainter(pixmap)
	painter.setRenderHint(QPainter.RenderHint.Antialiasing)
	painter.scale(1, height / width)
	gradient = QRadialGradient(QPointF(width / 2, width / 2), width / 2)
	for stop, alpha in ((0.0, 85), (0.5, 35), (1.0, 0)):
		gradient.setColorAt(stop, QColor(GLOW_COLOR.red(), GLOW_COLOR.green(), GLOW_COLOR.blue(), alpha))
	painter.setPen(Qt.PenStyle.NoPen)
	painter.setBrush(gradient)
	painter.drawEllipse(QRectF(0, 0, width, width))
	painter.end()
	return pixmap

