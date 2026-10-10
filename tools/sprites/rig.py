""" Face parts of other frames or of edits of a pose, transplanted onto it: mouth shapes for talking, closed eyes for blinking. """
# Imports
from dataclasses import dataclass

import cv2
import numpy as np
from cv2.typing import MatLike

from colors import to_lab
from matting import Box


# Classes
@dataclass(frozen=True)
class Part:
	""" A face part that a donor frame may replace. """
	box: Box
	""" Where it sits on the canvas. """
	pieces: int
	""" How many separate areas it holds: one mouth, two eyes with their eyebrows. """


@dataclass(frozen=True)
class Rig:
	""" A pose with one face part taken from another frame or redrawn. """
	name: str
	base: str
	donor: int | str
	""" Video frame the part is taken from, or the prompt that redraws the base sprite with it. """
	part: Part


# Functions
def transplant(base: MatLike, donor: MatLike, part: Part) -> MatLike:
	""" The base sprite wearing the donor's version of the part, aligned and recolored to melt in. """
	donor = match_colors(base, align_locally(base, donor, part.box), part.box)
	mask = changed_region(base, donor, part)
	result = base * (1 - mask) + donor * mask
	result[..., 3] = base[..., 3]
	return result


def align_locally(base: MatLike, donor: MatLike, box: Box) -> MatLike:
	""" The donor warped onto the base by ECC on the surroundings of the box, which stay put while the part itself changes. """
	x0, y0, x1, y1 = box
	mx, my = (x1 - x0) // 2 + 30, (y1 - y0) // 2 + 30
	mask = np.zeros(base.shape[:2], np.uint8)
	mask[y0 - my:y1 + my, x0 - mx:x1 + mx] = 255
	mask[y0:y1, x0:x1] = 0
	criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 300, 1e-6)
	try:
		identity = np.eye(2, 3, dtype=np.float32)
		_, warp = cv2.findTransformECC(gray_on_neutral(base), gray_on_neutral(donor), identity, cv2.MOTION_AFFINE, criteria, mask, 3)
	except cv2.error:
		return donor
	# A shift of more than a few pixels means ECC locked onto something else, the canvas eyes already agree
	if abs(warp[0, 2]) > 6 or abs(warp[1, 2]) > 6:
		return donor
	size = (base.shape[1], base.shape[0])
	return cv2.warpAffine(donor, warp, size, flags=cv2.INTER_CUBIC + cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_CONSTANT)


def match_colors(base: MatLike, donor: MatLike, box: Box) -> MatLike:
	""" The donor with the LAB mean and spread of the base, measured on a ring around the box. """
	x0, y0, x1, y1 = box
	ring = np.zeros(base.shape[:2], bool)
	ring[y0 - 20:y1 + 20, x0 - 20:x1 + 20] = True
	ring[y0:y1, x0:x1] = False
	ring &= (base[..., 3] > 0.95) & (donor[..., 3] > 0.95)
	base_lab, donor_lab = to_lab(base)[ring], to_lab(donor)
	gain = np.clip(base_lab.std(0) / np.maximum(donor_lab[ring].std(0), 1e-3), 0.8, 1.25)
	matched = donor.copy()
	recolored = (donor_lab - donor_lab[ring].mean(0)) * gain + base_lab.mean(0)
	matched[..., :3] = cv2.cvtColor(recolored.astype(np.float32), cv2.COLOR_LAB2RGB).clip(0, 1)
	return matched


def changed_region(base: MatLike, donor: MatLike, part: Part) -> MatLike:
	""" Feathered mask, shaped for broadcasting over RGBA, of the largest areas inside the part box where the donor differs. """
	x0, y0, x1, y1 = part.box
	diff = cv2.GaussianBlur(np.abs(gray_on_neutral(donor) - gray_on_neutral(base)), (0, 0), 2)
	region = np.zeros(diff.shape, np.uint8)
	region[y0:y1, x0:x1] = diff[y0:y1, x0:x1] > 0.05
	region = cv2.morphologyEx(region, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
	_, labels, stats, _ = cv2.connectedComponentsWithStats(region)
	largest = 1 + np.argsort(stats[1:, cv2.CC_STAT_AREA])[::-1][:part.pieces]
	kept = np.isin(labels, [i for i in largest if stats[i, cv2.CC_STAT_AREA] > 40])
	region = cv2.dilate(kept.astype(np.uint8), np.ones((7, 7), np.uint8))

	inside_box = np.zeros(region.shape, np.float32)
	inside_box[y0:y1, x0:x1] = 1
	return (cv2.GaussianBlur(region.astype(np.float32), (0, 0), 3) * cv2.GaussianBlur(inside_box, (0, 0), 3))[..., None]


def gray_on_neutral(rgba: MatLike) -> MatLike:
	return cv2.cvtColor(rgba[..., :3] * rgba[..., 3:] + 0.5 * (1 - rgba[..., 3:]), cv2.COLOR_RGB2GRAY)

