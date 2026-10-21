""" Where the tray menu opens, what a click on it does, and how it closes. """
# Imports
import pytest
from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from claudetan.overlay import menu as menu_module
from claudetan.overlay.avatar import Pill
from claudetan.overlay.menu import SHOW_MS, WATCH_MS, Entry, Menu, Slider, slider_track


# Functions
@pytest.fixture(autouse=True)
def buttons(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
	""" The mouse buttons as Windows tells them, up until a test presses one. """
	down = [False]
	monkeypatch.setattr(menu_module, "mouse_down", lambda: down[0])
	return down


def test_the_menu_opens_inside_the_screen_by_its_icon_and_fades_out_on_escape_or_a_click_outside(app: QApplication) -> None:
	ran: list[str] = []
	closed: list[bool] = []
	menu = Menu([[Entry("Quit", "x", lambda: ran.append("quit"))]])
	menu.closed.connect(lambda: closed.append(True))
	area = QGuiApplication.primaryScreen().availableGeometry()
	menu.toggle_by(QRect(area.bottomRight() - QPoint(10, -4), QSize(20, 20)))
	assert area.contains(menu.box.translated(menu.pos().toPointF()).toRect())
	QTest.qWait(2 * SHOW_MS)
	assert menu.appear.currentValue() == 1.0

	QTest.keyClick(menu, Qt.Key.Key_Escape)
	assert menu.isVisible()
	QTest.qWait(2 * SHOW_MS)
	assert not menu.isVisible()
	assert closed == [True]

	menu.toggle_by(QRect(QPoint(500, 500), QSize(20, 20)))
	QTest.mouseClick(menu, Qt.MouseButton.LeftButton, pos=QPoint(-40, -40))
	QTest.qWait(2 * SHOW_MS)
	assert closed == [True, True]
	assert ran == []


def test_a_button_pressed_away_from_the_menu_closes_it_and_one_held_since_it_opened_does_not(
	app: QApplication, buttons: list[bool],
) -> None:
	menu = Menu([[Entry("Quit", "x", lambda: None)]])
	cursor = QCursor.pos()
	buttons[0] = True
	menu.toggle_by(QRect(cursor + QPoint(300, 300), QSize(20, 20)))
	QTest.qWait(3 * WATCH_MS)
	assert menu.appear.direction() == menu.appear.Direction.Forward

	buttons[0] = False
	QTest.qWait(3 * WATCH_MS)
	buttons[0] = True
	QTest.qWait(3 * WATCH_MS)
	assert menu.appear.direction() == menu.appear.Direction.Backward
	QTest.qWait(2 * SHOW_MS)
	assert not menu.isVisible()
	assert not menu.watch.isActive()

	menu.toggle_by(QRect(cursor + QPoint(300, 300), QSize(20, 20)))
	menu.toggle_by(QRect(cursor + QPoint(300, 300), QSize(20, 20)))
	assert menu.appear.direction() == menu.appear.Direction.Backward


def test_dragging_the_slider_sets_it_by_hundredths_and_a_click_on_an_entry_runs_it(app: QApplication) -> None:
	volumes: list[float] = []
	ran: list[str] = []
	slider = Slider("Volume", "v", 0.5, volumes.append)
	menu = Menu([[slider], [Entry("Quit", "x", lambda: ran.append("quit"))]])
	menu.toggle_by(QRect(QPoint(500, 500), QSize(20, 20)))
	(_, volume_row), (_, quit_row) = menu.rows
	track = slider_track(volume_row)

	QTest.mousePress(menu, Qt.MouseButton.LeftButton, pos=QPoint(round(track.left()) + 5, round(track.center().y())))
	QTest.mouseMove(menu, QPoint(round(track.right()) + 40, round(track.center().y())))
	QTest.mouseRelease(menu, Qt.MouseButton.LeftButton, pos=QPoint(round(track.right()) + 40, round(track.center().y())))
	assert volumes[-1] == 1.0
	assert all(round(volume, 2) == volume for volume in volumes)
	assert ran == []

	QTest.mouseRelease(menu, Qt.MouseButton.RightButton, pos=quit_row.center().toPoint())
	assert ran == []
	QTest.mouseClick(menu, Qt.MouseButton.LeftButton, pos=quit_row.center().toPoint())
	assert ran == ["quit"]


def test_a_right_click_on_the_pill_asks_for_the_menu_without_dragging_it_or_opening_the_session(app: QApplication) -> None:
	pill = Pill()
	events: list[str] = []
	pill.menu_requested.connect(lambda: events.append("menu"))
	pill.clicked.connect(lambda: events.append("clicked"))
	QTest.mouseClick(pill, Qt.MouseButton.RightButton, pos=QPoint(30, 30))
	assert events == ["menu"]
	assert not pill.long_press.isActive()

