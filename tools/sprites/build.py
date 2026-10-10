""" Rebuilds `assets/claude/` from the source video and image edits.

Run `uv run build.py` in this folder, with ffmpeg and node on PATH and a CUDA GPU.

The poses of one scene are cut out of its frames onto the shared canvas and recolored like the first one.
The image editor draws the other poses from the first, then closed eyes and mouth shapes on each pose, which rigs transplant.
"""
# Imports
from pathlib import Path

import cv2
import numpy as np
from cv2.typing import MatLike

from canvas import LEFT, RIGHT, bottom_fade
from colors import FACE_SEEDS, Palette, derim, normalize, skin_mask
from cutout import Pose, cut_out
from edit import CANVAS_EYES, Drawing, edit
from eyes import find_eyes
from rig import Part, Rig, transplant
from sources import read_frame

# Constants
ASSETS: Path = Path(__file__).resolve().parents[2] / "assets" / "claude"
MOUTH: Part = Part(box=(378, 302, 456, 364), pieces=1)
EYES: Part = Part(box=(335, 210, 515, 312), pieces=2)
KEEP: str = "Keep the same character, face, hair, outfit, art style, line work, colors, lighting, framing and plain gray background."
ONLY: str = "Change nothing else at all."
BLINK: str = "Close both of her eyes gently, as in the middle of a blink."
POSES: list[Pose] = [
	Pose(name="idle",  frame=3771, hands=((460, 510),)),
	Pose(name="happy", frame=3764, hands=((460, 510),)),
]
""" The first pose sets the colors of all the others. """
DRAWINGS: list[Drawing] = [
	Drawing(name="hello",    prompt="Make her wave hello with her right hand raised beside her face, smiling warmly."),
	Drawing(name="present",  prompt="Make her proudly present a result, one palm held out to her side, with a closed-mouth smile."),
	Drawing(name="please",   prompt="Make her ask for permission, hands pressed together before her chest, closed-mouth smile."),
	Drawing(name="thanks",   prompt="Make her thank someone, hands clasped together beside her cheek, with a big grateful smile."),
	Drawing(name="thinking", prompt="Make her look thoughtful, eyes looking up to the side, her index finger touching her chin."),
	Drawing(name="working",  prompt="Make her look busy and focused, typing on a small keyboard floating before her chest."),
	Drawing(name="sad",      prompt="Make her look sad and apologetic, a small frown, one hand scratching the back of her head."),
]
""" Each prompt is followed by `KEEP`. """
FACES: list[str] = [pose.name for pose in POSES] + [drawing.name for drawing in DRAWINGS]
""" Every sprite but the rigs, which blink and get their eyes checked. """
RIGS: list[Rig] = [
	Rig(name="idle_talk_open",  base="idle",  donor=3785, part=MOUTH),
	Rig(name="idle_talk_o",     base="idle",  donor=3789, part=MOUTH),
	Rig(name="idle_talk_wide",  base="idle",  donor=3757, part=MOUTH),
	Rig(name="hello_talk_open", base="hello", donor="Open her mouth as if saying 'ah' in the middle of a sentence.", part=MOUTH),
	Rig(name="hello_talk_o",    base="hello", donor="Round her mouth into a small 'o' as if saying 'oh'.", part=MOUTH),
	Rig(name="hello_talk_wide", base="hello", donor="Open her mouth a little in a gentle smile, as if saying 'eh'.", part=MOUTH),
	*[Rig(name=f"{name}_blink", base=name, donor=BLINK, part=EYES) for name in FACES],
]
""" Only `idle` and `hello` talk, every pose blinks. Each prompt is followed by `ONLY`. """


# Functions
def main() -> None:
	cutouts = {pose.name: derim(cut_out(read_frame(pose.frame), matte_name=str(pose.frame))) for pose in POSES}
	skins = {pose.name: skin_mask(cutouts[pose.name], FACE_SEEDS + pose.hands) for pose in POSES}
	reference = Palette.sample(cutouts[POSES[0].name], skins[POSES[0].name])
	sprites = {pose.name: normalize(cutouts[pose.name], skins[pose.name], reference) for pose in POSES}
	for drawing in DRAWINGS:
		sprites[drawing.name] = cut_out(edit(drawing.name, sprites[POSES[0].name], f"{drawing.prompt} {KEEP}"))
	for rig in RIGS:
		if isinstance(rig.donor, int):
			donor = derim(cut_out(read_frame(rig.donor), matte_name=str(rig.donor)))
			donor = normalize(donor, skin_mask(donor, FACE_SEEDS), reference)
		else:
			# Closed eyes defeat the iris templates, and the edit leaves her head where the base sprite had it
			donor = cut_out(edit(rig.name, sprites[rig.base], f"{rig.donor} {ONLY}"), eyes=CANVAS_EYES)
		sprites[rig.name] = transplant(sprites[rig.base], donor, rig.part)

	for path in ASSETS.glob("*.png"):
		path.unlink()
	for name, rgba in sprites.items():
		bgra = cv2.cvtColor((bottom_fade(rgba) * 255).round().astype(np.uint8), cv2.COLOR_RGBA2BGRA)
		cv2.imwrite(str(ASSETS / f"{name}.png"), bgra, [cv2.IMWRITE_PNG_COMPRESSION, 9])
	for name in FACES:
		print(f"{name}: irises {eye_offset(sprites[name]):.2f} px from the canvas eyes")


def eye_offset(rgba: MatLike) -> float:
	""" How far the irises found in the sprite sit from the canvas eyes, in canvas pixels, for the worse of the two. """
	on_white = rgba[..., :3] * rgba[..., 3:] + (1 - rgba[..., 3:])
	found = find_eyes(cv2.resize((on_white * 255).round().astype(np.uint8), None, fx=3, fy=3, interpolation=cv2.INTER_LANCZOS4))
	return max(float(np.hypot(x / 3 - cx, y / 3 - cy)) for (x, y), (cx, cy) in ((found.left, LEFT), (found.right, RIGHT)))


if __name__ == "__main__":
	main()

