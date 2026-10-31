""" The test Minecraft client of tools/minecraft, a game instance of its own, driven through the HTTP bridge its mod opens. """
# Imports
import json
import subprocess
import urllib.error
import urllib.request

from stouputils.typing import JsonDict

from claudechan.config import ROOT
from claudechan.i18n import tr

# Constants
BRIDGE: str = "http://127.0.0.1:47621"
""" Where the bridge mod listens, `PORT` in Bridge.java. """
CLIENT: str = str(ROOT / "tools" / "minecraft")
""" The Gradle project of the bridge mod, whose runClient task starts the test client in its run folder. """


# Functions
def start() -> str:
	""" Starts the test client unless it already answers. It takes about a minute, until `state` says loading: false. """
	if call("/state").startswith("{"):
		return tr("The test client is already running.", "Le client de test tourne déjà.")
	subprocess.Popen(
		[f"{CLIENT}/gradlew.bat", "runClient", "--console=plain"], cwd=CLIENT,
		stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW,
	)
	return tr("The test client is starting.", "Le client de test démarre.")


def call(route: str, body: JsonDict | None = None) -> str:
	""" The bridge's JSON answer to a route, or why the client cannot answer. """
	request = urllib.request.Request(BRIDGE + route, data=json.dumps(body or {}).encode(), method="POST")
	try:
		with urllib.request.urlopen(request, timeout=15) as response:
			return response.read().decode()
	except (urllib.error.URLError, TimeoutError):
		return tr(
			"The test client is not running: start it with minecraft_start.",
			"Le client de test ne tourne pas : lance-le avec minecraft_start.",
		)

