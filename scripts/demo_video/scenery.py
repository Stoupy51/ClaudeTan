""" What the demo video draws around the overlay: a desktop, what the user says, and the cards that title it. """
# Imports
import math
import re
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
	QColor,
	QConicalGradient,
	QFont,
	QFontMetricsF,
	QImage,
	QLinearGradient,
	QPainter,
	QPainterPath,
	QPen,
	QPicture,
	QPixmap,
	QRadialGradient,
)

from claudechan.config import ROOT
from claudechan.overlay.avatar import ASSETS, face
from claudechan.overlay.effects import ACCENT

# Constants
WIDTH: int = 1920
HEIGHT: int = 1080
TASKBAR: float = 48.0
UI: str = "Segoe UI"
MONO: str = "Cascadia Mono"
WHITE: QColor = QColor(255, 255, 255)
MUTED: QColor = QColor(255, 255, 255, 170)
RIGHT: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
CODE: QColor = QColor(212, 212, 212)
SYNTAX: dict[str, QColor] = {
	"comment": QColor(106, 153, 85), "string": QColor(206, 145, 120), "keyword": QColor(197, 134, 192),
	"number": QColor(181, 206, 168), "call": QColor(220, 220, 170),
}
""" The colors of VS Code's dark theme, by group of `TOKENS`. """
TOKENS: re.Pattern[str] = re.compile(
	r'(?P<comment>#.*)|(?P<string>[rf]*"[^"]*"?)|(?P<keyword>\b(?:def|return|class|import|from|lambda|if|else|for|in|not|and|or|None|True|False)\b)'
	r"|(?P<number>\b\d+\b)|(?P<call>\w+(?=\())",
)
SHOWN_CODE: str = "ACTIONS: list[Action] = ["
""" The editor scrolls to this line of `actions.py`, a few lines above it. """
TERMINAL: tuple[tuple[str, QColor], ...] = (
	("PS D:\\dev\\ClaudeChan> uv run claudechan", CODE),
	("[PROGRESS 14:31:12] Starting ClaudeChan, which takes about 15 s...", QColor(214, 112, 214)),
	("[INFO  14:31:26] Claude Code session resumed: https://claude.ai/code/session_01HcV8", QColor(35, 209, 139)),
	("[INFO  14:31:29] Plan usage: Claude plan", QColor(35, 209, 139)),
	("5-hour window: 22% used, resets 6:30pm", QColor(35, 209, 139)),
	("Week: 27% used, resets Oct 19, 12am", QColor(35, 209, 139)),
	("[INFO  14:31:29] Whisper runs on the GPU", QColor(35, 209, 139)),
	('[INFO  14:31:29] Say "Hey Claire, ..." to ask her something', QColor(35, 209, 139)),
	("PS D:\\dev\\ClaudeChan> ", CODE),
)
""" What `uv run claudechan` prints, each line in its color. """
EDITOR_FRAME: QRectF = QRectF(64, 44, 1150, 800)
TERMINAL_FRAME: QRectF = QRectF(420, 590, 780, 330)
TERMINAL_ICON: QPointF = QPointF(WIDTH / 2 + 48, HEIGHT - TASKBAR / 2)
""" Where the terminal's window goes when it is minimized, its button in the taskbar. """
TRAY_ICON: QRectF = QRectF(WIDTH - 162, HEIGHT - TASKBAR / 2 - 11, 22, 22)
""" Her face by the clock, which opens her menu. """
FILES: tuple[str, ...] = (
	"actions.py", "app.py", "config.py", "i18n.py", "mcp.py", "report.py", "session.py", "overlay", "services", "voice",
)


# Classes
@dataclass(frozen=True)
class Desktop:
	""" The desktop in three layers, as vectors to stay sharp when zoomed. The terminal in between is minimized during the video. """
	windows: QPicture
	terminal: QPicture
	taskbar: QPicture


