""" Light around Claire: the glow behind her and the sparks she gives off, drawn from the avatar's clock. """
# Imports
import math
import random
from dataclasses import dataclass
from functools import cache

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPixmap, QRadialGradient

# Constants
ACCENT: QColor = QColor(217, 119, 87)
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


@dataclass(frozen=True)
class Shard:
	""" A square of the sprite that flies off when she vanishes, along a flight fixed in advance. """
	x: float
	y: float
	""" Top-left corner on the sprite, in pixels. """
	delay: float
	""" Fraction of the vanishing it waits before leaving, shorter the lower it sits. """
	dx: float
	dy: float
	""" Where it has flown to by the time it is gone, in pixels. """
	spin: float
	""" Degrees it has turned by then. """


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


def shards(sprite: QPixmap, size: int) -> list[Shard]:
	""" The squares of `size` pixels of the sprite that are not fully transparent, each with its flight. """
	image = sprite.toImage().convertToFormat(QImage.Format.Format_ARGB32)
	alpha = np.frombuffer(image.constBits(), np.uint8).reshape(image.height(), -1, 4)[:, : image.width(), 3]
	ratio = sprite.devicePixelRatio()
	step = round(size * ratio)
	height = sprite.height() / ratio
	return [
		Shard(
			x=left / ratio, y=top / ratio, delay=0.45 * (1 - top / ratio / height) + random.uniform(0, 0.1),
			dx=random.uniform(-30, 60), dy=random.uniform(-160, -50), spin=random.uniform(-200, 200),
		)
		for top in range(0, image.height(), step) for left in range(0, image.width(), step)
		if alpha[top : top + step, left : left + step].any()
	]


def silhouette(sprite: QPixmap) -> QPixmap:
	""" The sprite as a white shape. """
	white = QPixmap(sprite)
	painter = QPainter(white)
	painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
	painter.fillRect(white.rect(), Qt.GlobalColor.white)
	painter.end()
	return white


def flutter(at: QPointF, center: QPointF, now: float) -> Spark:
	""" A spark leaving the sprite at `at`, drifting around `center` while it rises. """
	angle = math.atan2(at.y() - center.y(), at.x() - center.x()) + math.pi / 2
	speed = random.uniform(40, 120)
	return Spark(
		x=at.x(), y=at.y(), vx=math.cos(angle) * speed, vy=math.sin(angle) * speed - random.uniform(90, 200),
		birth=now, life=random.uniform(0.9, 1.4), size=random.uniform(3.5, 7.0), color=random.choice(SPARK_COLORS),
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


def overshoot(t: float) -> float:
	""" Ease-out that passes its target by about 10% before settling, for things that pop up.

	>>> round(overshoot(0.0), 6), overshoot(1.0), round(max(overshoot(i / 100) for i in range(101)), 2)
	(0.0, 1.0, 1.1)
	"""
	return 1 + 2.70158 * (t - 1) ** 3 + 1.70158 * (t - 1) ** 2


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

