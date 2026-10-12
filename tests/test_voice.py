""" A spoken request kept open across pauses until its closing words or a long silence. """
# Imports
import re

from claudetan.voice import Listener


# Functions
def listener(sent: list[str]) -> Listener:
	voice = Listener(None, re.compile(r"^hey claude\W*(.*)", re.IGNORECASE))
	voice.heard.connect(sent.append)
	voice.cancelled.connect(lambda: sent.append("<cancelled>"))
	return voice


def test_a_request_ends_only_on_its_last_words() -> None:
	sent: list[str] = []
	voice = listener(sent)
	voice.add("Écris un script qui range mes captures.")
	voice.add("Prompt done, et trie-les par date.")
	assert sent == []

	voice.add("Fin du prompt.")
	assert sent == ["Écris un script qui range mes captures. Prompt done, et trie-les par date"]


def test_a_request_is_sent_after_a_pause_or_dropped() -> None:
	sent: list[str] = []
	voice = listener(sent)
	voice.add("Ouvre Spotify.")
	voice.send()
	voice.add("Supprime le dossier.")
	voice.add("Annule le prompt !")
	assert sent == ["Ouvre Spotify.", "<cancelled>"]

