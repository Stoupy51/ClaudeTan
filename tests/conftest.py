# Imports
import os
from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication


# Functions
@pytest.fixture(scope="session")
def app() -> Iterator[QApplication]:
	os.environ["QT_QPA_PLATFORM"] = "offscreen"
	yield QApplication([])

