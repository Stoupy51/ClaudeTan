""" Runs the app, starts it again when it quits to apply a change to its code, and puts that change aside if it then fails to start.

It imports nothing of the app, which the hidden session may have broken.
"""
# Imports
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from stouputils.typing import JsonDict

# Constants
READY: str = "ready\n"
""" Last line the app writes once started. The lines up to it are relayed to `claudechan`, which returns on it. """
RESTART: int = 3
""" Exit code of an app quitting to be started again on its changed code. """
CHANGED: str = "changed: "
""" Start of the line an app quitting with `RESTART` writes, then the JSON `{"files": [...], "since": commit}` of the change. """
LAUNCHER_LOG: Path = Path(os.environ["APPDATA"]) / "ClaudeChan" / "launcher.log"
""" What became of each run of the app, beside the app's own log: a crash that kills the app leaves nothing in that one. """
SET_ASIDE: str = "CLAUDECHAN_SET_ASIDE"
""" Variable giving an app the names of the files whose change broke the app before it, and was put aside. """


# Functions
def main() -> None:
	""" Runs the app until it quits for good, or fails to start on code that is not a change it can put aside. """
	logging.basicConfig(filename=LAUNCHER_LOG, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
	files: list[str] = []
	since = ""
	env = dict(os.environ)
	relay = True
	while True:
		ready, change = run_app(env, relay=relay)
		relay = relay and not ready
		env.pop(SET_ASIDE, None)
		if change:
			files, since = change["files"], change["since"]
		elif not ready and files:
			set_aside(files, since)
			env[SET_ASIDE] = ", ".join(Path(file).name for file in files)
			files = []
		else:
			return


def run_app(env: dict[str, str], *, relay: bool) -> tuple[bool, JsonDict]:
	""" Runs the app until it quits, relaying its lines up to `READY` when `relay` is set.

	Returns:
		Whether it got ready, and the change it quit to apply, empty for none.
	"""
	app = subprocess.Popen(
		[sys.executable, "-m", "claudechan.app"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
		text=True, env=env, creationflags=subprocess.CREATE_NO_WINDOW,
	)
	assert app.stdout
	ready = False
	change: JsonDict = {}
	for line in app.stdout:
		if line.startswith(CHANGED):
			change = json.loads(line.removeprefix(CHANGED))
		elif relay and not ready:
			print(line, end="", flush=True)
		ready = ready or line == READY
	logging.info("App exited with code %#x, ready=%s, change announced=%s", app.wait() & 0xFFFFFFFF, ready, bool(change))
	return ready, change


def set_aside(files: list[str], since: str) -> None:
	""" Undoes the hidden session's change to `files`: stashing what it left uncommitted, reverting its commits after `since`. """
	repository = Path(files[0]).parent
	if git(repository, "status", "--porcelain", "--", *files):
		git(repository, "stash", "push", "--include-untracked", "--message", "ClaudeChan: a change that broke the app", "--", *files)
	if commits := git(repository, "rev-list", f"{since}..HEAD", "--", *files).split():
		git(repository, "revert", "--no-edit", *commits)


def git(repository: Path, *arguments: str) -> str:
	""" The output of a git command run in the repository holding the `repository` folder. """
	run = subprocess.run(
		["git", *arguments], cwd=repository, capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW,
	)
	return run.stdout.strip()


if __name__ == "__main__":
	main()

