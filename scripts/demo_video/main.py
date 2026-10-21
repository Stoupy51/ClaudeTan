""" Renders the demo video of Claude-tan from `screenplay.py`.

Nothing runs for real: no microphone, no Claude session, no network call.
The screenplay feeds the real listener what Whisper would hear and the real `Assistant` the hook events Claude Code would post,
and a clock steps the overlay frame by frame, so the same script always gives the same video.
Her voice plays the clips of `voice/`, which only a line never said before needs AivisSpeech running to synthesize.

Run with `uv run scripts/demo_video/main.py`, which needs ffmpeg on the PATH and writes `dist/demo.mp4`,
and `dist/demo_small.mp4` under the 10 MB GitHub takes for the README.
`--stills 12 30.5` saves the frames at those seconds as PNG images instead, to check a change in a few seconds.
"""
# Imports
import argparse
import math
import random
import subprocess
import tempfile
import wave
from concurrent.futures import Future
from contextlib import ExitStack
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar, override
from unittest.mock import patch

import numpy as np
from mouse import Gesture, Move
from PySide6.QtCore import QAbstractAnimation, QEvent, QPoint, QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QLinearGradient, QMouseEvent, QPainter, QRegion, QTransform
from PySide6.QtWidgets import QApplication, QWidget
from scenery import (
	HEIGHT,
	TASKBAR,
	TERMINAL_FRAME,
	TERMINAL_ICON,
	TRAY_ICON,
	WIDTH,
	caption,
	chapter_card,
	desktop,
	ease,
	level,
	pointer,
	title_card,
	wallpaper,
)
from screenplay import (
	JAPANESE_REPLY,
	WHISPER_S,
	Cue,
	Drag,
	Frame,
	Hook,
	Leave,
	Outro,
	Read,
	Speak,
	Title,
	Tune,
	Words,
	reading_s,
	screenplay,
	speaking_s,
)
from spoken import Clip, clips
from stouputils.typing import JsonDict
from words import ENGLISH

import claudetan.app
import claudetan.config
import claudetan.voice.listener
from claudetan import i18n
from claudetan.app import Assistant
from claudetan.config import DEFAULTS, ROOT, Config
from claudetan.overlay import avatar as avatar_module, tray as tray_module
from claudetan.overlay.avatar import CHIME_RATE, LONG_PRESS_MS, PILL_SIZE, SPRITE_HEIGHT, SPRITE_TOP, Avatar, Pill, bell
from claudetan.overlay.menu import HOVER_MS, SHOW_MS, Slider, slider_track
from claudetan.voice.listener import Listener

# Constants
FPS: int = 60
SMALL_BYTES: int = 9_500_000
""" Size budget of `demo_small.mp4`, which GitHub takes up to 10 MB. """
ZOOM: float = 2.2
""" How many times larger than on a screen the overlay is drawn, as much as the camera zooms in on her. """
PILL_ZOOM: float = 2.6
HER_SHOT: float = 2.2
LINGER_S: float = 1.0
""" How long the camera stays on her once she leaves, in case she comes right back. """
SPRING: float = 6.0
""" Stiffness of the camera, in radians per second: it settles on a new shot in under a second, without overshooting it. """
SLIDE_S: float = 0.26
SLIDE_PX: float = 40.0
""" Her slide in and out of the screen, as `Avatar.pop_in` animates it. """
BLINK_S: float = 0.13
INTRO_S: float = 1.8
MINIMIZE_S: float = 2.2
""" When the terminal ClaudeTan started from is minimized, right after the intro. """
CARD_S: float = 3.0
""" How long a chapter card stays up. """
CAPTION_S: float = 0.8
""" How long the user's words stay up once said. """
CHORDS: tuple[tuple[float, ...], ...] = (
	(130.81, 261.63, 329.63, 392.00, 493.88), (110.00, 261.63, 329.63, 392.00, 440.00),
	(87.31, 261.63, 349.23, 440.00, 523.25), (98.00, 246.94, 293.66, 392.00, 440.00),
)
""" The soft pad under the video, in Hz: Cmaj7, Am7, Fmaj7 and G6, in the key of her chimes. """
CHORD_S: float = 4.8
VOICE_DELAY_S: float = 0.5
""" How long after her reply her voice starts, the time the translator and the engine take to say its first sentence. """
VOICE_LEVEL: float = 0.3
""" Her voice's loudness in the mix, its clips peaking at full scale and `write_wav` doubling the mix. """
DUCKED: float = 0.35
""" The pad's loudness under her voice. """
DUCK_S: float = 0.25
""" How long the pad takes to duck under her voice and to come back. """


