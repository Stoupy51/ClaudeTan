""" Claude-tan's speech bubble: warm paper with a shimmering rim, her name tag, and the text typed with its last letters fading in. """
# Imports
import html
import itertools
import math
import re

from PySide6.QtCore import QPointF, QRectF, QSize, QSizeF, Qt, QUrl
from PySide6.QtGui import (
	QBrush,
	QColor,
	QConicalGradient,
	QFont,
	QImage,
	QLinearGradient,
	QPainter,
	QPainterPath,
	QPen,
	QPixmap,
	QRadialGradient,
	QTextDocument,
)

from claudetan.overlay.effects import ACCENT, halo, overshoot, star
from claudetan.report import Report

# Constants
WIDTH: int = 400
""" Room the bubble takes left of the sprite, its tail included. """
TEXT_HEIGHT: float = 210.0
""" Tallest the text area gets: a longer text scrolls inside it. """
REPORT_HEIGHT: float = 290.0
""" Tallest it gets for a report, which is read at a glance rather than line by line. """
SLICE_COLORS: dict[str, str] = {
	"Messages": "#3b82f6", "System tools": "#ea5a2b", "Memory files": "#1fa97a", "Skills": "#d99a1e", "System prompt": "#9ca3af",
	"MCP tools": "#8b5cf6", "MCP server instructions": "#6b7280", "Autocompact buffer": "#4b5563", "Free space": "#e3dccf",
}
""" The color of each part of the context, in the order of the usual `/context` bar. """
PADDING: float = 16.0
MAX_TEXT_WIDTH: float = WIDTH - 20 - 2 * PADDING
""" Widest the text area gets: a longer line wraps. A shorter text narrows the bubble to its longest line. """
RIGHT_EDGE: float = WIDTH - 12.0
""" Where the bubble ends, whatever its width, so that its tail stays by her. """
SUBPIXEL_SCALE: float = 1.0001
""" Qt draws text and unscaled pixmaps at whole pixels, so a slow scroll jumps. Any scale makes it interpolate the pixmap instead. """
POP_S: float = 0.35
RESIZE_RATE: float = 14.0
""" How fast the bubble reaches the size of a new text, as the share of the remaining gap closed per second (exponential). """
TYPING_S: float = 1.0
""" The longest a text takes to appear: a long one types faster to fit. """
TYPING_SPEED: float = 80.0
""" Letters per second a short text types at, until the config's `typing_speed` replaces it. """
SCROLL_DELAY_S: float = 2.5
""" Time to read the first lines before a long text starts scrolling. """
SCROLL_SPEED: float = 14.0
""" Pixels per second a long text scrolls at, about the pace of reading it. """
FADE_CHARS: float = 6.0
""" How many letters behind the typing head are still fading in. """
INK: QColor = QColor(61, 57, 41)
LINK: QColor = QColor(37, 99, 235)
URI: re.Pattern[str] = re.compile(
	r"https?://[^\s<>\"')\]]*[^\s<>\"')\].,;:!?]|\b[A-Za-z]:[\\/][^\s<>\"'|*?]*[^\s<>\"'|*?)\].,;:!?]",
)
""" A web address or a Windows path, without the punctuation that ends the sentence around it. """
INK_RGB: str = f"{INK.red()}, {INK.green()}, {INK.blue()}"
LINK_RGB: str = f"{LINK.red()}, {LINK.green()}, {LINK.blue()}"
GOLD: QColor = QColor(242, 184, 112)
ROSE: QColor = QColor(236, 138, 150)
BUTTON_RADIUS: float = 10.0
NAME: str = "Claude-tan"
RAYS: tuple[float, ...] = (1.0, 0.8, 0.95, 0.85, 1.0, 0.75, 0.95, 0.8, 1.0, 0.8, 0.9, 0.85)
""" Relative length of each ray of the Claude logo, going around from the right. """


