""" Renders a demo video of Claude-tan: a scripted run through her main features, drawn by the real overlay.

Nothing is run for real: no microphone, no session, no screenshot, no key press.
The beats feed `Assistant` the events it would get from them, and a manual clock steps the overlay.
The same script therefore always gives the same video.

Run with `uv run scripts/demo_video.py`, which needs ffmpeg on the PATH.
Options: --out, --fps, --size, and --background for an image of a desktop, such as a screenshot, instead of the generated one.
"""
# Imports
import argparse
import random
import subprocess
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath
from PySide6.QtWidgets import QApplication

import claudetan.app
import claudetan.config
from claudetan.app import Assistant
from claudetan.config import DEFAULTS, ROOT, Config
from claudetan.overlay.avatar import Avatar, Pill
from claudetan.overlay.effects import burst
from claudetan.report import Report, Slice

# Constants
NEWLINE: str = chr(10)
CAPTION_S: float = 2.8
""" How long what the user says stays on screen. """
FADE_S: float = 0.3
BLINKS: tuple[float, ...] = (4.2, 11.6, 19.1, 27.4, 35.8, 44.3, 52.9, 61.5, 69.8)
""" When she blinks, since the real blinks come from a timer that would make every video different. """
SAMPLE_REPORT: Report = Report(
	"Contexte : 330,3k / 1m (33" + chr(0xA0) + "%)" + NEWLINE + "Modèle : claude-sonnet-5-5",
	tuple(
		Slice(key=key, label=label, amount=amount, share=share + chr(0xA0) + "%", fraction=float(share.replace(",", ".")) / 100)
		for key, label, amount, share in (
			("Messages", "Messages", "290,6k", "29,1"), ("System tools", "Outils", "20,6k", "2,1"),
			("Memory files", "Mémoire", "8,6k", "0,9"), ("Skills", "Skills", "6,4k", "0,6"),
			("System prompt", "Prompt", "3,4k", "0,3"),
			("Autocompact buffer", "Compactage", "33k", "3,3"), ("Free space", "Libre", "636,7k", "63,7"),
		)
	),
)
""" What `/context` reports in the middle of a long conversation. """
REPLY: str = (
	"Sur ton écran 1, tu es dans Minecraft, dans une grande bibliothèque avec un scoreboard à droite. "
	"Sur ton écran 2, Discord est ouvert sur le salon de la voix off, avec ton partage d'écran en cours."
	+ NEWLINE
	+ "Si tu veux que je lise un message en particulier, dis-moi de qui il vient et je le retrouve."
)


# Classes
@dataclass(frozen=True)
class Beat:
	""" Something that happens at `at` seconds, with what the user says at that moment shown as a caption. """
	at: float
	says: str = ""
	do: Callable[[Assistant], None] | None = None
	hide: bool = False
	""" She leaves the screen. """


@dataclass
class Stage:
	""" What the video shows at the moment: her, since when she is on screen, and what the user says. """
	assistant: Assistant
	avatar: Avatar
	visible: bool = False
	shown_at: float = 0.0
	says: str = ""
	said_at: float = -99.0

	def play(self, beat: Beat, now: float) -> None:
		if beat.says:
			self.says, self.said_at = beat.says, now
		if beat.do:
			if not self.visible:
				self.pop_in(now)
			beat.do(self.assistant)
		self.visible = self.visible and not beat.hide

	def pop_in(self, now: float) -> None:
		self.visible, self.shown_at = True, now
		self.avatar.popped_at = now
		self.avatar.sparks = burst(self.avatar.face_center(), now, count=14)

	def blink(self, now: float) -> None:
		closed = f"{self.avatar.expression}_blink"
		blinking = any(0 <= now - at < 0.13 for at in BLINKS) and closed in self.avatar.sprites
		self.avatar.frame = closed if blinking else self.avatar.expression

	def draw(self, painter: QPainter, now: float, spot: QPointF, size: tuple[int, int]) -> None:
		painter.setOpacity(min(1.0, (now - self.shown_at) / FADE_S) if self.visible else 0.0)
		painter.drawPixmap(spot, self.avatar.grab())
		age = now - self.said_at
		if self.says and 0 <= age < CAPTION_S:
			caption(painter, self.says, min(1.0, age / 0.2, (CAPTION_S - age) / 0.2), size)