# Classes
class Clock:
	""" The time of the video, which the overlay, the listener and the timers read instead of the real one. """
	seconds: float = 0.0


class ClockTimer(QTimer):
	""" A single-shot `QTimer` that times out on the video's clock, when `ClockTimer.ring` passes its deadline. """
	deadlines: ClassVar[dict[ClockTimer, float]] = {}

	@override
	def start(self, msec: int | None = None) -> None:
		ClockTimer.deadlines[self] = Clock.seconds + (self.interval() if msec is None else msec) / 1000

	@override
	def stop(self) -> None:
		ClockTimer.deadlines.pop(self, None)

	@staticmethod
	def ring() -> None:
		for timer, deadline in sorted(ClockTimer.deadlines.items(), key=lambda item: item[1]):
			if deadline <= Clock.seconds and ClockTimer.deadlines.get(timer) == deadline:
				del ClockTimer.deadlines[timer]
				timer.timeout.emit()


@dataclass(frozen=True)
class Grab:
	""" A press on her or on her pill, which drags it once held for `LONG_PRESS_MS`, as the overlay does. """
	pill: bool
	pointer: QPointF
	origin: QPointF
	""" Her top-left corner, or the pill's bottom-right one, when pressed. """
	since: float

	def dragging(self, now: float) -> bool:
		return now - self.since >= LONG_PRESS_MS / 1000


@dataclass(frozen=True)
class Shot:
	center: QPointF
	zoom: float
	spring: float = SPRING
	""" How stiffly the camera is pulled to the shot, in radians per second. """


class Camera:
	""" A spring pulling the view toward a shot, on its center and on the logarithm of its zoom. """

	def __init__(self) -> None:
		self.position = np.array([WIDTH / 2, HEIGHT / 2, 0.0])
		self.velocity = np.zeros(3)

	def follow(self, shot: Shot, seconds: float) -> None:
		target = np.array([shot.center.x(), shot.center.y(), math.log(shot.zoom)])
		self.velocity += (shot.spring**2 * (target - self.position) - 2 * shot.spring * self.velocity) * seconds
		self.position += self.velocity * seconds

	def zoom(self) -> float:
		return math.exp(self.position[2])

	def transform(self) -> QTransform:
		""" From the desktop to the video, the view kept inside the desktop. """
		zoom = self.zoom()
		half_width, half_height = WIDTH / zoom / 2, HEIGHT / zoom / 2
		x = min(max(float(self.position[0]), half_width), WIDTH - half_width)
		y = min(max(float(self.position[1]), half_height), HEIGHT - half_height)
		return QTransform().translate(WIDTH / 2, HEIGHT / 2).scale(zoom, zoom).translate(-x, -y)