# Functions
def font(size: float, weight: QFont.Weight = QFont.Weight.Normal, family: str = UI) -> QFont:
	shown = QFont(family)
	shown.setPixelSize(round(size))
	shown.setWeight(weight)
	return shown


def wallpaper(scale: float) -> QImage:
	""" A dark gradient lit by soft colored glows, `scale` times the video's size so the camera can zoom in on it. """
	image = QImage(round(WIDTH * scale), round(HEIGHT * scale), QImage.Format.Format_RGB32)
	painter = QPainter(image)
	painter.scale(scale, scale)
	sky = QLinearGradient(0, 0, WIDTH, HEIGHT)
	sky.setColorAt(0, QColor(20, 22, 44))
	sky.setColorAt(1, QColor(52, 28, 58))
	painter.fillRect(QRectF(0, 0, WIDTH, HEIGHT), sky)
	glows = (
		(QPointF(0.2, 0.2), 0.5, QColor(217, 119, 87, 80)), (QPointF(0.88, 0.12), 0.38, QColor(120, 90, 210, 70)),
		(QPointF(0.72, 0.95), 0.5, QColor(236, 138, 150, 60)), (QPointF(0.04, 0.92), 0.32, QColor(70, 120, 220, 55)),
	)
	for center, radius, color in glows:
		light = QRadialGradient(QPointF(center.x() * WIDTH, center.y() * HEIGHT), radius * WIDTH)
		light.setColorAt(0, color)
		light.setColorAt(1, QColor(color.red(), color.green(), color.blue(), 0))
		painter.fillRect(QRectF(0, 0, WIDTH, HEIGHT), light)
	painter.end()
	return image


def desktop() -> Desktop:
	""" An editor on the code of the actions, the terminal ClaudeChan started from, and the taskbar. """
	pictures: list[QPicture] = []
	for draw in (editor, terminal, taskbar):
		picture = QPicture()
		painter = QPainter(picture)
		painter.setRenderHint(QPainter.RenderHint.Antialiasing)
		draw(painter)
		painter.end()
		pictures.append(picture)
	return Desktop(*pictures)


def window(painter: QPainter, frame: QRectF, title: str, body: QColor) -> QRectF:
	""" A window with its shadow, title bar and buttons, returning the area under its title bar. """
	painter.setPen(Qt.PenStyle.NoPen)
	for spread in range(1, 16):
		painter.setBrush(QColor(0, 0, 0, 7))
		painter.drawRoundedRect(frame.adjusted(-spread, -spread + 6, spread, spread + 10), 10 + spread, 10 + spread)
	painter.setBrush(body)
	painter.drawRoundedRect(frame, 9, 9)
	bar = QRectF(frame.left(), frame.top(), frame.width(), 34)
	painter.setBrush(QColor(38, 39, 48))
	top = QPainterPath()
	top.addRoundedRect(bar.adjusted(0, 0, 0, 9), 9, 9)
	painter.save()
	painter.setClipRect(bar)
	painter.drawPath(top)
	painter.restore()
	painter.setFont(font(13))
	painter.setPen(QColor(200, 200, 210))
	painter.drawText(bar, Qt.AlignmentFlag.AlignCenter, title)
	painter.setPen(QPen(QColor(190, 190, 200), 1.2))
	right = bar.right() - 24
	painter.drawLine(QPointF(right - 6, bar.center().y() - 6), QPointF(right + 6, bar.center().y() + 6))
	painter.drawLine(QPointF(right - 6, bar.center().y() + 6), QPointF(right + 6, bar.center().y() - 6))
	painter.drawRect(QRectF(right - 52, bar.center().y() - 6, 12, 12))
	painter.drawLine(QPointF(right - 100, bar.center().y()), QPointF(right - 88, bar.center().y()))
	painter.setPen(QPen(QColor(255, 255, 255, 22), 1))
	painter.setBrush(Qt.BrushStyle.NoBrush)
	painter.drawRoundedRect(frame, 9, 9)
	return QRectF(frame.left(), bar.bottom(), frame.width(), frame.height() - bar.height())


