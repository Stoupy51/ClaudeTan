""" Her avatar, pill and tray icon, built again from the code of `claudechan.overlay` and of this module once a reload changes it. """
# Imports
from dataclasses import replace
from functools import partial
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal

from claudechan.config import Config, save_volume
from claudechan.overlay import avatar as avatar_module, tray as tray_module
from claudechan.session import Session
from claudechan.voice.listener import Listener
from claudechan.voice.speech import Voice

if TYPE_CHECKING:
	from claudechan.app import Assistant

# Constants
OVERLAY: str = "claudechan.overlay"
""" The package whose reloaded modules, or images, make the windows be built again. """


# Classes
class Windows(QObject):
	quit_requested = Signal()
	""" Quit was picked in the tray. """

	def __init__(self, config: Config) -> None:
		super().__init__()
		self.build(config)

	def connect_to(self, assistant: Assistant, session: Session, listener: Listener, voice: Voice) -> None:
		""" Wires the windows to what they act on, which they keep to wire the windows built after a reload. """
		self.assistant, self.session, self.listener, self.voice = assistant, session, listener, voice
		self.wire()

	def on_reloaded(self, modules: list[str]) -> None:
		""" Replaces the windows by new ones, wired again, when their classes or this module were reloaded, while she has left. """
		if not any(name.startswith((OVERLAY, __name__)) for name in modules):
			return
		for window in (self.avatar, self.pill, self.tray):
			window.hide()
			window.deleteLater()
		self.build(self.listener.config)
		self.assistant.avatar, self.assistant.pill = self.avatar, self.pill
		self.wire()

	def build(self, config: Config) -> None:
		self.avatar = avatar_module.Avatar(config.avatar_zoom, config.text_zoom)
		self.avatar.bubble.typing_speed = config.typing_speed
		self.pill = avatar_module.Pill(config.avatar_zoom)
		self.tray = tray_module.Tray(config.volume)
		self.tray.show()

	def wire(self) -> None:
		self.tray.quit_requested.connect(self.quit_requested)
		self.tray.action_requested.connect(self.assistant.announce)
		self.tray.open_session.connect(self.session.open)
		self.tray.volume_changed.connect(partial(set_volume, self.voice, self.listener))
		self.tray.menu.closed.connect(lambda: save_volume(self.listener.config.volume))
		self.avatar.clicked.connect(self.session.open)
		self.pill.clicked.connect(self.session.open)
		self.pill.menu_requested.connect(lambda: self.tray.menu.toggle_by(self.pill.geometry()))
		self.avatar.read.connect(self.assistant.on_read)
		self.avatar.closed.connect(self.listener.cancel)
		self.avatar.closed.connect(self.assistant.leave)
		self.avatar.hidden.connect(self.assistant.leave)
		self.avatar.closed.connect(self.voice.hush)
		self.avatar.hidden.connect(self.voice.hush)
		self.voice.started.connect(self.avatar.speak)


# Functions
def set_volume(voice: Voice, listener: Listener, volume: float) -> None:
	""" Applies a volume picked in the tray to her voice, and to the config the listener holds so that saving it announces nothing. """
	voice.volume = volume
	listener.config = replace(listener.config, volume=volume)

