""" The tray icon: its menu, and starting the app with Windows. """
# Imports
import os
import sys
import winreg
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QCursor, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from claudetan.avatar import face
from claudetan.config import USER_CONFIG

# Constants
RUN_KEY: str = r"Software\Microsoft\Windows\CurrentVersion\Run"
""" Registry key, under HKEY_CURRENT_USER, of the programs Windows starts at logon. """
LAUNCHER: Path = Path(sys.prefix) / "Scripts" / "claudetan.exe"
""" Entry point that `uv sync` installs in the project environment, which starts the app in the background. """


# Classes
class Tray(QSystemTrayIcon):
	open_session = Signal()

	def __init__(self) -> None:
		super().__init__(QIcon(face(64)))
		self.setToolTip("Claude-tan")
		self.menu = QMenu()
		self.menu.addAction("Ouvrir la session", self.open_session.emit)
		self.menu.addAction("Ouvrir la config", lambda: os.startfile(USER_CONFIG))
		startup = self.menu.addAction("Démarrer avec Windows")
		startup.setCheckable(True)
		startup.setChecked(starts_with_windows())
		startup.toggled.connect(start_with_windows)
		self.menu.addSeparator()
		self.menu.addAction("Quitter", QApplication.quit)
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

