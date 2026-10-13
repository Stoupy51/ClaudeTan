""" What an action tells when a bar and colors say it better than a sentence. """
# Imports
from dataclasses import dataclass

from claudetan.i18n import tr


# Classes
@dataclass(frozen=True)
class Slice:
	""" One part of a whole, such as what fills the context. """
	key: str
	""" Names the part for its color. """
	label: str
	amount: str
	share: str
	""" As written for the user, such as "29,1 %". """
	fraction: float
	""" Of the whole, from 0 to 1, for the width of its slice of the bar. """


@dataclass(frozen=True)
class Report:
	""" A title and the parts of a whole, which the bubble draws as a bar and a colored table and anything else reads as text. """
	title: str
	slices: tuple[Slice, ...]

	def __str__(self) -> str:
		rows = (f"{part.label}{tr(': ', ' : ')}{part.amount} ({part.share})" for part in self.slices)
		return "\n".join([self.title, *rows])

