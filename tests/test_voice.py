""" A spoken request kept open across pauses until its closing words or a long silence. """
# Imports
from pathlib import Path

import numpy as np
import pytest

import claudetan.config
from claudetan import i18n
from claudetan.config import DEFAULTS, Config, save_volume
from claudetan.i18n import tr
from claudetan.voice import listener as listener_module
from claudetan.voice.audio import RATE, Speech
from claudetan.voice.listener import SPELLING, Listener


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
	voice.hear("Hé Claude, qu'est-ce qu'il y a sur mon écran ? Terminé.", "fr", ended=True)
	assert sent == ["qu'est-ce qu'il y a sur mon écran ?"]


def test_a_bare_yes_or_no_answers_a_permission_request_only_while_she_asks(monkeypatch: pytest.MonkeyPatch) -> None:
	sent: list[str] = []
	voice = listener(sent, monkeypatch)
	answers: list[bool] = []
	voice.answered.connect(answers.append)
	voice.hear("Oui.", "fr", ended=True)
	assert answers == []

	voice.asking = True
	voice.hear("Oui.", "fr", ended=True)
	voice.hear("Non !", "fr", ended=True)
	voice.hear("Peut-être plus tard.", "fr", ended=True)
	assert answers == [True, False]
	assert sent == []


def test_a_request_is_sent_after_a_pause_or_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
	sent: list[str] = []
	voice = listener(sent, monkeypatch)
	voice.add("Ouvre Spotify.")
	voice.send()
	voice.add("Supprime le dossier.")
	voice.add("Annule !")
	assert sent == ["Ouvre Spotify.", "<cancelled>"]


def test_her_lines_follow_the_language_of_what_is_said_to_her_only(monkeypatch: pytest.MonkeyPatch) -> None:
	voice = listener([], monkeypatch)
	voice.hear("Hé Claude, quel temps fait-il ?", "fr", ended=True)
	voice.hear("Thank you.", "en", ended=True)
	assert tr("Yes?", "Oui ?") == "Oui ?"

	voice.hear("Hey Claude, set a timer for 5 minutes.", "en", ended=True)
	assert i18n.heard == "en"


def test_on_the_cpu_whisper_hears_only_the_sentences_she_listens_to(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setattr(listener_module, "GPU", False)
	voice = listener([], monkeypatch)
	sentence = np.zeros(2 * RATE, np.float32)
	assert not voice.transcribes(Speech(audio=sentence, ended=True))

	voice.wake()
	assert voice.transcribes(Speech(audio=sentence, ended=True))
	assert not voice.transcribes(Speech(audio=sentence, ended=False))



def test_closing_the_bubble_drops_the_request_and_the_wake(monkeypatch: pytest.MonkeyPatch) -> None:
	sent: list[str] = []
	voice = listener(sent, monkeypatch)
	voice.wake()
	voice.add("Ouvre Spotify.")
	voice.cancel()
	voice.hear("Et ouvre Discord.", "fr", ended=True)
	voice.send()
	assert sent == []


def test_a_stop_said_as_a_sentence_of_its_own_replaces_the_request_being_dictated(monkeypatch: pytest.MonkeyPatch) -> None:
	sent: list[str] = []
	voice = listener(sent, monkeypatch)
	voice.add("Écris un script qui range mes captures.")
	voice.add("Annule tout.")
	assert sent == ["Annule tout."]
	assert voice.request == []

	voice.add("Ouvre Spotify et arrête tout ce bruit.")
	assert sent == ["Annule tout."]


def test_the_sentence_given_to_whisper_as_context_does_not_wake_her_when_it_writes_it_back(monkeypatch: pytest.MonkeyPatch) -> None:
	sent: list[str] = []
	voice = listener(sent, monkeypatch)
	voice.hear(SPELLING, "en", ended=True)
	assert voice.awake_until == 0.0


def test_the_volume_is_set_in_the_config_whether_or_not_the_file_has_the_key(tmp_path: Path) -> None:
	config = tmp_path / "config.toml"
	config.write_text('city = ""\n', encoding="utf-8")
	save_volume(0.5, config)
	save_volume(0.25, config)
	assert config.read_text(encoding="utf-8") == 'city = ""\n\nvolume = 0.25\n'

