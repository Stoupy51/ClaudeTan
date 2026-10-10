""" Cutting her out of a frame with ToonOut, a BiRefNet fine-tuned on anime characters. """
# Imports
from functools import cache

import cv2
import numpy as np
import torch
from cv2.typing import MatLike
from transformers import AutoConfig, AutoModelForImageSegmentation

from sources import fetch

# Constants
type Box = tuple[int, int, int, int]
""" Left, top, right and bottom edges, in frame pixels. """
TOONOUT_URL: str = "https://huggingface.co/joelseytre/toonout/resolve/main/birefnet_finetuned_toonout.pth"
INPUT_SIZE: int = 1024
MEAN: MatLike = np.array([0.485, 0.456, 0.406], np.float32)
STD: MatLike = np.array([0.229, 0.224, 0.225], np.float32)
""" ImageNet normalization, which BiRefNet was trained with. """


# Functions
def matte(frame: MatLike) -> MatLike:
	""" Her alpha over the frame.

	A first pass finds her, a second pass on a crop around her gives the model more pixels for the edges.
	"""
	ys, xs = np.nonzero(largest_components(predict(frame)) > 0.5)
	pad = round(0.08 * max(xs.max() - xs.min(), ys.max() - ys.min()))
	bx0, by0 = max(0, xs.min() - pad), max(0, ys.min() - pad)
	bx1, by1 = min(frame.shape[1], xs.max() + pad), min(frame.shape[0], ys.max() + pad)

	alpha = np.zeros(frame.shape[:2], np.float32)
	alpha[by0:by1, bx0:bx1] = largest_components(predict(frame[by0:by1, bx0:bx1]))
	return alpha


def predict(rgb: MatLike) -> MatLike:
	normalized = (cv2.resize(rgb, (INPUT_SIZE, INPUT_SIZE), interpolation=cv2.INTER_AREA).astype(np.float32) / 255 - MEAN) / STD
	with torch.no_grad():
		tensor = torch.as_tensor(normalized.transpose(2, 0, 1).copy())[None].cuda().half()
		mask: MatLike = model()(tensor)[-1].sigmoid().float().cpu().numpy()[0, 0]
	return cv2.resize(mask, (rgb.shape[1], rgb.shape[0]), interpolation=cv2.INTER_CUBIC).clip(0, 1)


@cache
def model() -> torch.nn.Module:
	config = AutoConfig.from_pretrained("ZhengPeng7/BiRefNet", trust_remote_code=True)
	net = AutoModelForImageSegmentation.from_config(config, trust_remote_code=True)
	state: dict[str, torch.Tensor] = torch.load(fetch(TOONOUT_URL), map_location="cpu", weights_only=True)
	net.load_state_dict({key.removeprefix("module._orig_mod.").removeprefix("module."): value for key, value in state.items()})
	return net.to("cuda").eval().half()


def largest_components(mask: MatLike) -> MatLike:
	""" The mask without specks: blobs under 15% of the largest one are dropped. """
	count, labels, stats, _ = cv2.connectedComponentsWithStats((mask > 0.5).astype(np.uint8), connectivity=8)
	if count <= 1:
		return mask
	areas = stats[1:, cv2.CC_STAT_AREA]
	keep = [i + 1 for i, area in enumerate(areas) if area >= areas.max() * 0.15]
	return mask * cv2.dilate(np.isin(labels, keep).astype(np.uint8), np.ones((15, 15), np.uint8))


def foreground(image: MatLike, alpha: MatLike) -> MatLike:
	""" Her own colors along the semi-transparent edges, without the background blended in (blur fusion, Forte and Pitie 2021). """
	first, background = blur_fusion(image, image, image, alpha, 180)
	return blur_fusion(image, first, background, alpha, 9)[0]


def blur_fusion(
	image: MatLike, fore: MatLike, back: MatLike, alpha: MatLike, radius: int,
) -> tuple[MatLike, MatLike]:
	a = alpha[..., None]
	blurred_alpha = cv2.blur(alpha, (radius, radius))[..., None]
	blurred_fore = cv2.blur(fore * a, (radius, radius)) / (blurred_alpha + 1e-5)
	blurred_back = cv2.blur(back * (1 - a), (radius, radius)) / (1 - blurred_alpha + 1e-5)
	return np.clip(blurred_fore + a * (image - a * blurred_fore - (1 - a) * blurred_back), 0, 1), blurred_back