class Studio:
	""" One video in the making: the app's objects on a desktop, the camera, and the sounds they make. """

	def __init__(self, words: Words, stack: ExitStack) -> None:
		""" Sets up the app as `run` does, with every I/O it would do replaced for the time of `stack`. """
		self.words = words
		self.timeline = screenplay(words)
		self.cues = list(self.timeline.cues)
		self.end = self.timeline.now
		""" When the video ends, which each `Read` pushes back. """
		self.sounds: list[tuple[float, np.ndarray[tuple[int], np.dtype[np.float32]]]] = []
		self.sent: list[str] = []
		self.said: tuple[Speak, float] | None = None
		self.titled: tuple[Title, float] | None = None
		self.outro_at: float | None = None
		self.slide = (0.0, 0.0, 0.0)
		""" Her opacity at the start of her last slide, the one it goes to, and when it started. """
		self.ducks: list[tuple[float, float]] = []
		""" When her voice starts and stops saying each line, which the pad ducks under. """
		self.voice_end = 0.0
		self.gesture = Gesture(0.0, QPointF(1250, 560), ())
		self.point, self.held = self.gesture.origin, False
		self.grab: Grab | None = None
		self.pointer_since = 0.0
		""" When the pointer last came into sight. """
		self.pill_corner: QPointF | None = None
		""" Where the pill was dropped, its bottom-right corner, None for her own corner, which it shows at until dragged. """
		self.menu_since: float | None = None
		""" When the menu last started opening or closing, None while it is closed. """
		self.menu_direction = QAbstractAnimation.Direction.Forward
		self.glide_since = 0.0
		Clock.seconds = 0.0
		ClockTimer.deadlines.clear()
		random.seed(7)
		blink = random.Random(7)
		self.blinks = [2.0 + sum(blink.uniform(2.5, 6.0) for _ in range(i)) for i in range(60)]

		stack.enter_context(patch.object(claudetan.config, "USER_CONFIG", DEFAULTS))
		stack.enter_context(patch.object(claudetan.app, "QTimer", ClockTimer))
		stack.enter_context(patch.object(avatar_module, "chime", self.chime))
		stack.enter_context(patch.object(claudetan.voice.listener, "time", SimpleNamespace(monotonic=lambda: Clock.seconds)))
		stack.enter_context(patch.object(Avatar, "now", video_time))
		stack.enter_context(patch.object(i18n, "heard", "en"))
		stack.enter_context(patch.object(tray_module, "starts_with_windows", lambda: True))

		config = Config.load()
		self.volume = config.volume
		self.voiced = {
			"".join(words.reply): words.spoken_reply, words.cleaned: words.spoken_cleaned, words.handed_off: words.spoken_handed_off,
			words.dark_mode_done: words.spoken_dark_mode_done, words.tests_done: words.spoken_tests_done,
			"".join(JAPANESE_REPLY): "".join(JAPANESE_REPLY),
		}
		""" Her replies in the Japanese her voice says them in. Her permission request stays silent, to keep the video short. """
		self.frame: Frame | None = None
		self.avatar = Avatar(ZOOM, ZOOM)
		self.pill = Pill(PILL_ZOOM)
		for widget in (self.avatar, self.pill):
			widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
		self.avatar.blink.stop()
		self.assistant = Assistant(self.avatar, self.pill, config)
		self.assistant.send.connect(self.sent.append)
		self.assistant.speak.connect(self.say)
		self.tray = tray_module.Tray(config.volume)
		self.tray.volume_changed.connect(partial(setattr, self, "volume"))
		self.listener = Listener(config)
		# Not `woke`: each request is said in one breath with the wake phrase, so its own bubble would replace her "Yes?" at once
		self.listener.dictated.connect(self.assistant.on_dictation)
		self.listener.heard.connect(self.assistant.on_command)
		self.listener.answered.connect(self.assistant.on_verdict)
		self.assistant.listening_for_answer.connect(lambda: setattr(self.listener, "asking", True))
		self.assistant.answer_settled.connect(lambda: setattr(self.listener, "asking", False))

		self.size = QPointF(self.avatar.width(), self.avatar.height()) / ZOOM
		self.spot = QPointF(WIDTH, HEIGHT - TASKBAR) - self.size
		self.camera = Camera()
		self.wallpaper = wallpaper(scale=HER_SHOT)
		self.desktop = desktop()

	def render(self, output: Path) -> None:
		""" Writes the video with its soundtrack, encoded for any player at 1080p and `FPS` frames per second. """
		frames = 0
		with tempfile.TemporaryDirectory(dir=output.parent) as folder:
			video, audio = Path(folder) / "video.mkv", Path(folder) / "audio.wav"
			encoder = subprocess.Popen([
				"ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr0", "-s", f"{WIDTH}x{HEIGHT}", "-r", str(FPS),
				"-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-tune", "animation",
				"-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
				"-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", str(video),
			], stdin=subprocess.PIPE)
			assert encoder.stdin
			while frames / FPS < self.end:
				self.step(frames / FPS)
				# Named, since the bits `constBits` points to are freed with an image nothing holds
				frame = self.draw()
				encoder.stdin.write(frame.constBits())
				frames += 1
			encoder.stdin.close()
			encoder.wait()
			write_wav(audio, self.soundtrack(frames / FPS))
			subprocess.run([
				"ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-i", str(audio),
				"-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
				"-movflags", "+faststart", "-shortest", str(output),
			], check=True)
		# Same 1080p and frame rate, with the video bitrate capped so that the whole file fits the 9.5 MB under GitHub's 10
		small = output.with_stem(f"{output.stem}_small")
		video_kbps = int(SMALL_BYTES * 8 / 1000 / (frames / FPS)) - 96
		subprocess.run([
			"ffmpeg", "-y", "-loglevel", "error", "-i", str(output),
			"-c:v", "libx264", "-preset", "slow", "-crf", "23", "-maxrate", f"{video_kbps}k", "-bufsize", f"{2 * video_kbps}k",
			"-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(small),
		], check=True)
		print(f"{output}: {frames / FPS:.1f} s at {FPS} fps, {WIDTH}x{HEIGHT}, and {small}: {small.stat().st_size / 1e6:.1f} MB")

	def stills(self, moments: list[float], folder: Path) -> None:
		""" Saves the frames at those seconds, stepping through the others without drawing them. """
		for index in range(round(max(moments) * FPS) + 1):
			self.step(index / FPS)
			if any(round(moment * FPS) == index for moment in moments):
				path = folder / f"demo_{index / FPS:06.2f}.png"
				self.draw().save(str(path))
				print(path)

	def step(self, now: float) -> None:
		""" Moves everything to `now`: the cues due, the timers, her blinks and slides, and the camera. """
		Clock.seconds = now
		ClockTimer.ring()
		while self.cues and self.cues[0][0] <= now:
			self.play(self.cues.pop(0)[1])
		self.blink()
		self.avatar.tick()
		self.follow_slide()
		self.follow_pointer(now)
		self.follow_menu(now)
		self.pill.angle = round(-8 * now / 0.03) % 360
		self.camera.follow(self.shot(), 1 / FPS)

	def play(self, cue: Cue) -> None:
		match cue:
			case Speak():
				self.said = (cue, Clock.seconds)
				self.later(speaking_s(cue.text) + WHISPER_S, lambda: self.listener.hear(cue.text, cue.language, ended=True))
			case Hook():
				self.post(cue.event)
			case Leave():
				self.assistant.leave()
			case Read():
				hold = max(reading_s(self.avatar.bubble.text), self.voice_end - Clock.seconds) + cue.longer_s
				self.cues = [(at + hold, later) for at, later in self.cues]
				self.end += hold
			case Drag():
				self.drag(cue)
			case Tune():
				self.tune(cue)
			case Frame():
				self.frame = cue
			case Title():
				self.titled = (cue, Clock.seconds)
			case Outro():
				self.outro_at = Clock.seconds

	def post(self, event: JsonDict) -> None:
		""" Hands the event to her as the hook server does, a prompt being the command she last typed unless the event names one. """
		if event["hook_event_name"] == "UserPromptSubmit":
			event = {"prompt": self.sent[-1], **event}
		self.assistant.on_hook(event)
		if event["hook_event_name"] == "PermissionRequest":
			self.assistant.on_permission_asked(Future())

	def later(self, seconds: float, callback: object) -> None:
		timer = ClockTimer()
		timer.timeout.connect(callback)
		timer.start(round(seconds * 1000))

	def say(self, text: str, style: int) -> None:
		""" Has her voice say a line of `voiced` as `Voice` does, each sentence moving her mouth as it starts. """
		if (japanese := self.voiced.get(text)) is None:
			return
		start = at = Clock.seconds + VOICE_DELAY_S
		for clip in clips(japanese, style):
			self.later(at - Clock.seconds, partial(self.speak, clip))
			self.sounds.append((at, clip.sound * np.float32(VOICE_LEVEL * self.volume)))
			at += len(clip.sound) / CHIME_RATE
		self.ducks.append((start, at))
		self.voice_end = at

	def speak(self, clip: Clip) -> None:
		self.avatar.speak(clip.vowels)
		self.assistant.on_speaking(clip.vowels)

	def drag(self, cue: Drag) -> None:
		""" Has the pointer long-press her chest, or the middle of her pill while it is up, and drag it. """
		her = self.her_rect()
		grip = self.pill_rect().center() if self.pill.isVisible() else QPointF(her.center().x(), her.top() + 0.72 * her.height())
		hold = LONG_PRESS_MS / 1000 + 0.1
		drop = grip + QPointF(*cue.by)
		self.point_at(
			Move(grip, 0.45, held=False), Move(grip, hold, held=True),
			Move(drop, cue.seconds - 0.65 - hold, held=True), Move(drop, 0.2, held=False),
		)

	def tune(self, cue: Tune) -> None:
		""" Has the pointer click her tray icon, drag the volume slider of the menu, and click away from it. """
		menu = self.tray.menu
		corner = menu.place(TRAY_ICON.toRect(), QRect(0, 0, WIDTH, round(HEIGHT - TASKBAR))).toPointF()
		slider, row = next((row, rect) for row, rect in menu.rows if isinstance(row, Slider))
		track = slider_track(row).translated(corner)
		knob = QPointF(track.left() + track.width() * slider.value, track.center().y())
		turned = QPointF(track.left() + track.width() * cue.volume, knob.y())
		away = corner + QPointF(menu.box.left() - 160, menu.box.center().y())
		icon = TRAY_ICON.center()
		self.point_at(
			Move(icon, 0.5, held=False), Move(icon, 0.1, held=True), Move(icon, 0.3, held=False),
			Move(knob, 0.5, held=False), Move(knob, 0.1, held=True), Move(turned, 0.65, held=True), Move(turned, 0.2, held=False),
			Move(away, 0.4, held=False), Move(away, 0.1, held=True), Move(away, 0.15, held=False),
		)

	def point_at(self, *moves: Move) -> None:
		if Clock.seconds > self.gesture.end() + 1.0:
			self.pointer_since = Clock.seconds
		self.gesture = Gesture(Clock.seconds, self.point, moves)

	def follow_pointer(self, now: float) -> None:
		""" Moves the pointer along its gesture, the menu and the drag of her or her pill following it as they do the mouse. """
		point, held = self.gesture.at(now)
		if self.menu_since is not None:
			self.send(QEvent.Type.MouseMove, point)

		if held and not self.held:
			self.press(point, now)
		elif self.held and not held:
			self.release(point)
		self.point, self.held = point, held

		if self.grab and self.grab.dragging(now):
			moved = self.grab.origin + point - self.grab.pointer
			if self.grab.pill:
				self.pill_corner = moved
			else:
				self.spot = moved

	def press(self, point: QPointF, now: float) -> None:
		if self.menu_since is not None:
			self.send(QEvent.Type.MouseButtonPress, point)
		elif self.pill.isVisible() and self.pill_rect().contains(point):
			self.grab = Grab(pill=True, pointer=point, origin=self.pill_at(), since=now)
		elif self.avatar.isVisible() and self.her_rect().contains(point):
			self.grab = Grab(pill=False, pointer=point, origin=self.spot, since=now)

	def release(self, point: QPointF) -> None:
		""" Drops what the pointer dragged, or opens the menu on a click on her tray icon, as `Tray.on_activated` does. """
		self.grab = None
		if self.menu_since is not None:
			self.send(QEvent.Type.MouseButtonRelease, point)
		elif TRAY_ICON.contains(point):
			menu = self.tray.menu
			menu.move(menu.place(TRAY_ICON.toRect(), QRect(0, 0, WIDTH, round(HEIGHT - TASKBAR))))
			menu.appear.setDirection(QAbstractAnimation.Direction.Forward)
			self.menu_since, self.menu_direction = Clock.seconds, QAbstractAnimation.Direction.Forward

	def send(self, kind: QEvent.Type, point: QPointF) -> None:
		""" Hands the menu the mouse event its popup gets with the pointer at `point` on the desktop. """
		menu = self.tray.menu
		button = Qt.MouseButton.NoButton if kind == QEvent.Type.MouseMove else Qt.MouseButton.LeftButton
		event = QMouseEvent(kind, point - menu.pos().toPointF(), point, button, button, Qt.KeyboardModifier.NoModifier)
		hovered = menu.hovered
		match kind:
			case QEvent.Type.MouseButtonPress:
				menu.mousePressEvent(event)
			case QEvent.Type.MouseButtonRelease:
				menu.mouseReleaseEvent(event)
			case _:
				menu.mouseMoveEvent(event)
		if menu.hovered != hovered:
			self.glide_since = Clock.seconds

	def follow_menu(self, now: float) -> None:
		""" Plays the menu's animations on the video's clock, no event loop running them. """
		if self.menu_since is None:
			return
		menu = self.tray.menu
		if menu.appear.direction() != self.menu_direction:
			self.menu_since, self.menu_direction = now, menu.appear.direction()

		elapsed = round(1000 * (now - self.menu_since))
		closing = self.menu_direction == QAbstractAnimation.Direction.Backward
		menu.appear.setCurrentTime(max(0, SHOW_MS - elapsed) if closing else min(SHOW_MS, elapsed))
		if menu.glide.state() == QAbstractAnimation.State.Running:
			menu.glide.setCurrentTime(min(HOVER_MS, round(1000 * (now - self.glide_since))))
		if closing and elapsed >= SHOW_MS:
			self.menu_since = None

	def her_rect(self) -> QRectF:
		""" Her sprite on the desktop, which the overlay's own coordinates match at `ZOOM`. """
		return QRectF(self.spot.x() + self.avatar.sprite_left, self.spot.y() + SPRITE_TOP, self.avatar.sprite_width, SPRITE_HEIGHT)

	def pill_at(self) -> QPointF:
		return self.spot + self.size if self.pill_corner is None else self.pill_corner

	def pill_rect(self) -> QRectF:
		corner = self.pill_at()
		return QRectF(corner.x() - PILL_SIZE, corner.y() - PILL_SIZE, PILL_SIZE, PILL_SIZE)

	def blink(self) -> None:
		""" Closes her eyes on the precomputed blinks, which a random timer would make different in every video. """
		closed = f"{self.avatar.expression}_blink"
		if self.avatar.frame not in (self.avatar.expression, closed) or closed not in self.avatar.sprites:
			return
		blinking = any(0 <= Clock.seconds - at < BLINK_S for at in self.blinks)
		self.avatar.frame = closed if blinking else self.avatar.expression

	def follow_slide(self) -> None:
		""" Starts her slide when the app pops her in or out, and hides her once she has faded, as `Avatar.hide_if_faded` does. """
		target = 1.0 if self.avatar.isVisible() and self.avatar.fade.endValue() == 1.0 else 0.0
		if target != self.slide[1]:
			self.slide = (self.opacity(), target, Clock.seconds)
		if target == 0 and self.opacity() == 0 and self.avatar.isVisible():
			self.avatar.hide()

	def opacity(self) -> float:
		start, end, at = self.slide
		return start + (end - start) * ease((Clock.seconds - at) / SLIDE_S)

	def shot(self) -> Shot:
		""" Wide on the desktop, close on her or her pill while either is up, or the view a `Frame` holds.

		The view stays inside the desktop, so that a shot on a corner of it frames that corner.
		"""
		now = Clock.seconds
		if now < INTRO_S - 0.5 or self.outro_at is not None:
			return Shot(QPointF(WIDTH / 2, HEIGHT / 2), 1.0)
		if self.frame:
			return Shot(QPointF(*self.frame.center), self.frame.zoom, self.frame.spring)
		if self.pill.isVisible():
			return Shot(self.pill_rect().center(), HER_SHOT)
		if self.slide[1] == 1.0 or now - self.slide[2] < LINGER_S:
			# The view's bottom-right corner on hers, which leaves room for her bubble on her left
			return Shot(self.spot + self.size - QPointF(WIDTH, HEIGHT) / HER_SHOT / 2, HER_SHOT)
		return Shot(QPointF(WIDTH / 2, HEIGHT / 2), 1.0)

	def draw(self) -> QImage:
		frame = QImage(WIDTH, HEIGHT, QImage.Format.Format_RGB32)
		painter = QPainter(frame)
		hints = QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform | QPainter.RenderHint.TextAntialiasing
		painter.setRenderHints(hints)
		camera = self.camera.transform()
		painter.setTransform(camera)
		painter.drawImage(QRectF(0, 0, WIDTH, HEIGHT), self.wallpaper)
		painter.drawPicture(0, 0, self.desktop.windows)
		if (minimized := ease((Clock.seconds - MINIMIZE_S) / 0.3)) < 1:
			center = TERMINAL_FRAME.center()
			painter.save()
			painter.setOpacity(1 - minimized)
			painter.translate(center + (TERMINAL_ICON - center) * minimized)
			painter.scale(1 - 0.9 * minimized, 1 - 0.9 * minimized)
			painter.translate(-center)
			painter.drawPicture(0, 0, self.desktop.terminal)
			painter.restore()
		painter.drawPicture(0, 0, self.desktop.taskbar)
		painter.resetTransform()
		# The closer the shot, the darker the desktop away from her, so that she stands out of it
		depth = min(1.0, max(0.0, (self.camera.zoom() - 1) / (HER_SHOT - 1)))
		shade = QLinearGradient(0, 0, 0.65 * WIDTH, 0)
		shade.setColorAt(0, QColor(8, 6, 14, round(160 * depth)))
		shade.setColorAt(1, QColor(8, 6, 14, 0))
		painter.fillRect(QRectF(0, 0, WIDTH, HEIGHT), shade)

		if self.pill.isVisible():
			corner = self.pill_rect().topLeft()
			painter.setTransform(QTransform().translate(corner.x(), corner.y()).scale(1 / PILL_ZOOM, 1 / PILL_ZOOM) * camera)
			self.pill.render(painter, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
		painter.resetTransform()

		if self.avatar.isVisible():
			self.draw_her(painter, camera, hints)
		if self.menu_since is not None:
			painter.setTransform(QTransform().translate(self.tray.menu.x(), self.tray.menu.y()) * camera)
			self.tray.menu.render(painter, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
		self.draw_pointer(painter, camera)
		painter.resetTransform()
		self.draw_titles(painter)
		painter.end()
		return frame

	def draw_her(self, painter: QPainter, camera: QTransform, hints: QPainter.RenderHint) -> None:
		""" The overlay on a layer of its own, which then fades as a whole as the window does on the screen. """
		layer = QImage(WIDTH, HEIGHT, QImage.Format.Format_ARGB32_Premultiplied)
		layer.fill(0)
		opacity = self.opacity()
		overlay = QPainter(layer)
		overlay.setRenderHints(hints)
		place = QTransform().translate(self.spot.x(), self.spot.y() + SLIDE_PX * (1 - opacity)).scale(1 / ZOOM, 1 / ZOOM)
		overlay.setTransform(place * camera)
		self.avatar.render(overlay, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
		overlay.end()
		painter.setOpacity(opacity)
		painter.drawImage(0, 0, layer)
		painter.setOpacity(1)

	def draw_pointer(self, painter: QPainter, camera: QTransform) -> None:
		""" The pointer while it moves, with the ring of a long press on her or her pill, or a full one for a click. """
		now = Clock.seconds
		shown = min(1.0, (now - self.pointer_since) / 0.2, (self.gesture.end() + 1.0 - now) / 0.3)
		if shown <= 0:
			return
		held = min(1.0, (now - self.grab.since) * 1000 / LONG_PRESS_MS) if self.grab else 1.0 if self.held else None
		painter.setTransform(camera)
		painter.setOpacity(shown)
		pointer(painter, self.point, held)
		painter.setOpacity(1)

	def draw_titles(self, painter: QPainter) -> None:
		""" Everything drawn over the desktop rather than on it: the user's words and the cards. """
		now = Clock.seconds
		if self.said:
			self.draw_caption(painter, *self.said)
		if self.titled and (age := now - self.titled[1]) < CARD_S:
			painter.save()
			painter.setOpacity(min(1.0, age / 0.35, (CARD_S - age) / 0.4))
			painter.translate(-30 * (1 - ease(age / 0.5)), 0)
			chapter_card(painter, self.titled[0].number, self.titled[0].chapter.title, self.titled[0].chapter.subtitle)
			painter.restore()

		if now < INTRO_S:
			painter.setOpacity(min(1.0, (INTRO_S - now) / 0.4))
			title_card(painter, "hello", self.words.tagline, (), appeared=now / 0.9)
		if self.outro_at is not None:
			painter.setOpacity(min(1.0, (now - self.outro_at) / 0.4))
			footer = ("uv run claudetan", "github.com/Stoupy51/ClaudeTan")
			title_card(painter, "happy", self.words.outro, footer, appeared=(now - self.outro_at) / 0.9)
		black = max(1 - now / 0.5, 1 - (self.end - now) / 0.5, 0.0)
		painter.setOpacity(1)
		painter.fillRect(QRectF(0, 0, WIDTH, HEIGHT), QColor(0, 0, 0, round(255 * black)))

	def draw_caption(self, painter: QPainter, said: Speak, at: float) -> None:
		""" What the user says, rising in as they start and fading out a while after they stop. """
		age, speech = Clock.seconds - at, speaking_s(said.text)
		if age >= speech + CAPTION_S:
			return
		painter.save()
		painter.setOpacity(min(1.0, age / 0.15, (speech + CAPTION_S - age) / 0.3))
		painter.translate(0, 14 * (1 - ease(age / 0.3)))
		caption(painter, self.words.you, said.language, said.text, age / speech, level(Clock.seconds) if age < speech else 0.0)
		painter.restore()

	def chime(self, *notes: float) -> None:
		self.sounds.append((Clock.seconds, bell(*notes)))

	def soundtrack(self, seconds: float) -> np.ndarray[tuple[int, int], np.dtype[np.float32]]:
		""" The pad, ducked under her voice, with her chimes and her voice over it, in stereo. """
		mix = music(seconds)
		now = np.arange(len(mix)) / CHIME_RATE
		gain = np.ones(len(mix), np.float32)
		for start, end in self.ducks:
			under = np.clip(np.minimum(now - start + DUCK_S, end + DUCK_S - now) / DUCK_S, 0, 1)
			gain = np.minimum(gain, 1 - (1 - DUCKED) * under).astype(np.float32)
		mix *= gain[:, None]
		for at, sound in self.sounds:
			start = round(at * CHIME_RATE)
			end = min(len(mix), start + len(sound))
			mix[start:end] += sound[:end - start, None]
		return mix


# Functions
def video_time(_avatar: Avatar) -> float:
	return Clock.seconds


def music(seconds: float) -> np.ndarray[tuple[int, int], np.dtype[np.float32]]:
	""" A slow pad of `CHORDS`, each fading into the next, the left and right voices slightly detuned to widen it. """
	samples = round(seconds * CHIME_RATE)
	pad = np.zeros((samples, 2), np.float32)
	for index, start in enumerate(np.arange(0.0, seconds, CHORD_S)):
		first, last = round(start * CHIME_RATE), min(samples, round((start + CHORD_S + 2.0) * CHIME_RATE))
		t = np.arange(last - first) / CHIME_RATE
		envelope = np.clip(t / 1.6, 0, 1) ** 2 * np.clip((CHORD_S + 2.0 - t) / 2.0, 0, 1)
		for note in CHORDS[index % len(CHORDS)]:
			for side, detune in enumerate((0.9985, 1.0015)):
				phase = 2 * np.pi * note * detune * t
				pad[first:last, side] += envelope * (np.sin(phase) + 0.2 * np.sin(2 * phase))
	pad *= 0.03 / np.sqrt(np.mean(pad**2))
	fade = np.minimum(1.0, np.minimum(np.arange(samples), samples - np.arange(samples)) / (2.5 * CHIME_RATE))
	return (pad * fade[:, None]).astype(np.float32)


def write_wav(path: Path, mix: np.ndarray[tuple[int, int], np.dtype[np.float32]]) -> None:
	with wave.open(str(path), "wb") as file:
		file.setnchannels(2)
		file.setsampwidth(2)
		file.setframerate(CHIME_RATE)
		file.writeframes((np.clip(2.0 * mix, -1, 1) * 32767).astype(np.int16).tobytes())


def main() -> None:
	parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
	parser.add_argument("--stills", nargs="+", type=float, help="seconds of the frames to save as images, instead of the video")
	args = parser.parse_args()
	folder = ROOT / "dist"
	folder.mkdir(exist_ok=True)

	app = QApplication([])
	app.setQuitOnLastWindowClosed(False)
	with ExitStack() as stack:
		studio = Studio(ENGLISH, stack)
		if args.stills:
			studio.stills(args.stills, folder)
		else:
			studio.render(folder / "demo.mp4")


if __name__ == "__main__":
	main()

