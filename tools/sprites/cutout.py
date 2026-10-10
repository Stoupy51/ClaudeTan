""" Cutting her out of a frame and onto the shared canvas. """
# Imports
from dataclasses import dataclass

import cv2
import numpy as np
from cv2.typing import MatLike

from canvas import render
from eyes import Eyes, find_eyes
from matting import matte
from sources import WORK


# Classes
@dataclass(frozen=True)
class Pose:
	""" A sprite cut out of one frame of the video. """
	name: str
	frame: int
	hands: tuple[tuple[int, int], ...] = ()
	""" Canvas points on her visible hands, so their skin is recolored like her face. """


# Functions
def cut_out(frame: MatLike, eyes: Eyes | None = None, matte_name: str | None = None) -> MatLike:
	""" RGBA canvas of her, values in [0, 1], her eyes on the canvas eyes.

	Args:
		frame:      RGB uint8, a video frame or an edit.
		eyes:       Her eye centers in the frame, found by the iris templates when None.
		matte_name: Name the matte is cached under, for frames that never change.
	"""
	alpha = matte(frame) if matte_name is None else cached_matte(matte_name, frame)
	return render(frame, alpha, eyes or find_eyes(frame))


def cached_matte(name: str, frame: MatLike) -> MatLike:
	""" `matte` of the frame, kept as a 16-bit PNG since it is the slowest step. """
	path = WORK / "mattes" / f"{name}.png"
	if (cached := cv2.imread(str(path), cv2.IMREAD_UNCHANGED)) is not None:
		return cached.astype(np.float32) / 65535
	alpha = matte(frame)
	path.parent.mkdir(parents=True, exist_ok=True)
	cv2.imwrite(str(path), (alpha * 65535).round().astype(np.uint16))
	return alpha