# Classes
class Bubble:
	""" Her speech bubble, its text laid out in full from the start so that words never jump to the next line while typed. """

	def __init__(self) -> None:
		self.text = ""
		self.report: Report | None = None
		self.shown_at = -1.0
		""" When the bubble popped out of its tail, which a new text shown while it is up does not repeat. """
		self.started_at = -1.0
		""" When the current text started, from which it scrolls. """
		self.size = QSizeF()
		self.sized_at = -1.0
		""" The size the box is drawn at, easing toward the one the text needs, and when it was last moved. """
		self.revealed = 0.0
		""" How many letters are typed so far, running `FADE_CHARS` past the end while the last ones fade in. """
		self.typing_speed = TYPING_SPEED
		self.document = QTextDocument()
		""" The text laid out, kept between frames while `typed` is unchanged. """
		self.document.setDefaultFont(QFont("Segoe UI", 11))
		self.document.setDocumentMargin(0)
		self.document.setTextWidth(MAX_TEXT_WIDTH)
		self.text_width = MAX_TEXT_WIDTH
		self.fitted = ""
		""" The text `text_width` was fitted to. """
		self.typed = ("", -1.0)
		self.pixmap_key: tuple[tuple[str, float], float] = (("", -1.0), 0.0)
		self.pixmap = QPixmap()
		""" The text drawn once at the screen's scale, to scroll it smoothly. """
		self.scrolled = 0.0
		self.max_scroll = 0.0
		self.dragged: float | None = None
		""" Where the mouse wheel left the text, which stops the automatic scroll until another text is shown. """

		self.read_since: float | None = None
		""" When the wheel last left the text at its end, None while the end is not in sight. """
		self.links: list[tuple[int, int, str]] = []
		""" The span of `text` each link covers, with its URL. """
		self.text_area = QRectF()
		""" Where the text was last drawn, in the coordinates the bubble is painted in. """
		self.buttons: dict[str, QRectF] = {}
		""" Where its "close" and "hide" buttons were last drawn, in the coordinates the bubble is painted in. """

	def scroll(self, pixels: float, now: float) -> None:
		self.dragged = max(0.0, min(self.max_scroll, self.scrolled + pixels))
		self.read_since = now if self.dragged == self.max_scroll else None

	def say(self, text: str | Report, now: float) -> None:
		""" Shows the text, typing on from where it was when it continues the shown one, as a reply streamed in pieces does.

		A report appears at once, since it is a bar and a table rather than a text to read as it comes.
		"""
		self.report = text if isinstance(text, Report) else None
		shown = plain(str(text))
		if not shown:
			self.shown_at = -1.0
		elif not self.text:
			self.shown_at = now
		if self.report:
			self.revealed = len(shown) + FADE_CHARS
			self.started_at = now
			self.dragged = self.read_since = None
		elif not (self.text and shown.startswith(self.text)):
			self.revealed = 0.0
			self.started_at = now
			self.dragged = self.read_since = None
		self.text = shown
		self.links = [] if self.report else links(shown)

	def type(self, seconds: float) -> None:
		speed = max(self.typing_speed, len(self.text) / TYPING_S)
		self.revealed = min(len(self.text) + FADE_CHARS, self.revealed + speed * seconds)

	def paint(self, painter: QPainter, now: float, bottom: float) -> None:
		""" The bubble with its bottom edge at `bottom`, growing upward, popping out once and then easing to each new text size. """
		self.lay_out()
		height = self.document.size().height()
		visible = min(height, REPORT_HEIGHT if self.report else TEXT_HEIGHT)
		self.max_scroll = height - visible
		automatic = SCROLL_SPEED * max(0.0, now - self.started_at - SCROLL_DELAY_S)
		scrolled = self.scrolled = min(self.max_scroll, automatic if self.dragged is None else self.dragged)
		size = self.eased_size(QSizeF(self.text_width + 2 * PADDING, visible + 2 * PADDING), now)
		box = QRectF(RIGHT_EDGE - size.width(), max(18.0, bottom - size.height()), size.width(), size.height())
		shape = outline(box)
		tip = QPointF(box.right() + 18, box.bottom() - 14)
		close = QPointF(box.right() - 6, box.top() + 2)
		centers = {"close": close, "hide": close - QPointF(2 * BUTTON_RADIUS + 4, 0)}
		diameter = 2 * BUTTON_RADIUS
		self.buttons = {name: QRectF(c.x() - BUTTON_RADIUS, c.y() - BUTTON_RADIUS, diameter, diameter) for name, c in centers.items()}
		appeared = min(1.0, (now - self.shown_at) / POP_S)
		grown = 0.8 + 0.2 * overshoot(appeared)

		painter.save()
		painter.setOpacity(min(1.0, 3 * appeared))
		painter.translate(tip + QPointF(0, 8 * (1 - appeared)))
		painter.scale(grown, grown)
		painter.translate(-tip)
		paint_shadow(painter, shape)
		paint_paper(painter, shape, box, now)
		paint_twinkles(painter, box, now)
		paint_tag(painter, box, now)
		paint_button(painter, centers["hide"], hide=True)
		paint_button(painter, centers["close"], hide=False)
		if self.revealed >= len(self.text) + FADE_CHARS:
			paint_next_mark(painter, box, now)
		self.text_area = box.adjusted(PADDING, PADDING, -PADDING, -PADDING)
		self.paint_text(painter, self.text_area, scrolled)
		painter.restore()

	def eased_size(self, target: QSizeF, now: float) -> QSizeF:
		""" `self.size` moved toward `target`, set to it when the bubble has just popped out. """
		if now - self.shown_at < POP_S:
			self.size = target
		else:
			share = 1 - math.exp(-RESIZE_RATE * (now - self.sized_at))
			self.size += (target - self.size) * share
		self.sized_at = now
		return self.size

	def paint_text(self, painter: QPainter, area: QRectF, scrolled: float) -> None:
		""" The text clipped to `area`, `scrolled` pixels up. """
		painter.setClipRect(area)
		if self.dragged is not None or not scrolled:
			painter.translate(on_whole_pixels(painter, area.topLeft() - QPointF(0, scrolled)))
			self.document.drawContents(painter)
			return

		painter.scale(SUBPIXEL_SCALE, SUBPIXEL_SCALE)
		painter.drawPixmap(QPointF(area.left(), area.top() - scrolled), self.text_pixmap(painter.deviceTransform().m11()))

	def text_pixmap(self, device_scale: float) -> QPixmap:
		scale = round(device_scale, 2)
		key = (self.typed, scale)
		if self.pixmap_key != key:
			self.pixmap_key = key
			size = QSize(math.ceil(self.text_width * scale), math.ceil(self.document.size().height() * scale))
			image = QImage(size, QImage.Format.Format_ARGB32_Premultiplied)
			image.fill(0)
			painter = QPainter(image)
			painter.setRenderHint(QPainter.RenderHint.Antialiasing)
			painter.scale(scale, scale)
			self.document.drawContents(painter)
			painter.end()
			image.setDevicePixelRatio(scale)
			self.pixmap = QPixmap.fromImage(image)
		return self.pixmap

	def lay_out(self) -> None:
		""" Sets the document to the whole text: typed letters in ink, the latest ones fading in, the rest transparent. """
		if self.typed == (self.text, self.revealed):
			return
		self.typed = (self.text, self.revealed)
		if self.report:
			self.document.setHtml(report_markup(self.report))
			self.document.setTextWidth(MAX_TEXT_WIDTH)
			self.text_width = MAX_TEXT_WIDTH
			self.fitted = ""
			return

		solid = max(0, math.floor(self.revealed - FADE_CHARS))
		head = min(len(self.text), math.ceil(self.revealed))
		fading = "".join(self.segment(i, i + 1, round(255 * min(1.0, (self.revealed - i) / FADE_CHARS))) for i in range(solid, head))
		self.document.setHtml(
			f'<p style="line-height: 118%">{self.segment(0, solid, 255)}{fading}{self.segment(head, len(self.text), 0)}</p>',
		)
		if self.fitted != self.text:
			self.fitted = self.text
			self.document.setTextWidth(MAX_TEXT_WIDTH)
			self.text_width = min(MAX_TEXT_WIDTH, math.ceil(self.document.idealWidth()))
			self.document.setTextWidth(self.text_width)

	def segment(self, start: int, end: int, alpha: int) -> str:
		""" The markup of `text[start:end]` at `alpha` out of 255, its links being anchors in the color of links. """
		cuts = sorted({start, end, *(cut for first, last, _ in self.links for cut in (first, last) if start < cut < end)})
		pieces: list[str] = []
		for first, last in itertools.pairwise(cuts):
			url = next((url for begin, stop, url in self.links if begin <= first < stop), None)
			text = markup(self.text[first:last])
			if url:
				pieces.append(f'<a href="{html.escape(url)}" style="color: rgba({LINK_RGB}, {alpha})">{text}</a>')
			else:
				pieces.append(f'<span style="color: rgba({INK_RGB}, {alpha})">{text}</span>')
		return "".join(pieces)

	def link_at(self, point: QPointF) -> str:
		""" The URL of the link under `point`, given in the coordinates the bubble is painted in, or an empty string. """
		if not self.text_area.contains(point):
			return ""
		return self.document.documentLayout().anchorAt(point - self.text_area.topLeft() + QPointF(0, self.scrolled))


