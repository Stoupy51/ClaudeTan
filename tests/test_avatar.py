""" Where Claude-tan shows up as screens come and go. """
# Imports
from pathlib import Path

from PySide6.QtCore import QPoint, QSettings
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from claudetan.overlay.avatar import Avatar


# Functions
def test_a_screen_unplugged_sends_her_to_the_main_one_without_forgetting_her_place(app: QApplication, tmp_path: Path) -> None:
	avatar = Avatar()
	avatar.settings = QSettings(str(tmp_path / "overlay.ini"), QSettings.Format.IniFormat)
	avatar.settings.setValue("pos", QPoint(10, 10))
	assert avatar.home() == QPoint(10, 10)

	avatar.settings.setValue("pos", QPoint(5000, 5000))
	assert QGuiApplication.primaryScreen().availableGeometry().contains(avatar.home())
	assert avatar.settings.value("pos") == QPoint(5000, 5000)

