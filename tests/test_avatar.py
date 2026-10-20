""" Where Claude-tan shows up as screens come and go, and how her mouth follows her voice. """
# Imports
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QPointF, QSettings, Qt
from PySide6.QtGui import QGuiApplication, QImage, QMouseEvent, QPainter
from PySide6.QtWidgets import QApplication

from claudetan.overlay.avatar import Avatar, Pill


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



def test_the_buttons_of_her_bubble_close_or_hide_her_and_a_click_elsewhere_opens_the_session(app: QApplication) -> None:
	avatar = Avatar()
	avatar.set_expression("present", bubble="The tests pass.")
	image = QImage(500, 500, QImage.Format.Format_ARGB32)
	painter = QPainter(image)
	avatar.bubble.paint(painter, now=1.0, bottom=250)
	painter.end()
	events: list[str] = []
	avatar.closed.connect(lambda: events.append("closed"))
	avatar.hidden.connect(lambda: events.append("hidden"))
	avatar.clicked.connect(lambda: events.append("clicked"))

	def click(point: QPointF) -> None:
		left, none, no_keys = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier
		avatar.mousePressEvent(QMouseEvent(QEvent.Type.MouseButtonPress, point, point, left, left, no_keys))
		avatar.mouseReleaseEvent(QMouseEvent(QEvent.Type.MouseButtonRelease, point, point, left, none, no_keys))

	click(avatar.bubble.buttons["close"].center() * avatar.text_zoom)
	click(avatar.bubble.buttons["hide"].center() * avatar.text_zoom)
	click(QPointF(avatar.width() - 5, avatar.height() - 5))
	assert events == ["closed", "hidden", "clicked"]


def test_a_pill_dragged_after_a_long_press_moves_her_place_and_a_short_press_only_clicks(app: QApplication, tmp_path: Path) -> None:
	avatar = Avatar()
	avatar.settings = QSettings(str(tmp_path / "overlay.ini"), QSettings.Format.IniFormat)
	pill = Pill()
	pill.dropped.connect(avatar.stand_at)
	clicks: list[str] = []
	pill.clicked.connect(lambda: clicks.append("clicked"))
	pill.move(100, 100)
	left, none, no_keys = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier

	def mouse(kind: QEvent.Type, point: QPoint, button: Qt.MouseButton) -> QMouseEvent:
		return QMouseEvent(kind, QPointF(point), QPointF(point), left, button, no_keys)

	pill.mousePressEvent(mouse(QEvent.Type.MouseButtonPress, QPoint(110, 110), left))
	pill.mouseReleaseEvent(mouse(QEvent.Type.MouseButtonRelease, QPoint(110, 110), none))
	assert clicks == ["clicked"]
	assert avatar.settings.value("pos") is None

	pill.mousePressEvent(mouse(QEvent.Type.MouseButtonPress, QPoint(110, 110), left))
	pill.long_press.stop()
	pill.start_drag()
	pill.mouseMoveEvent(mouse(QEvent.Type.MouseMove, QPoint(310, 210), left))
	pill.mouseReleaseEvent(mouse(QEvent.Type.MouseButtonRelease, QPoint(310, 210), none))
	assert clicks == ["clicked"]
	corner = QPoint(300, 200) + QPoint(pill.width(), pill.height())
	assert avatar.settings.value("pos") == corner - QPoint(avatar.width(), avatar.height())