# Functions
def links(text: str) -> list[tuple[int, int, str]]:
	""" The web addresses and Windows paths of the text, each as its span and the URL to open.

	>>> links("See https://claude.ai/code#top, or D:/x/a.py.")
	[(4, 30, 'https://claude.ai/code#top'), (35, 44, 'file:///D:/x/a.py')]
	"""
	return [
		(found.start(), found.end(), found[0] if found[0].startswith("http") else QUrl.fromLocalFile(found[0]).toString())
		for found in URI.finditer(text)
	]


def on_whole_pixels(painter: QPainter, point: QPointF) -> QPointF:
	""" The painter's `point`, moved to the nearest whole pixel of the screen, where Qt draws text sharp. """
	to_screen = painter.deviceTransform()
	on_screen = to_screen.map(point)
	inverse, _ = to_screen.inverted()
	return inverse.map(QPointF(round(on_screen.x()), round(on_screen.y())))


def plain(text: str) -> str:
	""" The text as the bubble shows it: Markdown marks dropped, spaces collapsed, one line per line of text.

	>>> plain("**Done**: edited `app.py`.\\n\\n- one\\n- two")
	'Done: edited app.py.\\none\\ntwo'
	"""
	lines = re.sub(r"[*`]|^\s*#+ ?|^\s*[-+] ", "", text, flags=re.MULTILINE).splitlines()
	return "\n".join(" ".join(line.split()) for line in lines if line.strip())


