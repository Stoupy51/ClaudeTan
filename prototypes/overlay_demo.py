""" Overlay demo: the avatar pops up in the bottom-right corner and plays through her expressions.

A click opens the Remote Control page, a long press lets you drag her somewhere else.
Run with `uv run prototypes/overlay_demo.py`, close with Ctrl+C.
"""
# Imports
import signal
import sys
import webbrowser
from dataclasses import dataclass
from typing import ClassVar

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from clairechan.overlay.avatar import Avatar


# Classes
@dataclass(frozen=True)
class Beat:
	""" One step of the demo loop. """
	expression: str
	bubble: str
	duration_ms: int
	talking: bool = False


class Demo:
	BEATS: ClassVar[list[Beat]] = [
		Beat(expression="hello",     bubble="Coucou ! Tu m'as appelée ?",                duration_ms=2600, talking=True),
		Beat(expression="idle",      bubble="",                                          duration_ms=3000),
		Beat(expression="idle",      bubble="Je regarde ça tout de suite...",            duration_ms=3200, talking=True),
		Beat(expression="thinking",  bubble="Hmm, laisse-moi réfléchir.",                duration_ms=2400),
		Beat(expression="working",   bubble="Écrit main.py",                             duration_ms=2400),
		Beat(expression="present",   bubble="Voilà, c'est fait !",                       duration_ms=2200),
		Beat(expression="please",    bubble="J'ai besoin de ton accord pour continuer.", duration_ms=3000),
		Beat(expression="thanks",    bubble="Merci !",                                   duration_ms=1800),
		Beat(expression="sad",       bubble="Oups, la requête a échoué.",                duration_ms=2000),
		Beat(expression="happy",     bubble="Clique sur moi pour ouvrir la session.",    duration_ms=3000),
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
	# Qt's event loop never hands control back to Python's KeyboardInterrupt, so let Ctrl+C end the process directly
	signal.signal(signal.SIGINT, signal.SIG_DFL)
	app = QApplication(sys.argv)
	avatar = Avatar()
	avatar.clicked.connect(lambda: webbrowser.open("https://claude.ai/code"))
	Demo(avatar).restart()
	sys.exit(app.exec())


if __name__ == "__main__":
	main()