class Clock:
	""" The time of the video, which the overlay reads instead of the real one. """
	seconds: float = 0.0


# Functions
def silent(*_notes: float) -> None:
	""" Stands for her chimes, which would play during the rendering. """


def hook(name: str, **fields: object) -> dict[str, object]:
	return {"hook_event_name": name, **fields}


def ask_permission(assistant: Assistant) -> None:
	assistant.on_hook(hook("PermissionRequest", tool_name="Bash", tool_input={"command": "git push origin main"}))
	assistant.on_permission_asked(Future())


def tool(description: str) -> Callable[[Assistant], None]:
	use = hook("PreToolUse", tool_name="Bash", tool_input={"command": "...", "description": description})
	return lambda assistant: assistant.on_hook(use)


def say(text: str) -> Callable[[Assistant], None]:
	return lambda assistant: assistant.on_announce(text)


def beats() -> list[Beat]:
	""" The scenario: a request by voice, a few local actions, a permission and the context. """
	prompt = "Qu'est-ce qu'il y a sur mes écrans ?"
	return [
		Beat(at=1.0, says="Hé Claude", do=Assistant.on_wake),
		Beat(at=2.8, says=prompt, do=lambda assistant: assistant.on_dictation(prompt.lower())),
		Beat(at=5.8, says="Terminé", do=lambda assistant: assistant.on_hook(hook("UserPromptSubmit", prompt=prompt))),
		Beat(at=7.5, do=tool("Take a screenshot of each monitor")),
		Beat(at=9.0, do=tool("Read the captures")),
		Beat(at=10.8, do=lambda assistant: assistant.on_hook(hook("Stop", last_assistant_message=REPLY))),
		Beat(at=24.0, hide=True),
		Beat(at=25.5, says="Capture l'écran 2", do=say("Capture de l'écran 2 enregistrée dans Images" + chr(92) + "Screenshots.")),
		Beat(at=29.5, hide=True),
		Beat(at=30.5, says="Mets un minuteur de 8 secondes", do=say("Minuteur de 8 s lancé.")),
		Beat(at=34.5, hide=True),
		Beat(at=38.5, do=lambda assistant: assistant.on_alarm("les pâtes")),
		Beat(at=43.0, hide=True),
		Beat(at=44.0, says="Passe en Opus", do=say("Je passe en opus.")),
		Beat(at=47.5, hide=True),
		Beat(at=48.5, do=ask_permission),
		Beat(at=51.5, says="Oui", do=lambda assistant: assistant.on_verdict(allowed=True)),
		Beat(at=55.0, hide=True),
		Beat(at=56.0, says="Quel est le contexte ?", do=lambda assistant: assistant.on_announce(SAMPLE_REPORT)),
		Beat(at=64.0, hide=True),
		Beat(at=65.0, says="Quel temps fait-il à Rennes ?", do=say("Rennes : plutôt dégagé, 15 °C (ressenti 14), vent 7 km/h.")),
		Beat(at=70.0, hide=True),
	]


def background(size: tuple[int, int], image: Path | None) -> QImage:
	""" A dark desktop with a few windows, or the image given, scaled to the video. """
	width, height = size
	if image:
		wallpaper = QImage(str(image))
		fill, smooth = Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation
		return wallpaper.scaled(width, height, fill, smooth)

	desktop = QImage(width, height, QImage.Format.Format_RGB888)
	painter = QPainter(desktop)
	painter.setRenderHint(QPainter.RenderHint.Antialiasing)
	sky = QLinearGradient(0, 0, width, height)
	sky.setColorAt(0, QColor(30, 34, 58))
	sky.setColorAt(1, QColor(74, 44, 70))
	painter.fillRect(desktop.rect(), sky)
	for x, y, w, h in ((0.06, 0.1, 0.5, 0.62), (0.34, 0.2, 0.46, 0.55)):
		window = QPainterPath()
		window.addRoundedRect(QRectF(x * width, y * height, w * width, h * height), 14, 14)
		painter.fillPath(window, QColor(24, 26, 34, 235))
		painter.fillRect(QRectF(x * width, y * height, w * width, 34), QColor(40, 44, 58, 255))
		for line in range(14):
			length = w * width * (0.2 + 0.5 * ((line * 37) % 10) / 10)
			painter.fillRect(QRectF((x + 0.02) * width, (y + 0.08) * height + 30 * line, length, 10), QColor(90, 100, 130, 120))
	painter.end()
	return desktop


