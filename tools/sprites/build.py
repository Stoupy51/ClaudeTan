""" Rebuilds `assets/claude/` from the source video. Run `uv run build.py` in this folder, with ffmpeg and node on PATH and a CUDA GPU.

Every pose is cut out of one frame onto the shared canvas and recolored like the first pose.
Rigs then give poses mouth and eye variants taken from neighboring frames, for talking and blinking.
"""
# Imports
from pathlib import Path

import cv2
import numpy as np
from cv2.typing import MatLike

from canvas import LEFT, RIGHT, bottom_fade
from colors import FACE_SEEDS, Palette, derim, normalize, skin_mask
from cutout import Pose, cut_out
from eyes import find_eyes
from matting import Box
from rig import Part, Rig, transplant

# Constants
ASSETS: Path = Path(__file__).resolve().parents[2] / "assets" / "claude"
MOUTH: Part = Part(box=(378, 302, 456, 364), pieces=1)
EYES: Part = Part(box=(340, 236, 510, 312), pieces=2)
PRAYER_CLIP: Box = (2235, 0, 3175, 1950)
""" Inside the shelves that frame her in the prayer scene. """
PRAYER_HANDS: tuple[tuple[int, int], ...] = ((430, 420), (440, 500))
SHELF_CORNER: Box = (2930, 0, 3240, 275)
""" A shelf corner the matte keeps above her head in the thanks frame. """
BENCH: Box = (2330, 640, 2620, 1000)
""" The striped bench the matte glues to her hair in the pointing frame. """
BLINK_FRAME: int = 1998
BLINK_EYES: tuple[tuple[float, float], tuple[float, float]] = ((2675.5, 1259.7), (2905.5, 1216.9))
""" Eye centers of the open-eyed frame just before the blink, which the iris templates cannot find with the eyes closed. """
POSES: list[Pose] = [
	Pose(name="idle",      frame=3771, hands=((460, 510),)),
	Pose(name="happy",     frame=3764, hands=((460, 510),)),
	Pose(name="surprised", frame=3760, hands=((460, 510),)),
	Pose(name="hello",     frame=72,   hands=((270, 350),)),
	Pose(name="present",   frame=134,  hands=((230, 545),), clip=(0, 0, 3840, 1400), upscale=True),
	Pose(name="please",    frame=5987, hands=PRAYER_HANDS, clip=PRAYER_CLIP),
	Pose(name="thanks",    frame=5979, hands=PRAYER_HANDS, clip=PRAYER_CLIP, erase=(SHELF_CORNER,)),
	Pose(name="point",     frame=3512, hands=((130, 260),), eyes=((1984, 627), (2102, 604)), hair_only=(BENCH,), upscale=True),
	Pose(name="stand",     frame=3489, upscale=True),
]
""" The first pose sets the colors of all the others. `present` is clipped above the reflecting floor. """
RIGS: list[Rig] = [
	Rig(name="idle_talk_open",  base="idle",  frame=3785, part=MOUTH),
	Rig(name="idle_talk_o",     base="idle",  frame=3789, part=MOUTH),
	Rig(name="idle_talk_wide",  base="idle",  frame=3757, part=MOUTH),
	Rig(name="hello_talk_open", base="hello", frame=93,   part=MOUTH),
	Rig(name="hello_talk_o",    base="hello", frame=82,   part=MOUTH),
	Rig(name="hello_talk_wide", base="hello", frame=67,   part=MOUTH),
	*[Rig(name=f"{pose.name}_blink", base=pose.name, frame=BLINK_FRAME, part=EYES, eyes=BLINK_EYES) for pose in POSES],
]
""" Only `idle` and `hello` talk, every pose blinks with the closed eyes of the same frame. """


# Functions
def main() -> None:
	cutouts = {pose.name: derim(cut_out(pose)) for pose in POSES}
	skins = {pose.name: skin_mask(cutouts[pose.name], FACE_SEEDS + pose.hands) for pose in POSES}
	reference = Palette.sample(cutouts[POSES[0].name], skins[POSES[0].name])
	sprites = {pose.name: normalize(cutouts[pose.name], skins[pose.name], reference) for pose in POSES}
	for rig in RIGS:
		donor = derim(cut_out(Pose(name=rig.name, frame=rig.frame, eyes=rig.eyes)))
		sprites[rig.name] = transplant(sprites[rig.base], normalize(donor, skin_mask(donor, FACE_SEEDS), reference), rig.part)

	for name, rgba in sprites.items():
		bgra = cv2.cvtColor((bottom_fade(rgba) * 255).round().astype(np.uint8), cv2.COLOR_RGBA2BGRA)
		cv2.imwrite(str(ASSETS / f"{name}.png"), bgra, [cv2.IMWRITE_PNG_COMPRESSION, 9])
	for pose in POSES:
		if pose.eyes is None:
			print(f"{pose.name}: irises {eye_offset(sprites[pose.name]):.2f} px from the canvas eyes")


def eye_offset(rgba: MatLike) -> float:
	""" How far the irises found in the sprite sit from the canvas eyes, in canvas pixels, for the worse of the two. """
	on_white = rgba[..., :3] * rgba[..., 3:] + (1 - rgba[..., 3:])
	found = find_eyes(cv2.resize((on_white * 255).round().astype(np.uint8), None, fx=3, fy=3, interpolation=cv2.INTER_LANCZOS4))
	return max(float(np.hypot(x / 3 - cx, y / 3 - cy)) for (x, y), (cx, cy) in ((found.left, LEFT), (found.right, RIGHT)))


if __name__ == "__main__":
	main()

