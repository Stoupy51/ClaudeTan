""" The language of her own lines: French when the user last spoke French to her, English otherwise. """

heard: str = "en"
""" Whisper's code of the language of the last sentence meant for her, set from the microphone's thread. """


def tr(english: str, french: str) -> str:
	""" Her line in the language the user speaks.

	>>> tr("Yes?", "Oui ?")
	'Yes?'
	"""
	return french if heard == "fr" else english

