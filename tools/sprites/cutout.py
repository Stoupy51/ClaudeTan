""" Cutting one pose out of its frame and onto the shared canvas. """
# Imports
from dataclasses import dataclass

import cv2
import numpy as np
from cv2.typing import MatLike

from canvas import render
from eyes import Eyes, Point, find_eyes
from matting import Box, matte
from sources import WORK, read_frame

# Constants
FULL_FRAME: Box = (0, 0, 3840, 2160)


# Classes
@dataclass(frozen=True)
class Pose:
	""" A sprite cut out of one frame of the video. """
	name: str
	frame: int
	hands: tuple[tuple[int, int], ...] = ()
	""" Canvas points on her visible hands, so their skin is recolored like her face. """
	clip: Box = FULL_FRAME
	""" Frame region she is cut from; whatever crosses its edges fades out. """
	erase: tuple[Box, ...] = ()
	""" Frame regions removed from the matte. """
	hair_only: tuple[Box, ...] = ()
	""" Frame regions where the matte keeps only hair-colored pixels, dropping props it glued to her hair. """
	eyes: tuple[Point, Point] | None = None
	""" Eye centers read off a grid, where the iris templates cannot find them (closed eyes, averted gaze). """
	upscale: bool = False
	""" Whether the shot is too distant to enlarge without the anime upscaler. """


# Functions
def cut_out(pose: Pose) -> MatLike:
	""" RGBA canvas of the pose, values in [0, 1], her eyes on the canvas eyes. """
	frame = read_frame(pose.frame)
	alpha = cached_matte(pose, frame)
	for x0, y0, x1, y1 in pose.erase:
		alpha[y0:y1, x0:x1] = 0
	for x0, y0, x1, y1 in pose.hair_only:
		alpha[y0:y1, x0:x1] *= hair_mask(frame[y0:y1, x0:x1])
	eyes = Eyes(left=pose.eyes[0], right=pose.eyes[1]) if pose.eyes else find_eyes(frame)
	return render(frame, alpha, eyes, pose.clip, upscale=pose.upscale)


def cached_matte(pose: Pose, frame: MatLike) -> MatLike:
	""" `matte` of the pose's frame, kept as a 16-bit PNG since it is the slowest step. """
	path = WORK / "mattes" / f"{pose.frame}_{'_'.join(map(str, pose.clip))}.png"
	if (cached := cv2.imread(str(path), cv2.IMREAD_UNCHANGED)) is not None:
		return cached.astype(np.float32) / 65535
	alpha = matte(frame, pose.clip)
	path.parent.mkdir(parents=True, exist_ok=True)
	cv2.imwrite(str(path), (alpha * 65535).round().astype(np.uint16))
	return alpha


def hair_mask(rgb: MatLike) -> MatLike:
	""" Soft mask of her red-orange hair. """
	hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
	hue, saturation, value = hsv[..., 0], hsv[..., 1] / 255, hsv[..., 2] / 255
	hair = ((hue <= 22) | (hue >= 172)) & (saturation >= 0.3) & (value >= 0.25)
	return cv2.GaussianBlur(cv2.dilate(hair.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(np.float32), (0, 0), 1.5)