def editor(painter: QPainter) -> None:
	area = window(painter, EDITOR_FRAME, "actions.py - ClaudeChan - Visual Studio Code", QColor(30, 31, 38))
	status = QRectF(area.left(), area.bottom() - 24, area.width(), 24)
	painter.fillRect(QRectF(area.left(), area.top(), 48, area.height() - 24), QColor(36, 37, 46))
	for row in range(4):
		painter.setPen(QPen(QColor(150, 150, 165) if row else WHITE, 1.6))
		painter.drawRoundedRect(QRectF(area.left() + 14, area.top() + 16 + 48 * row, 20, 20), 4, 4)
	painter.fillRect(QRectF(area.left(), area.top() + 10, 2, 32), WHITE)

	sidebar = QRectF(area.left() + 48, area.top(), 230, area.height() - 24)
	painter.fillRect(sidebar, QColor(26, 27, 33))
	painter.setFont(font(12, QFont.Weight.DemiBold))
	painter.setPen(QColor(170, 170, 185))
	painter.drawText(QPointF(sidebar.left() + 18, sidebar.top() + 26), "EXPLORER")
	painter.drawText(QPointF(sidebar.left() + 18, sidebar.top() + 56), "CLAUDECHAN")
	painter.setFont(font(14))
	for row, name in enumerate(("src/claudechan", *FILES, "tests", "README.md", "PLAN.md")):
		y = sidebar.top() + 70 + 26 * row
		nested = 0 < row <= len(FILES)
		if name == "actions.py":
			painter.fillRect(QRectF(sidebar.left(), y, sidebar.width(), 26), QColor(55, 58, 75))
		painter.setPen(QColor(220, 220, 230) if "." in name else QColor(170, 170, 185))
		painter.drawText(QPointF(sidebar.left() + (44 if nested else 24), y + 18), name)
		if name.endswith(".py"):
			painter.fillRect(QRectF(sidebar.left() + (30 if nested else 10), y + 9, 8, 8), QColor(80, 140, 220))

	tabs = QRectF(sidebar.right(), area.top(), area.right() - sidebar.right(), 36)
	painter.fillRect(tabs, QColor(24, 25, 31))
	for column, name in enumerate(("actions.py", "app.py")):
		tab = QRectF(tabs.left() + 150 * column, tabs.top(), 150, 36)
		if not column:
			painter.fillRect(tab, QColor(30, 31, 38))
			painter.fillRect(QRectF(tab.left(), tab.top(), tab.width(), 2), QColor(0, 122, 204))
		painter.setFont(font(14))
		painter.setPen(WHITE if not column else QColor(150, 150, 165))
		painter.drawText(tab, Qt.AlignmentFlag.AlignCenter, name)
	painter.setFont(font(13))
	painter.setPen(QColor(150, 150, 165))
	painter.drawText(QPointF(tabs.left() + 16, tabs.bottom() + 20), "src  >  claudechan  >  actions.py")
	code(painter, QRectF(tabs.left(), tabs.bottom() + 30, tabs.width(), status.top() - tabs.bottom() - 30))

	painter.fillRect(status, QColor(0, 122, 204))
	painter.setFont(font(13))
	painter.setPen(WHITE)
	painter.drawText(status.adjusted(12, 0, -12, 0), Qt.AlignmentFlag.AlignVCenter, "main")
	painter.drawText(status.adjusted(12, 0, -16, 0), RIGHT, "Python 3.14    UTF-8    LF")


