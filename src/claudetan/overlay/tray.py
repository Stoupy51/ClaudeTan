""" The tray icon: its menu, and starting the app with Windows. """
# Imports
import os
import sys
import winreg
from pathlib import Path

from PySide6.QtCore import QRect, QSize, Signal
from PySide6.QtGui import QCursor, QIcon
from PySide6.QtWidgets import QSystemTrayIcon

from claudetan.config import APP_DATA, LOG_FILE, USER_CONFIG
from claudetan.overlay.avatar import face
from claudetan.overlay.menu import Entry, Menu, Slider, Switch

# Constants
RUN_KEY: str = r"Software\Microsoft\Windows\CurrentVersion\Run"
""" Registry key, under HKEY_CURRENT_USER, of the programs Windows starts at logon. """
LAUNCHER: Path = Path(sys.prefix) / "Scripts" / "claudetan.exe"
""" Entry point that `uv sync` installs in the project environment, which starts the app in the background. """


# Classes
class Tray(QSystemTrayIcon):
	open_session = Signal()
	action_requested = Signal(str)
	""" The name of an action picked in the menu. """
	quit_requested = Signal()
	volume_changed = Signal(float)
	""" The volume of her voice the slider was moved to, from 0 to 1. """

	def __init__(self, volume: float) -> None:
		super().__init__(QIcon(face(64)))
		self.setToolTip("Claude-tan")
		self.menu = Menu([
			[
				Entry("Open the session", "\ue8a7", self.open_session.emit),
				Entry("Session context", "\ue9d2", lambda: self.action_requested.emit("context")),
				Entry("Plan usage", "\uec4a", lambda: self.action_requested.emit("plan_usage")),
			],
			[Slider("Volume", "\ue767", volume, self.volume_changed.emit)],
			[
				Entry("Open the config", "\ue713", lambda: os.startfile(USER_CONFIG)),
				Entry("View the log", "\ue8a5", lambda: os.startfile(LOG_FILE)),
				Entry("Open the folder", "\ue838", lambda: os.startfile(APP_DATA)),
				Switch("Start with Windows", "\ue770", starts_with_windows(), start_with_windows),
			],
			[Entry("Quit", "\ue7e8", self.quit_requested.emit)],
		])
		self.activated.connect(self.on_activated)

	def on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
		""" Opens the menu by the icon on a left or a right click, or by the cursor where the system tells no place for the icon. """
		if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.Context):
			icon = self.geometry()
			self.menu.toggle_by(icon if icon.isValid() else QRect(QCursor.pos(), QSize(1, 1)))


# Functions
def starts_with_windows() -> bool:
	with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
		try:
			winreg.QueryValueEx(key, "ClaudeTan")
		except FileNotFoundError:
			return False
		return True


def start_with_windows(enabled: bool) -> None:
	with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, access=winreg.KEY_SET_VALUE) as key:
		if enabled:
			winreg.SetValueEx(key, "ClaudeTan", 0, winreg.REG_SZ, f'"{LAUNCHER}"')
		else:
			winreg.DeleteValue(key, "ClaudeTan")

