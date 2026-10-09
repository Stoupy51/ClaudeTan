""" Bringing every sprite to the colors of the reference pose, whatever the lighting of its scene.

Skin, hair and the rest get separate mappings: some scenes clip skin and sweater to the same white, so one curve cannot fix both.
Statistics come from regions that the eye alignment makes comparable across sprites, in LAB space.
"""
# Imports
from dataclasses import dataclass
from typing import Self

import cv2
import numpy as np
from cv2.typing import MatLike
from numpy.typing import NDArray

from canvas import HEIGHT, WIDTH
from matting import Box

# Constants
type Curve = tuple[MatLike, MatLike]
""" Anchor inputs and outputs of a monotone piecewise-linear mapping. """
FACE_SEEDS: tuple[tuple[int, int], ...] = ((398, 312), (446, 302), (424, 352))
""" Canvas points on her cheeks and chin, skin in every frontal pose. """
WHITE_BOX: Box = (350, 385, 500, 470)
NAVY_BOX: Box = (280, 450, 570, 600)
""" Canvas boxes where the sweater and the overalls sit in every pose. """
HAIR_QUANTILES: NDArray[np.float64] = np.array([0.02, 0.1, 0.25, 0.5, 0.75, 0.9, 0.98])
HAIR_HUE: float = np.radians(42)


# Classes
@dataclass(frozen=True)
class Palette:
	""" LAB pixels of each color class of a sprite, one row per pixel. """
	skin: MatLike
	hair: MatLike
	white: MatLike
	navy: MatLike

	@classmethod
	def sample(cls, rgba: MatLike, skin: MatLike) -> Self:
		lab = to_lab(rgba)
		chroma = np.hypot(lab[..., 1], lab[..., 2])
		solid = (rgba[..., 3] > 0.95) & (skin < 0.05)
		return cls(
			skin=lab[(skin > 0.95) & (rgba[..., 3] > 0.95)],
			hair=lab[solid & (hairness(lab) > 0.95)],
			white=lab[inside(WHITE_BOX) & solid & (lab[..., 0] > 65) & (chroma < 14)],
			navy=lab[inside(NAVY_BOX) & solid & (lab[..., 0] < 40) & (lab[..., 2] < 2)],
		)


# Functions
def normalize(rgba: MatLike, skin: MatLike, reference: Palette) -> MatLike:
	""" The sprite recolored to match the reference palette.

	Args:
		skin: Soft skin mask from `skin_mask`.
	"""
	lab = to_lab(rgba)
	own = Palette.sample(rgba, skin)

	(rest_x, rest_y), rest_shift = rest_mapping(own, reference)
	rest = lab.copy()
	rest[..., 0] = apply_curve(lab[..., 0], rest_x, rest_y)
	rest[..., 1:] = lab[..., 1:] + rest_shift

	hair = lab.copy()
	for c in range(3):
		curve_x, curve_y = monotone(np.quantile(own.hair[:, c], HAIR_QUANTILES), np.quantile(reference.hair[:, c], HAIR_QUANTILES))
		hair[..., c] = apply_curve(lab[..., c], curve_x, curve_y)

	own_skin, ref_skin = np.median(own.skin, axis=0), np.median(reference.skin, axis=0)
	gain = np.clip(np.std(reference.skin[:, 0]) / max(float(np.std(own.skin[:, 0])), 1e-3), 0.85, 1.15)
	tone = lab.copy()
	tone[..., 0] = ref_skin[0] + (lab[..., 0] - own_skin[0]) * gain
	tone[..., 1:] = lab[..., 1:] + (ref_skin[1:] - own_skin[1:])

	w_skin = skin[..., None]
	w_hair = (1 - w_skin) * hairness(lab)[..., None]
	recolored = rgba.copy()
	recolored[..., :3] = to_rgb(w_skin * tone + w_hair * hair + (1 - w_skin - w_hair) * rest)
	return recolored


def rest_mapping(own: Palette, reference: Palette) -> tuple[Curve, MatLike]:
	""" Lightness curve through black, navy and white, plus the mean a and b drift of navy and white. """
	own_med = np.array([np.median(own.navy, axis=0), np.median(own.white, axis=0)])
	ref_med = np.array([np.median(reference.navy, axis=0), np.median(reference.white, axis=0)])
	xs = np.concatenate([[0.0], own_med[:, 0]])
	ys = np.concatenate([[0.0], ref_med[:, 0]])
	if own_med[1, 0] < 99:
		xs, ys = np.append(xs, 100.0), np.append(ys, 100.0)
	return monotone(xs, ys), (ref_med - own_med)[:, 1:].mean(axis=0)


