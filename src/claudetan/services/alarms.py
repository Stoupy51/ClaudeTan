""" The timers she keeps while she runs. """
# Imports
from PySide6.QtCore import QObject, QTimer, Signal


# Classes
class Alarms(QObject):
	rang = Signal(str)
	""" A timer ended, with what it was set for. """

	def start(self, seconds: int, label: str) -> None:
		""" Rings after `seconds`, from the Qt thread. """
		QTimer.singleShot(seconds * 1000, lambda: self.rang.emit(label))


# Constants
ALARMS: Alarms = Alarms()
""" The timers set by voice or by the session, which a reload keeps as long as this line does not change. """

