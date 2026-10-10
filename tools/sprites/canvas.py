""" The shared sprite canvas: every cut-out lands with her eyes on the same pixels, faded where the source frame cut her off. """
# Imports
from functools import cache

import cv2
import numpy as np
import torch
from cv2.typing import MatLike
from numpy.typing import NDArray
from spandrel import ImageModelDescriptor, ModelLoader

from eyes import Eyes, Point
from matting import Box, foreground
from sources import fetch

# Constants
WIDTH, HEIGHT = 850, 608
IOD: float = 87.0
MID: Point = (425.0, 280.0)
TILT: float = np.radians(11.8)
""" Head tilt of the idle pose, kept for every sprite so the reference itself is not rotated. """
LEFT: Point = (MID[0] - IOD / 2 * np.cos(TILT), MID[1] + IOD / 2 * np.sin(TILT))
RIGHT: Point = (MID[0] + IOD / 2 * np.cos(TILT), MID[1] - IOD / 2 * np.sin(TILT))
EDGE_FADE: float = 90.0
""" Width of the fade where the frame cuts her, in canvas pixels. """
FADE_ROWS: tuple[int, int] = (430, 604)
""" Rows where the shared bottom fade starts and reaches zero. """
UPSCALER_URL: str = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.2.4/RealESRGAN_x4plus_anime_6B.pth"
TILE, TILE_OVERLAP = 384, 16


# Functions
def render(frame: MatLike, alpha: MatLike, eyes: Eyes) -> MatLike:
	""" RGBA canvas of her, values in [0, 1], fading out where the edges of the frame cross her. """
	transform = similarity(eyes)
	scale = float(np.hypot(transform[0, 0], transform[1, 0]))
	ys, xs = np.nonzero(alpha > 0.002)
	x0, y0 = max(0, xs.min() - 40), max(0, ys.min() - 40)
	x1, y1 = min(frame.shape[1], xs.max() + 41), min(frame.shape[0], ys.max() + 41)
	crop_alpha = alpha[y0:y1, x0:x1]
	colors = foreground(frame[y0:y1, x0:x1].astype(np.float32) / 255, crop_alpha)

	# Work at twice the canvas resolution, then downsample, for clean edges
	h, w = crop_alpha.shape
	big = cv2.resize(colors, (round(w * scale * 2), round(h * scale * 2)), interpolation=cv2.INTER_AREA)
	bh, bw = big.shape[:2]
	big_alpha = cv2.resize(crop_alpha, (bw, bh), interpolation=cv2.INTER_AREA)
	linear = transform[:, :2] @ np.diag([w / bw, h / bh])
	offset = transform[:, :2] @ np.array([x0, y0]) + transform[:, 2]
	to_canvas = 2 * np.hstack([linear, offset[:, None]])
	size = (WIDTH * 2, HEIGHT * 2)
	rgb = cv2.warpAffine(big, to_canvas, size, flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
	opacity = cv2.warpAffine(big_alpha, to_canvas, size, flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=0)

	opacity = opacity.clip(0, 1) * edge_fade(transform, (0, 0, frame.shape[1], frame.shape[0]))
	return np.dstack([
		cv2.resize(rgb, (WIDTH, HEIGHT), interpolation=cv2.INTER_AREA).clip(0, 1),
		cv2.resize(opacity, (WIDTH, HEIGHT), interpolation=cv2.INTER_AREA).clip(0, 1),
	])


def similarity(eyes: Eyes) -> NDArray[np.float64]:
	""" 2x3 matrix from frame pixels to canvas pixels that lands both eyes exactly on the canvas eyes. """
	source = np.subtract(eyes.right, eyes.left)
	target = np.subtract(RIGHT, LEFT)
	scale = np.hypot(*target) / np.hypot(*source)
	theta = np.arctan2(target[1], target[0]) - np.arctan2(source[1], source[0])
	rotation = scale * np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
	return np.hstack([rotation, (np.asarray(MID) - rotation @ np.asarray(eyes.mid))[:, None]])


def edge_fade(transform: NDArray[np.float64], clip: Box) -> MatLike:
	""" Smoothstep from 0 on the edges of `clip` to 1 at `EDGE_FADE` inside them, at twice the canvas resolution. """
	x0, y0, x1, y1 = clip
	corners = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], np.float64)
	inside = np.zeros((HEIGHT * 2, WIDTH * 2), np.uint8)
	cv2.fillPoly(inside, [(2 * (corners @ transform[:, :2].T + transform[:, 2])).round().astype(np.int32)], 1)
	inside[0, :] = inside[-1, :] = inside[:, 0] = inside[:, -1] = 1
	t = np.clip(cv2.distanceTransform(inside, cv2.DIST_L2, 5) / 2 / EDGE_FADE, 0, 1)
	return t * t * (3 - 2 * t)


def upscale4(rgb: MatLike) -> MatLike:
	""" 4x enlargement by Real-ESRGAN anime, run by tiles to bound GPU memory. """
	h, w = rgb.shape[:2]
	out = np.zeros((h * 4, w * 4, 3), np.float32)
	for ty in range(0, h, TILE):
		for tx in range(0, w, TILE):
			ax0, ay0 = max(0, tx - TILE_OVERLAP), max(0, ty - TILE_OVERLAP)
			ax1, ay1 = min(w, tx + TILE + TILE_OVERLAP), min(h, ty + TILE + TILE_OVERLAP)
			with torch.no_grad():
				tile = torch.as_tensor(rgb[ay0:ay1, ax0:ax1].transpose(2, 0, 1).copy())[None].cuda().half()
				up = upscaler()(tile).clamp(0, 1)[0].float().cpu().numpy().transpose(1, 2, 0)
			cw, ch = (min(tx + TILE, w) - tx) * 4, (min(ty + TILE, h) - ty) * 4
			out[ty * 4:ty * 4 + ch, tx * 4:tx * 4 + cw] = up[(ty - ay0) * 4:(ty - ay0) * 4 + ch, (tx - ax0) * 4:(tx - ax0) * 4 + cw]
	return out


@cache
def upscaler() -> ImageModelDescriptor:
	model = ModelLoader().load_from_file(fetch(UPSCALER_URL))
	assert isinstance(model, ImageModelDescriptor)
	return model.cuda().eval().half()


def bottom_fade(rgba: MatLike) -> MatLike:
	""" The sprite fading out towards the bottom of the canvas, the same way for every sprite. """
	top, bottom = FADE_ROWS
	t = np.clip((np.arange(HEIGHT) - top) / (bottom - top), 0, 1)
	faded = rgba.copy()
	faded[..., 3] *= (1 - t * t * (3 - 2 * t))[:, None]
	return faded

