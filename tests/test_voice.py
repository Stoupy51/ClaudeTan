""" A spoken request kept open across pauses until its closing words or a long silence. """
# Imports
import pytest

import claudetan.config
from claudetan.config import DEFAULTS, Config
from claudetan.voice.listener import Listener


# Functions
def listener(sent: list[str], monkeypatch: pytest.MonkeyPatch) -> Listener:
	monkeypatch.setattr(claudetan.config, "USER_CONFIG", DEFAULTS)
	voice = Listener(Config.load())
	voice.heard.connect(sent.append)
	voice.cancelled.connect(lambda: sent.append("<cancelled>"))
	return voice


def test_a_request_ends_only_on_its_last_words(monkeypatch: pytest.MonkeyPatch) -> None:
	sent: list[str] = []
	voice = listener(sent, monkeypatch)
	voice.add("Écris un script qui range mes captures.")
	voice.add("Prompt done, et trie-les par date.")
	assert sent == []

	voice.add("Fin du prompt.")
	assert sent == ["Écris un script qui range mes captures. Prompt done, et trie-les par date"]


def test_a_request_is_sent_after_a_pause_or_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
	sent: list[str] = []
	voice = listener(sent, monkeypatch)
	voice.add("Ouvre Spotify.")
	voice.send()
	voice.add("Supprime le dossier.")
	voice.add("Annule le prompt !")
	assert sent == ["Ouvre Spotify.", "<cancelled>"]

