""" The tray icon: its menu, and starting the app with Windows. """
# Imports
import os
import sys
import winreg
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QCursor, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from claudetan.config import APP_DATA, LOG_FILE, USER_CONFIG
from claudetan.overlay.avatar import face

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

	def __init__(self) -> None:
		super().__init__(QIcon(face(64)))
		self.setToolTip("Claude-tan")
		self.menu = QMenu()
		self.menu.addAction("Open the session", self.open_session.emit)
		self.menu.addAction("Session context", lambda: self.action_requested.emit("context"))
		self.menu.addAction("Plan usage", lambda: self.action_requested.emit("plan_usage"))
		self.menu.addSeparator()
		self.menu.addAction("Open the config", lambda: os.startfile(USER_CONFIG))
		self.menu.addAction("View the log", lambda: os.startfile(LOG_FILE))
		self.menu.addAction("Open the folder", lambda: os.startfile(APP_DATA))
		startup = self.menu.addAction("Start with Windows")
		startup.setCheckable(True)
		startup.setChecked(starts_with_windows())
		startup.toggled.connect(start_with_windows)
		self.menu.addSeparator()
		self.menu.addAction("Quit", self.quit_requested.emit)
		self.setContextMenu(self.menu)
		self.activated.connect(self.on_activated)

	def on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
		""" Opens the menu on a left click too, Windows only showing it on a right click. """
		if reason == QSystemTrayIcon.ActivationReason.Trigger:
			self.menu.popup(QCursor.pos())


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

