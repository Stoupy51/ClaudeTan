""" The programs installed on the computer, found through the Start menu shortcuts. """
# Imports
import os
from pathlib import Path

# Constants
START_MENUS: tuple[Path, ...] = (
	Path(os.environ["PROGRAMDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
	Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
)
""" Where the installers put their shortcuts, for every user and for the current one. """


# Functions
def launch(name: str) -> str:
	""" Opens the program whose Start menu shortcut has `name` in its own, the closest name first. """
	wanted = name.lower()
	links = (link for menu in START_MENUS for link in menu.rglob("*.lnk") if wanted in link.stem.lower())
	shortcuts = sorted(links, key=lambda link: len(link.stem))
	if not shortcuts:
		return f"Je ne trouve pas de programme {name}."
	os.startfile(shortcuts[0])
	return f"J'ouvre {shortcuts[0].stem}."

