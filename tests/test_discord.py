""" Direct messages read from Discord. """
# Imports
import pytest
from stouputils.typing import JsonList

from claudetan.services import discord


# Functions
def test_the_last_messages_with_a_person_are_listed_oldest_first_with_their_attachments(monkeypatch: pytest.MonkeyPatch) -> None:
	artyu = {"username": "artyu_", "global_name": "Artyu"}
	me = {"username": "stoupy", "global_name": None}
	channels: JsonList = [
		{"id": "1", "type": 1, "recipients": [{"username": "bob", "global_name": None}]},
		{"id": "2", "type": 1, "recipients": [artyu]},
	]
	messages: JsonList = [
		{"timestamp": "2026-10-13T19:05:00+00:00", "author": me, "content": "Je regarde", "attachments": []},
		{"timestamp": "2026-10-13T19:00:00+00:00", "author": artyu, "content": "Une PR ?", "attachments": [{"url": "https://cdn/x.png"}]},
	]
	def get(path: str, _token: str) -> JsonList:
		return channels if path == "/users/@me/channels" else messages if path == "/channels/2/messages?limit=2" else []
	monkeypatch.setattr(discord, "get", get)

	lines = discord.last_messages("ARTY", 2, "token").splitlines()
	assert [line.split("] ", 1)[1] for line in lines] == ["Artyu: Une PR ? https://cdn/x.png", "stoupy: Je regarde"]
	assert discord.last_messages("zoe", 2, "token") == "I can't find a direct conversation with zoe."

