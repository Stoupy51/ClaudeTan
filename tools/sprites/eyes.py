""" Where her eyes are in a frame: an anime face cascade finds the face, then each iris of the idle frame is matched inside it. """
# Imports
from dataclasses import dataclass
from functools import cache

import cv2
import numpy as np
from cv2.typing import MatLike
from numpy.typing import NDArray

from sources import fetch, read_frame

# Constants
type Point = tuple[float, float]
CASCADE_URL: str = "https://raw.githubusercontent.com/nagadomi/lbpcascade_animeface/master/lbpcascade_animeface.xml"
REF_FRAME: int = 3771
REF_LEFT: Point = (2487.0, 1085.0)
REF_RIGHT: Point = (2727.0, 1035.0)
""" Iris centers in the idle frame, read off a grid; the irises around them are the templates. """
TEMPLATE_HALF: tuple[int, int] = (70, 56)
""" Half width and half height of an iris template, in frame pixels. """


# Classes
@dataclass(frozen=True)
class Eyes:
	""" Eye centers in frame pixels, `left` being the one on the viewer's left. """
	left: Point
	right: Point

	@property
	def mid(self) -> Point:
		return (self.left[0] + self.right[0]) / 2, (self.left[1] + self.right[1]) / 2

	@property
	def iod(self) -> float:
		""" Inter-ocular distance. """
		return float(np.hypot(self.right[0] - self.left[0], self.right[1] - self.left[1]))


@dataclass(frozen=True)
class Match:
	score: float
	center: Point
	scale: float
	angle: float


# Functions
def find_eyes(frame: MatLike) -> Eyes:
	""" Iris centers of the largest anime face, to a fraction of a pixel. """
	x, y, w, h = detect_face(frame)
	zoom = Eyes(REF_LEFT, REF_RIGHT).iod / (0.35 * w)
	x0, y0 = max(0, x - w // 4), max(0, y - h // 6)
	x1, y1 = min(frame.shape[1], x + w + w // 4), min(frame.shape[0], y + h)
	interpolation = cv2.INTER_AREA if zoom < 1 else cv2.INTER_CUBIC
	region = cv2.resize(gray(frame[y0:y1, x0:x1]), None, fx=zoom, fy=zoom, interpolation=interpolation)

	middle = region.shape[1] // 2
	found: list[Point] = []
	for template, (lo, hi) in zip(templates(), ((0, middle + 40), (middle - 40, region.shape[1])), strict=True):
		cx, cy = locate(region[:, lo:hi], template)
		found.append((x0 + (lo + cx) / zoom, y0 + cy / zoom))
	return Eyes(left=found[0], right=found[1])


def detect_face(frame: MatLike) -> tuple[int, int, int, int]:
	""" Left, top, width and height of the largest anime face, in frame pixels. """
	small = cv2.resize(frame, (frame.shape[1] // 4, frame.shape[0] // 4), interpolation=cv2.INTER_AREA)
	equalized = cv2.equalizeHist(cv2.cvtColor(small, cv2.COLOR_RGB2GRAY))
	faces = cascade().detectMultiScale(equalized, scaleFactor=1.05, minNeighbors=4, minSize=(30, 30))
	x, y, w, h = max(faces, key=lambda face: face[2] * face[3])
	return int(x) * 4, int(y) * 4, int(w) * 4, int(h) * 4


@cache
def cascade() -> cv2.CascadeClassifier:
	return cv2.CascadeClassifier(str(fetch(CASCADE_URL)))


@cache
def templates() -> tuple[MatLike, MatLike]:
	reference = gray(read_frame(REF_FRAME))
	hw, hh = TEMPLATE_HALF
	left, right = (reference[round(y) - hh:round(y) + hh, round(x) - hw:round(x) + hw].copy() for x, y in (REF_LEFT, REF_RIGHT))
	return left, right


def gray(rgb: MatLike) -> MatLike:
	return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)


def locate(region: MatLike, template: MatLike) -> Point:
	""" Center of the template in the region, searched over scales and rotations, then refined around the best pair. """
	coarse = best_match(region, template, np.arange(0.8, 1.26, 0.04), np.arange(-14, 15, 3.5))
	scales = np.arange(coarse.scale - 0.03, coarse.scale + 0.031, 0.01)
	return best_match(region, template, scales, np.arange(coarse.angle - 2, coarse.angle + 2.1, 1)).center


def best_match(region: MatLike, template: MatLike, scales: NDArray[np.float64], angles: NDArray[np.float64]) -> Match:
	matches = (match_at(region, template, float(scale), float(angle)) for scale in scales for angle in angles)
	return max(matches, key=lambda match: match.score)


def match_at(region: MatLike, template: MatLike, scale: float, angle: float) -> Match:
	th, tw = template.shape
	rotation = cv2.getRotationMatrix2D((tw / 2, th / 2), angle, scale)
	warped = cv2.warpAffine(template, rotation, (tw, th), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
	scores = cv2.matchTemplate(region, warped, cv2.TM_CCOEFF_NORMED)
	_, score, _, (x, y) = cv2.minMaxLoc(scores)
	dx = parabola_peak(scores[y, x - 1], scores[y, x], scores[y, x + 1]) if 0 < x < scores.shape[1] - 1 else 0.0
	dy = parabola_peak(scores[y - 1, x], scores[y, x], scores[y + 1, x]) if 0 < y < scores.shape[0] - 1 else 0.0
	return Match(score=score, center=(x + dx + tw / 2, y + dy + th / 2), scale=scale, angle=angle)


def parabola_peak(before: float, at: float, after: float) -> float:
	""" Offset of the true maximum from the sampled one, in samples, from a parabola through three neighbors. """
	curvature = before - 2 * at + after
	return 0.5 * (before - after) / curvature if curvature else 0.0