def caption(painter: QPainter, text: str, opacity: float, size: tuple[int, int]) -> None:
	""" What the user says, on a dark pill at the bottom of the screen. """
	painter.save()
	painter.setOpacity(opacity)
	painter.setFont(QFont("Segoe UI", 20))
	shown = f"Toi : « {text} »"
	width = painter.fontMetrics().horizontalAdvance(shown) + 60
	pill = QPainterPath()
	pill.addRoundedRect(QRectF((size[0] - width) / 2, size[1] - 110, width, 52), 26, 26)
	painter.fillPath(pill, QColor(0, 0, 0, 170))
	painter.setPen(QColor(255, 255, 255))
	painter.drawText(pill.boundingRect(), Qt.AlignmentFlag.AlignCenter, shown)
	painter.restore()


def render(output: Path, fps: int, size: tuple[int, int], image: Path | None) -> None:
	random.seed(7)
	clock = Clock()
	def now(_avatar: Avatar) -> float:
		return clock.seconds

	with patch.object(Avatar, "now", now):
		play(output, fps, size, image, clock)


def play(output: Path, fps: int, size: tuple[int, int], image: Path | None, clock: Clock) -> None:
	scenario = beats()
	total = round((scenario[-1].at + 2.0) * fps)
	desktop = background(size, image)
	avatar = Avatar()
	avatar.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
	avatar.show()
	avatar.blink.stop()
	stage = Stage(Assistant(avatar, Pill(), Config.load()), avatar)
	spot = QPointF(size[0] - avatar.width() - 40, size[1] - avatar.height() - 40)

	frames = ["-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{size[0]}x{size[1]}", "-r", str(fps), "-i", "-"]
	ffmpeg = subprocess.Popen(
		["ffmpeg", "-y", "-loglevel", "error", *frames, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", str(output)],
		stdin=subprocess.PIPE,
	)
	assert ffmpeg.stdin
	for index in range(total):
		clock.seconds = index / fps
		while scenario and scenario[0].at <= clock.seconds:
			stage.play(scenario.pop(0), clock.seconds)
		stage.blink(clock.seconds)
		avatar.tick()

		frame = QImage(desktop)
		painter = QPainter(frame)
		painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
		stage.draw(painter, clock.seconds, spot, size)
		painter.end()
		ffmpeg.stdin.write(bytes(frame.convertToFormat(QImage.Format.Format_RGB888).constBits()))
	ffmpeg.stdin.close()
	ffmpeg.wait()
	print(f"{output}: {total / fps:.0f} s at {fps} fps, {size[0]}x{size[1]}")


def main() -> None:
	parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
	parser.add_argument("--out", type=Path, default=ROOT / "dist" / "demo.mp4")
	parser.add_argument("--fps", type=int, default=30)
	parser.add_argument("--size", default="1920x1080")
	parser.add_argument("--background", type=Path)
	args = parser.parse_args()
	width, height = map(int, args.size.split("x"))
	args.out.parent.mkdir(parents=True, exist_ok=True)

	app = QApplication([])
	app.setQuitOnLastWindowClosed(False)
	with patch.object(claudetan.config, "USER_CONFIG", DEFAULTS), patch.object(claudetan.app, "chime", silent):
		render(args.out, args.fps, (width, height), args.background)


if __name__ == "__main__":
	main()

