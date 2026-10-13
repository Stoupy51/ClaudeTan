""" The last direct messages with a person, read with the user's own Discord account. Read-only: nothing is ever sent. """
# Imports
import json
import urllib.error
import urllib.request
from datetime import datetime

from stouputils.typing import JsonDict, JsonList

from claudetan.i18n import tr

# Constants
API: str = "https://discord.com/api/v9"
DIRECT_MESSAGE: int = 1
""" Type of the channels that hold a conversation with one person. """


# Functions
def last_messages(person: str, count: int, token: str) -> str:
	""" The `count` last messages of the direct conversation with the person whose name contains `person`, oldest first. """
	try:
		channels = get("/users/@me/channels", token)
		wanted = person.lower()
		channel = next((
			channel for channel in channels
			if channel["type"] == DIRECT_MESSAGE and any(wanted in names(user) for user in channel["recipients"])
		), None)
		if not channel:
			return tr(f"I can't find a direct conversation with {person}.", f"Je ne trouve pas de conversation privée avec {person}.")
		messages = get(f"/channels/{channel['id']}/messages?limit={count}", token)
	except urllib.error.HTTPError as error:
		if error.code == 401:
			return tr("Discord refused the token of the config.", "Discord a refusé le jeton de la config.")
		return tr(f"Discord answered {error.code}.", f"Discord a répondu {error.code}.")
	except urllib.error.URLError:
		return tr("I can't reach Discord.", "Je n'arrive pas à joindre Discord.")

	lines = [
		f"[{datetime.fromisoformat(message['timestamp']).astimezone():%d/%m %H:%M}] {shown(message['author'])}: "
		+ " ".join([message["content"], *(file["url"] for file in message["attachments"])])
		for message in reversed(messages)
	]
	return "\n".join(lines) or tr(f"No messages with {person}.", f"Aucun message avec {person}.")


def get(path: str, token: str) -> JsonList:
	request = urllib.request.Request(f"{API}{path}", headers={"Authorization": token, "User-Agent": "Mozilla/5.0"})
	with urllib.request.urlopen(request, timeout=10) as response:
		return json.load(response)


def names(user: JsonDict) -> str:
	""" Both names of a user, in lower case, to look a person up by either. """
	return f"{user['username']} {user['global_name'] or ''}".lower()


def shown(user: JsonDict) -> str:
	""" What a user is called in the conversation. """
	return user["global_name"] or user["username"]