def code(painter: QPainter, area: QRectF) -> None:
	""" The lines of `actions.py` around `SHOWN_CODE`, numbered and colored as VS Code shows them. """
	lines = (ROOT / "src" / "claudechan" / "actions.py").read_text(encoding="utf-8").splitlines()
	first = next(i for i, line in enumerate(lines) if line.startswith(SHOWN_CODE)) - 4
	mono = font(15, family=MONO)
	advance = QFontMetricsF(mono).horizontalAdvance
	painter.save()
	painter.setClipRect(area)
	painter.setFont(mono)
	for row in range(int(area.height() // 22)):
		y = area.top() + 22 * row
		if row == 6:
			painter.fillRect(QRectF(area.left(), y, area.width(), 22), QColor(40, 42, 54))
		painter.setPen(QColor(110, 112, 128) if row != 6 else QColor(200, 200, 210))
		painter.drawText(QRectF(area.left(), y, 48, 22), RIGHT, str(first + row + 1))
		text = lines[first + row].replace("\t", "    ")
		x, end = area.left() + 72, 0
		for token in TOKENS.finditer(text):
			for part, color in ((text[end:token.start()], CODE), (token.group(), SYNTAX[token.lastgroup or "call"])):
				painter.setPen(color)
				painter.drawText(QPointF(x, y + 16), part)
				x += advance(part)
			end = token.end()
		painter.setPen(CODE)
		painter.drawText(QPointF(x, y + 16), text[end:])
	painter.restore()


def terminal(painter: QPainter) -> None:
	area = window(painter, TERMINAL_FRAME, "PowerShell", QColor(12, 12, 16))
	painter.setFont(font(15, family=MONO))
	for row, (line, color) in enumerate(TERMINAL):
		painter.setPen(color)
		painter.drawText(QPointF(area.left() + 16, area.top() + 30 + 26 * row), line)
	cursor = QFontMetricsF(font(15, family=MONO)).horizontalAdvance(TERMINAL[-1][0])
	painter.fillRect(QRectF(area.left() + 16 + cursor, area.top() + 14 + 26 * (len(TERMINAL) - 1), 9, 20), CODE)


def taskbar(painter: QPainter) -> None:
	""" Windows 11's taskbar: centered app icons, the editor and the terminal open, and her tray icon by the clock. """
	bar = QRectF(0, HEIGHT - TASKBAR, WIDTH, TASKBAR)
	painter.fillRect(bar, QColor(28, 28, 36, 245))
	painter.fillRect(QRectF(0, bar.top(), WIDTH, 1), QColor(255, 255, 255, 24))
	icons = (start_icon, search_icon, folder_icon, editor_icon, terminal_icon, chat_icon, browser_icon)
	for i, icon in enumerate(icons):
		center = QPointF(WIDTH / 2 + 48 * (i - (len(icons) - 1) / 2), bar.center().y())
		icon(painter, center)
		if icon in (editor_icon, terminal_icon):
			painter.setPen(Qt.PenStyle.NoPen)
			painter.setBrush(QColor(200, 200, 210))
			painter.drawRoundedRect(QRectF(center.x() - 4, bar.bottom() - 5, 8, 3), 1.5, 1.5)

	painter.setPen(QPen(QColor(220, 220, 230), 1.4))
	arrow, middle = TRAY_ICON.left() - 18, bar.center().y()
	painter.drawPolyline([QPointF(arrow - 5, middle + 3), QPointF(arrow, middle - 2), QPointF(arrow + 5, middle + 3)])
	disc = QPainterPath()
	disc.addEllipse(TRAY_ICON)
	painter.save()
	painter.setClipPath(disc)
	painter.drawPixmap(TRAY_ICON, face(64), QRectF(0, 0, 64, 64))
	painter.restore()
	painter.setFont(font(13))
	painter.setPen(WHITE)
	clock = QRectF(WIDTH - 110, bar.top(), 96, TASKBAR)
	painter.drawText(clock.adjusted(0, 5, 0, -TASKBAR / 2), RIGHT, "14:32")
	painter.drawText(clock.adjusted(0, TASKBAR / 2 - 5, 0, 0), RIGHT, "13/10/2026")


def start_icon(painter: QPainter, center: QPointF) -> None:
	painter.setPen(Qt.PenStyle.NoPen)
	painter.setBrush(QColor(0, 120, 215))
	for dx, dy in ((-1, -1), (0, -1), (-1, 0), (0, 0)):
		painter.drawRoundedRect(QRectF(center.x() + 11 * dx + 0.5, center.y() + 11 * dy + 0.5, 10, 10), 1.5, 1.5)


def search_icon(painter: QPainter, center: QPointF) -> None:
	painter.setPen(QPen(QColor(220, 220, 230), 2))
	painter.setBrush(Qt.BrushStyle.NoBrush)
	painter.drawEllipse(center + QPointF(-2, -2), 7, 7)
	painter.drawLine(center + QPointF(3, 3), center + QPointF(8, 8))


def folder_icon(painter: QPainter, center: QPointF) -> None:
	painter.setPen(Qt.PenStyle.NoPen)
	painter.setBrush(QColor(232, 170, 40))
	painter.drawRoundedRect(QRectF(center.x() - 11, center.y() - 9, 10, 6), 2, 2)
	painter.setBrush(QColor(250, 200, 70))
	painter.drawRoundedRect(QRectF(center.x() - 11, center.y() - 6, 22, 16), 2.5, 2.5)


def editor_icon(painter: QPainter, center: QPointF) -> None:
	painter.setPen(Qt.PenStyle.NoPen)
	painter.setBrush(QColor(35, 140, 230))
	painter.drawRoundedRect(QRectF(center.x() - 11, center.y() - 11, 22, 22), 5, 5)
	painter.setPen(QPen(WHITE, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
	painter.drawPolyline([center + QPointF(-2, -5), center + QPointF(-7, 0), center + QPointF(-2, 5)])
	painter.drawPolyline([center + QPointF(2, -5), center + QPointF(7, 0), center + QPointF(2, 5)])


def terminal_icon(painter: QPainter, center: QPointF) -> None:
	painter.setPen(QPen(QColor(120, 120, 135), 1))
	painter.setBrush(QColor(30, 30, 38))
	painter.drawRoundedRect(QRectF(center.x() - 11, center.y() - 10, 22, 20), 4, 4)
	painter.setPen(QPen(WHITE, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
	painter.drawPolyline([center + QPointF(-6, -3), center + QPointF(-2, 0), center + QPointF(-6, 3)])
	painter.drawLine(center + QPointF(0, 4), center + QPointF(6, 4))


def chat_icon(painter: QPainter, center: QPointF) -> None:
	painter.setPen(Qt.PenStyle.NoPen)
	painter.setBrush(QColor(88, 101, 242))
	painter.drawRoundedRect(QRectF(center.x() - 11, center.y() - 11, 22, 22), 6, 6)
	painter.setBrush(WHITE)
	painter.drawEllipse(center + QPointF(-4, 0), 2.2, 2.6)
	painter.drawEllipse(center + QPointF(4, 0), 2.2, 2.6)


def browser_icon(painter: QPainter, center: QPointF) -> None:
	ring = QConicalGradient(center, 90)
	for stop, color in ((0.0, (234, 67, 53)), (0.33, (251, 188, 5)), (0.66, (52, 168, 83)), (1.0, (234, 67, 53))):
		ring.setColorAt(stop, QColor(*color))
	painter.setPen(Qt.PenStyle.NoPen)
	painter.setBrush(ring)
	painter.drawEllipse(center, 11, 11)
	painter.setBrush(WHITE)
	painter.drawEllipse(center, 5.5, 5.5)
	painter.setBrush(QColor(66, 133, 244))
	painter.drawEllipse(center, 4, 4)


def caption(painter: QPainter, who: str, language: str, text: str, said: float, level: float) -> None:
	""" What the user says, on a dark card under her bubble once the camera is on her.

	It shows who speaks, the language Whisper hears, and the words said so far.

	Args:
		said:  Share of the text said so far, from 0 to 1, shown a whole word at a time.
		level: Loudness of the voice for the microphone's rings, from 0 for silence to 1.
	"""
	words = font(30, QFont.Weight.DemiBold)
	width = max(360.0, QFontMetricsF(words).horizontalAdvance(text) + 150)
	card = QRectF(72, 600, width, 112)
	shadow(painter, card, 22)
	painter.setPen(QPen(QColor(255, 255, 255, 30), 1))
	painter.setBrush(QColor(16, 16, 24, 225))
	painter.drawRoundedRect(card, 22, 22)

	mic = QPointF(card.left() + 56, card.center().y())
	painter.setPen(Qt.PenStyle.NoPen)
	for ring in range(3):
		painter.setBrush(QColor(ACCENT.red(), ACCENT.green(), ACCENT.blue(), round(70 * level / (ring + 1))))
		painter.drawEllipse(mic, 26 + 7 * ring * level, 26 + 7 * ring * level)
	painter.setBrush(ACCENT)
	painter.drawEllipse(mic, 24, 24)
	painter.setPen(QPen(WHITE, 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
	painter.setBrush(WHITE)
	painter.drawRoundedRect(QRectF(mic.x() - 5, mic.y() - 13, 10, 17), 5, 5)
	painter.setBrush(Qt.BrushStyle.NoBrush)
	painter.drawArc(QRectF(mic.x() - 9, mic.y() - 8, 18, 16), 200 * 16, 140 * 16)
	painter.drawLine(mic + QPointF(0, 8), mic + QPointF(0, 12))

	left = card.left() + 104
	painter.setFont(font(15, QFont.Weight.Bold))
	painter.setPen(QColor(240, 160, 130))
	label = who.upper()
	painter.drawText(QPointF(left, card.top() + 36), label)
	badge = QRectF(left + QFontMetricsF(font(15, QFont.Weight.Bold)).horizontalAdvance(label) + 12, card.top() + 19, 36, 22)
	painter.setPen(QPen(QColor(240, 160, 130, 160), 1.2))
	painter.drawRoundedRect(badge, 6, 6)
	painter.setFont(font(12, QFont.Weight.Bold))
	painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, language.upper())
	units, glue = (text.split(" "), " ") if " " in text else (list(text), "")
	painter.setFont(words)
	painter.setPen(WHITE)
	painter.drawText(QPointF(left, card.top() + 82), glue.join(units[:math.ceil(len(units) * said)]))


def chapter_card(painter: QPainter, number: int, title: str, subtitle: str) -> None:
	""" The number, name and line of the chapter, right above her bubble once the camera is on her. """
	heading, line = font(40, QFont.Weight.DemiBold), font(21)
	width = max(QFontMetricsF(heading).horizontalAdvance(title), QFontMetricsF(line).horizontalAdvance(subtitle)) + 130
	card = QRectF(525, 170, width, 118)
	shadow(painter, card, 18)
	painter.setPen(Qt.PenStyle.NoPen)
	painter.setBrush(QColor(14, 14, 22, 215))
	painter.drawRoundedRect(card, 18, 18)
	painter.setBrush(ACCENT)
	painter.drawRoundedRect(QRectF(card.left() + 22, card.top() + 24, 5, card.height() - 48), 2.5, 2.5)
	painter.setFont(font(20, QFont.Weight.Bold))
	painter.setPen(QColor(240, 160, 130))
	painter.drawText(QPointF(card.left() + 46, card.top() + 50), f"{number:02d}")
	painter.setFont(heading)
	painter.setPen(WHITE)
	painter.drawText(QPointF(card.left() + 92, card.top() + 54), title)
	painter.setFont(line)
	painter.setPen(MUTED)
	painter.drawText(QPointF(card.left() + 92, card.top() + 90), subtitle)


def title_card(painter: QPainter, sprite: str, tagline: str, footer: tuple[str, ...], appeared: float) -> None:
	""" A full-screen card: her sprite on a glow, her name, a line under it, and footer lines, sliding in as `appeared` goes to 1. """
	painter.fillRect(QRectF(0, 0, WIDTH, HEIGHT), QColor(12, 10, 20, 225))
	glow = QRadialGradient(QPointF(1390, 560), 520)
	glow.setColorAt(0, QColor(ACCENT.red(), ACCENT.green(), ACCENT.blue(), 90))
	glow.setColorAt(1, QColor(ACCENT.red(), ACCENT.green(), ACCENT.blue(), 0))
	painter.fillRect(QRectF(0, 0, WIDTH, HEIGHT), glow)

	rise = 60 * (1 - ease(appeared))
	pixmap = QPixmap(str(ASSETS / f"{sprite}.png"))
	height = 760.0
	width = height * pixmap.width() / pixmap.height()
	painter.drawPixmap(QRectF(1390 - width / 2, HEIGHT - height + rise, width, height), pixmap, QRectF(pixmap.rect()))

	name = QPainterPath()
	name.addText(QPointF(150, 470 + rise / 2), font(132, QFont.Weight.Bold), "Claire")
	shine = QLinearGradient(150, 360, 900, 470)
	shine.setColorAt(0, QColor(255, 214, 186))
	shine.setColorAt(1, ACCENT)
	painter.setPen(Qt.PenStyle.NoPen)
	painter.setBrush(shine)
	painter.drawPath(name)
	painter.setFont(font(36))
	painter.setPen(WHITE)
	painter.drawText(QPointF(156, 550 + rise / 2), tagline)
	painter.setFont(font(24))
	painter.setPen(MUTED)
	for row, line in enumerate(footer):
		painter.setFont(font(26, family=MONO) if line.startswith("uv ") else font(24))
		painter.drawText(QPointF(156, 660 + 50 * row + rise / 2), line)


def shadow(painter: QPainter, card: QRectF, radius: float) -> None:
	painter.setPen(Qt.PenStyle.NoPen)
	for spread in range(1, 12):
		painter.setBrush(QColor(0, 0, 0, 9))
		painter.drawRoundedRect(card.adjusted(-spread, -spread + 4, spread, spread + 8), radius + spread, radius + spread)


def pointer(painter: QPainter, tip: QPointF, held: float | None) -> None:
	""" The mouse pointer, with a ring around its tip while its button is down that closes as a long press lets her be dragged.

	Args:
		held: Share of the long press done, from 0 to 1, or None while the button is up.
	"""
	if held is not None:
		ring = QRectF(tip.x() - 15, tip.y() - 15, 30, 30)
		painter.setPen(Qt.PenStyle.NoPen)
		painter.setBrush(QColor(ACCENT.red(), ACCENT.green(), ACCENT.blue(), 70))
		painter.drawEllipse(ring)
		painter.setPen(QPen(ACCENT, 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
		painter.setBrush(Qt.BrushStyle.NoBrush)
		painter.drawArc(ring, 90 * 16, round(-360 * 16 * held))
	arrow = QPainterPath(tip)
	for x, y in ((0, 25), (6, 19.5), (10, 28.5), (14, 26.8), (10, 18), (18, 18)):
		arrow.lineTo(tip + QPointF(x, y))
	arrow.closeSubpath()
	painter.setPen(QPen(QColor(10, 10, 14), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
	painter.setBrush(WHITE)
	painter.drawPath(arrow)


def ease(progress: float) -> float:
	""" Cubic ease-out of a progress clamped to 0 to 1, the curve of her slides.

	>>> ease(0.0), ease(1.0), ease(2.0)
	(0.0, 1.0, 1.0)
	"""
	return 1 - (1 - min(1.0, max(0.0, progress))) ** 3


def level(now: float) -> float:
	""" A voice's loudness at `now`, from 0.35 to 1, wavering like speech. """
	return 0.35 + 0.65 * abs(math.sin(9.1 * now) * math.sin(3.7 * now + 1.3))