def report_markup(report: Report) -> str:
	""" The title, a bar of the colored slices, and a table of them, each part in the color of its slice. """
	title = markup(report.title)
	bar = "".join(
		f'<td width="{100 * part.fraction:.1f}%" bgcolor="{SLICE_COLORS.get(part.key, "#9ca3af")}" style="font-size: 9pt">&nbsp;</td>'
		for part in report.slices if part.fraction >= 0.005
	)
	rows = "".join(
		f'<tr><td><span style="color: {SLICE_COLORS.get(part.key, "#9ca3af")}">&#9632;</span> {markup(part.label)}</td>'
		f'<td align="right">{markup(part.amount)}</td><td align="right">{markup(part.share)}</td></tr>'
		for part in report.slices
	)
	return (
		f'<p style="line-height: 118%; color: {INK.name()}">{title}</p>'
		f'<table width="100%" cellspacing="0" cellpadding="0"><tr>{bar}</tr></table>'
		f'<table width="100%" cellspacing="0" cellpadding="2" style="font-size: 10pt; color: {INK.name()}">{rows}</table>'
	)


def markup(text: str) -> str:
	return html.escape(text).replace("\n", "<br>")


def outline(box: QRectF) -> QPainterPath:
	""" Rounded box with a curved tail hooking out of its right side toward her. """
	shape = QPainterPath()
	shape.addRoundedRect(box, 16, 16)
	tail = QPainterPath()
	tail.moveTo(box.right() - 8, box.bottom() - 42)
	tail.quadTo(box.right() + 4, box.bottom() - 24, box.right() + 18, box.bottom() - 14)
	tail.quadTo(box.right() + 2, box.bottom() - 10, box.right() - 8, box.bottom() - 18)
	tail.closeSubpath()
	return shape.united(tail)


