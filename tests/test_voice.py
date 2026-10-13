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
	voice.add("C'est tout, et trie-les par date.")
	assert sent == []

	voice.add("Envoie.")
	assert sent == ["Écris un script qui range mes captures. C'est tout, et trie-les par date"]


def test_a_short_word_ends_a_request_only_as_a_sentence_of_its_own(monkeypatch: pytest.MonkeyPatch) -> None:
	sent: list[str] = []
	voice = listener(sent, monkeypatch)
	voice.add("Résume le document jusqu'à la fin.")
	assert sent == []

	voice.add("Fin.")
	assert sent == ["Résume le document jusqu'à la fin."]


def test_a_word_after_the_punctuation_of_a_single_utterance_ends_the_request(monkeypatch: pytest.MonkeyPatch) -> None:
	sent: list[str] = []
	voice = listener(sent, monkeypatch)
	voice.hear("Hé Claude, qu'est-ce qu'il y a sur mon écran ? Terminé.", ended=True)
	assert sent == ["qu'est-ce qu'il y a sur mon écran ?"]


def test_a_request_is_sent_after_a_pause_or_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
	sent: list[str] = []
	voice = listener(sent, monkeypatch)
	voice.add("Ouvre Spotify.")
	voice.send()
	voice.add("Supprime le dossier.")
	voice.add("Annule !")
	assert sent == ["Ouvre Spotify.", "<cancelled>"]