def monotone(xs: MatLike, ys: MatLike) -> Curve:
	""" Anchors sorted by input, outputs made non-decreasing, near-duplicate inputs dropped. """
	order = np.argsort(xs)
	xs, ys = xs[order], np.maximum.accumulate(ys[order])
	keep = np.concatenate([[True], np.diff(xs) > 0.5])
	return xs[keep], ys[keep]


def apply_curve(values: MatLike, xs: MatLike, ys: MatLike) -> MatLike:
	""" Piecewise-linear through the anchors, continued with slope 1 past both ends. """
	mapped = np.interp(values, xs, ys)
	mapped = np.where(values < xs[0], ys[0] + (values - xs[0]), mapped)
	return np.where(values > xs[-1], ys[-1] + (values - xs[-1]), mapped)


def derim(rgba: MatLike) -> MatLike:
	""" The purple neon rim light some scenes paint on her hair outline, turned into hair-colored highlights. """
	lab = to_lab(rgba)
	chroma = np.hypot(lab[..., 1], lab[..., 2])
	hue = np.degrees(np.arctan2(lab[..., 2], lab[..., 1]))
	purple_hue = np.clip((hue + 85) / 10, 0, 1) * np.clip((5 - hue) / 10, 0, 1)
	purple = purple_hue * np.clip((chroma - 6) / 8, 0, 1) * np.clip((lab[..., 0] - 40) / 10, 0, 1)
	fixed = lab.copy()
	fixed[..., 1], fixed[..., 2] = chroma * np.cos(HAIR_HUE), chroma * np.sin(HAIR_HUE)
	derimmed = rgba.copy()
	derimmed[..., :3] = to_rgb(lab + purple[..., None] * (fixed - lab))
	return derimmed


def skin_mask(rgba: MatLike, seeds: tuple[tuple[int, int], ...]) -> MatLike:
	""" Soft mask of the light areas, bounded by line art, that contain a seed, with their light enclosed holes. """
	lab = to_lab(rgba)
	chroma = np.hypot(lab[..., 1], lab[..., 2])
	edges = np.hypot(cv2.Sobel(lab[..., 0], cv2.CV_32F, 1, 0), cv2.Sobel(lab[..., 0], cv2.CV_32F, 0, 1))
	light = (lab[..., 0] > 70) & (chroma < 34) & (edges < 60) & (rgba[..., 3] > 0.5)
	_, labels = cv2.connectedComponents(light.astype(np.uint8), connectivity=4)
	seeded: set[int] = set()
	for x, y in seeds:
		window = labels[y - 4:y + 5, x - 4:x + 5].ravel()
		values, counts = np.unique(window[window > 0], return_counts=True)
		if len(values):
			seeded.add(int(values[counts.argmax()]))
	mask = np.isin(labels, list(seeded))

	# Blush and thin lines leave holes in the light area: light holes are skin, dark ones (eyes, mouth) are not
	_, gaps = cv2.connectedComponents((~mask).astype(np.uint8), connectivity=4)
	outside = np.unique(np.concatenate([gaps[0], gaps[-1], gaps[:, 0], gaps[:, -1]]))
	count, holes = cv2.connectedComponents((~mask & ~np.isin(gaps, outside)).astype(np.uint8), connectivity=8)
	for i in range(1, count):
		hole = holes == i
		if np.median(lab[..., 0][hole]) > 70 and np.median(chroma[hole]) < 45:
			mask |= hole
	return cv2.GaussianBlur(cv2.morphologyEx(mask.astype(np.float32), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)), (0, 0), 1.5)


def hairness(lab: MatLike) -> MatLike:
	""" Soft membership of saturated warm pixels: her hair, and her irises, which share its palette. """
	chroma = np.hypot(lab[..., 1], lab[..., 2])
	hue = np.degrees(np.arctan2(lab[..., 2], lab[..., 1]))
	return np.clip((chroma - 18) / 12, 0, 1) * np.clip((hue - 10) / 8, 0, 1) * np.clip((70 - hue) / 8, 0, 1)


def inside(box: Box) -> NDArray[np.bool_]:
	x0, y0, x1, y1 = box
	mask = np.zeros((HEIGHT, WIDTH), bool)
	mask[y0:y1, x0:x1] = True
	return mask


def to_lab(rgba: MatLike) -> MatLike:
	return cv2.cvtColor(rgba[..., :3].astype(np.float32), cv2.COLOR_RGB2LAB)


def to_rgb(lab: NDArray[np.float64] | MatLike) -> MatLike:
	return cv2.cvtColor(lab.astype(np.float32), cv2.COLOR_LAB2RGB).clip(0, 1)