def paint_shadow(painter: QPainter, shape: QPainterPath) -> None:
	""" Soft warm shadow under the bubble, built from widening translucent strokes of its outline. """
	painter.setBrush(Qt.BrushStyle.NoBrush)
	for width in range(2, 20, 2):
		painter.setPen(QPen(QColor(90, 40, 20, 7), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
		painter.drawPath(shape.translated(0, 5))


def paint_paper(painter: QPainter, shape: QPainterPath, box: QRectF, now: float) -> None:
	""" Cream paper lit warmly from her name tag, with a sheen along its top edge and a rim of slowly turning colors. """
	fill = QLinearGradient(box.topLeft(), box.bottomLeft())
	fill.setColorAt(0, QColor(255, 253, 249))
	fill.setColorAt(1, QColor(250, 240, 230))
	painter.setPen(Qt.PenStyle.NoPen)
	painter.setBrush(fill)
	painter.drawPath(shape)

	painter.save()
	painter.setClipPath(shape)
	light = QRadialGradient(box.topLeft() + QPointF(36, 0), 0.75 * box.width())
	light.setColorAt(0, QColor(255, 190, 140, 60))
	light.setColorAt(1, QColor(255, 190, 140, 0))
	painter.setBrush(light)
	painter.drawPath(shape)
	# Clipped to the shape, a 3 px stroke leaves a 1.5 px line on the inside of the edge
	sheen = QLinearGradient(box.topLeft(), box.topLeft() + QPointF(0, 22))
	sheen.setColorAt(0, QColor(255, 255, 255, 230))
	sheen.setColorAt(1, QColor(255, 255, 255, 0))
	painter.setPen(QPen(QBrush(sheen), 3))
	painter.setBrush(Qt.BrushStyle.NoBrush)
	painter.drawPath(shape)
	painter.setPen(QPen(QColor(ACCENT.red(), ACCENT.green(), ACCENT.blue(), 30), 7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
	paint_logo(painter, box.bottomLeft() + QPointF(16, -4), 44, angle=0.15 * now)
	painter.restore()

	rim = QConicalGradient(box.center(), -45 * now % 360)
	for stop, color in ((0.0, ACCENT), (0.35, GOLD), (0.7, ROSE), (1.0, ACCENT)):
		rim.setColorAt(stop, color)
	painter.setPen(QPen(QBrush(rim), 1.6))
	painter.setBrush(Qt.BrushStyle.NoBrush)
	painter.drawPath(shape)


def paint_twinkles(painter: QPainter, box: QRectF, now: float) -> None:
	""" Two glowing stars twinkling out of step astride the top right corner. """
	painter.save()
	painter.setPen(Qt.PenStyle.NoPen)
	opacity = painter.opacity()
	for offset, size, phase in ((QPointF(-6, -2), 9.0, 0.0), (QPointF(6, 10), 5.0, 2.1)):
		twinkle = 0.5 + 0.5 * math.sin(2.6 * now + phase)
		center = box.topRight() + offset
		radius = size * (0.75 + 0.25 * twinkle)
		painter.setOpacity(opacity * (0.45 + 0.55 * twinkle))
		glow = QRectF(center.x() - 2 * radius, center.y() - 2 * radius, 4 * radius, 4 * radius)
		painter.drawPixmap(glow, halo(GOLD.rgb()), QRectF(0, 0, 64, 64))
		painter.setBrush(GOLD)
		painter.drawPath(star(center, radius, angle=0.3 * now + phase))
		painter.setBrush(QColor(255, 255, 255))
		painter.drawEllipse(center, 0.22 * radius, 0.22 * radius)
	painter.restore()


def paint_tag(painter: QPainter, box: QRectF, now: float) -> None:
	""" Her name on a gradient pill straddling the top edge, behind the Claude logo, with a gleam sweeping across it now and then. """
	painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
	tag = QRectF(box.left() + 14, box.top() - 10, painter.fontMetrics().horizontalAdvance(NAME) + 32, 20)
	pill = QPainterPath()
	pill.addRoundedRect(tag, 10, 10)
	fill = QLinearGradient(tag.topLeft(), tag.topRight())
	fill.setColorAt(0, ACCENT)
	fill.setColorAt(1, QColor(240, 150, 100))
	painter.setPen(Qt.PenStyle.NoPen)
	painter.setBrush(fill)
	painter.drawPath(pill)

	sweep = (now % 3.5) / 0.9
	if sweep < 1:
		x = tag.left() - 24 + sweep * (tag.width() + 48)
		gleam = QLinearGradient(QPointF(x - 14, 0), QPointF(x + 14, 0))
		gleam.setColorAt(0, QColor(255, 255, 255, 0))
		gleam.setColorAt(0.5, QColor(255, 255, 255, 120))
		gleam.setColorAt(1, QColor(255, 255, 255, 0))
		painter.setBrush(gleam)
		painter.drawPath(pill)

	painter.setPen(QPen(QColor(255, 255, 255), 1.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
	paint_logo(painter, QPointF(tag.left() + 12, tag.center().y()), 5, angle=0)
	painter.drawText(tag.adjusted(16, 0, -4, 0), Qt.AlignmentFlag.AlignCenter, NAME)


def paint_button(painter: QPainter, center: QPointF, *, hide: bool) -> None:
	""" Round button straddling the bubble's top edge: a chevron down to hide her, a cross to drop what she is listening to. """
	painter.setPen(QPen(ACCENT, 1.2))
	painter.setBrush(QColor(255, 250, 238))
	painter.drawEllipse(center, BUTTON_RADIUS, BUTTON_RADIUS)
	reach = 0.45 * BUTTON_RADIUS
	painter.setPen(QPen(INK, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
	if hide:
		half = 0.5 * reach
		painter.drawPolyline([center + QPointF(-reach, -half), center + QPointF(0, half), center + QPointF(reach, -half)])
		return
	painter.drawLine(center + QPointF(-reach, -reach), center + QPointF(reach, reach))
	painter.drawLine(center + QPointF(-reach, reach), center + QPointF(reach, -reach))


def paint_logo(painter: QPainter, center: QPointF, radius: float, angle: float) -> None:
	""" The Claude logo in the painter's pen, its rays turned by `angle` radians, stroked as one path so overlaps never darken. """
	logo = QPainterPath()
	for i, length in enumerate(RAYS):
		theta = angle + i * math.tau / len(RAYS)
		logo.moveTo(center)
		logo.lineTo(center + QPointF(math.cos(theta), -math.sin(theta)) * radius * length)
	painter.drawPath(logo)


def paint_next_mark(painter: QPainter, box: QRectF, now: float) -> None:
	""" Little chevron bobbing in the bottom right corner once the whole text is typed. """
	bob = 2.0 * math.sin(5 * now)
	corner = QPointF(box.right() - PADDING, box.bottom() - 8 + bob)
	mark = QPainterPath()
	mark.moveTo(corner + QPointF(-5, -3))
	mark.lineTo(corner + QPointF(0, 2))
	mark.lineTo(corner + QPointF(5, -3))
	painter.setPen(QPen(ACCENT, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
	painter.setBrush(Qt.BrushStyle.NoBrush)
	painter.drawPath(mark)

