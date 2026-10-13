# Imports
import os
from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication

from claudetan import i18n


# Functions
@pytest.fixture(scope="session")
def app() -> Iterator[QApplication]:
	os.environ["QT_QPA_PLATFORM"] = "offscreen"
	yield QApplication([])


@pytest.fixture(autouse=True)
def english(monkeypatch: pytest.MonkeyPatch) -> None:
	""" Her lines in English, the language of a fresh app, whatever language an earlier test heard. """
	monkeypatch.setattr(i18n, "heard", "en")

