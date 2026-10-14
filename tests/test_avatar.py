""" Where Claude-tan shows up as screens come and go, and how her mouth follows her voice. """
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


def test_her_mouth_follows_the_vowels_her_voice_says_in_a_pose_that_can_talk(app: QApplication) -> None:
	avatar = Avatar()
	avatar.set_expression("present", bubble="The tests pass.")
	vowels = ((0.0, "a"), (1.0, "i"), (2.0, "N"), (3.0, ""))
	avatar.speak(vowels)
	assert avatar.expression == "idle"
	assert avatar.bubble.text == "The tests pass."

	frames: list[str] = []
	for said in (0.5, 1.5, 2.5, 3.5):
		avatar.move_mouth(said, vowels)
		frames.append(avatar.frame)
	assert frames == ["idle_talk_wide", "idle_talk_open", "idle", "idle"]
	assert avatar.speech is None

