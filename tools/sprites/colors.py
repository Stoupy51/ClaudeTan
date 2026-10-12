""" The purple neon rim light of the source frame, repainted in the colors of her hair, in LAB space. """
# Imports
import cv2
import numpy as np
from cv2.typing import MatLike
from numpy.typing import NDArray

# Constants
HAIR_HUE: float = np.radians(42)


# Functions
def derim(rgba: MatLike) -> MatLike:
	""" The purple neon rim light on her hair outline, turned into hair-colored highlights. """
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


def to_lab(rgba: MatLike) -> MatLike:
	return cv2.cvtColor(rgba[..., :3].astype(np.float32), cv2.COLOR_RGB2LAB)


def to_rgb(lab: NDArray[np.float64] | MatLike) -> MatLike:
	return cv2.cvtColor(lab.astype(np.float32), cv2.COLOR_LAB2RGB).clip(0, 1)

