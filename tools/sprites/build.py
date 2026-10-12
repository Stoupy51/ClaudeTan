""" Rebuilds `assets/claude/` from one frame of the source video, redrawn by the image editor.

Run `uv run build.py` in this folder, with ffmpeg and node on PATH and a CUDA GPU.

The frame is cut out onto the shared canvas and redrawn cleanly as `idle`. The editor draws the other poses from `idle`,
then closed eyes and mouth shapes on each pose, which rigs transplant.
"""
# Imports
from pathlib import Path

import cv2
import numpy as np
from cv2.typing import MatLike
from resvg_py import svg_to_bytes

from canvas import LEFT, RIGHT, bottom_fade
from colors import derim
from cutout import cut_out
from edit import CANVAS_EYES, Drawing, edit
from eyes import find_eyes
from rig import Part, Rig, transplant
from sources import read_frame

# Constants
ASSETS: Path = Path(__file__).resolve().parents[2] / "assets" / "claude"
SOURCE_FRAME: int = 3771
""" The video frame `idle` is redrawn from: hand on her heart, facing the viewer. """
MOUTH: Part = Part(box=(368, 296, 480, 372), pieces=3)
EYES: Part = Part(box=(335, 210, 515, 312), pieces=2)
KEEP: str = "Keep the same character, face, hair, outfit, art style, line work, colors, lighting, framing and plain gray background."
ONLY: str = "Change nothing else at all."
CLEAN: str = "Redraw her exactly as she is, as a crisp and clean anime illustration."
BLINK: str = "Close both of her eyes gently, as in the middle of a blink."
DRAWINGS: list[Drawing] = [
	Drawing(name="happy",    prompt="Make her smile happily, mouth open on white teeth, her hand still on her chest."),
	Drawing(name="hello",    prompt="Make her wave hello with her right hand raised beside her face, smiling warmly."),
	Drawing(name="present",  prompt="Make her proudly present a result, one palm held out to her side, with a closed-mouth smile."),
	Drawing(name="please",   prompt="Make her ask for permission, hands pressed together before her chest, closed-mouth smile."),
	Drawing(name="thanks",   prompt="Make her thank someone, hands on her cheeks, with a soft and symmetrical closed-mouth smile."),
	Drawing(name="thinking", prompt=(
		"Make her look thoughtful and pensive, her index finger touching her chin, her head and gaze unchanged."
	)),
	Drawing(name="working",  prompt="Make her look busy and focused, typing on a small keyboard floating before her chest."),
	Drawing(name="sad",      prompt=(
		"Make her look sad and apologetic, a small frown, one hand scratching the back of her head, "
		"her other arm hanging down at her side."
	)),
]
""" Each prompt is followed by `KEEP`. """
HANDS: dict[str, tuple[int, int, int, int]] = {
	"hello":   (90, 280, 350, 608),
	"present": (0, 360, 250, 608),
	"working": (325, 432, 570, 556),
}
""" Poses whose hands are the layer `hands/<pose>.png`, kept from the drawings of commit 4b95767 since the editor draws them worse now.
The canvas box is painted with `idle` first, to clear the hands the editor drew. """
SPARK: Path = Path(__file__).with_name("spark.svg")
""" A seven-pointed star like the flower in her hair, drawn in white where the editor puts a cross-shaped highlight in her pupils. """
FACES: list[str] = ["idle", *(drawing.name for drawing in DRAWINGS)]
""" Every sprite but the rigs, which blink and get their eyes checked. """
TALKERS: tuple[str, ...] = ("idle", "hello")
MOUTHS: dict[str, str] = {
	"talk_open": "Open her mouth as if saying 'ah' in the middle of a sentence.",
	"talk_o":    "Round her mouth into a small 'o' as if saying 'oh'.",
	"talk_wide": "Open her mouth in a relaxed smile, white upper teeth showing, as if saying 'ee'.",
}
RIGS: list[Rig] = [
	*[Rig(name=f"{base}_{shape}", base=base, prompt=prompt, part=MOUTH) for base in TALKERS for shape, prompt in MOUTHS.items()],
	*[Rig(name=f"{name}_blink", base=name, prompt=BLINK, part=EYES) for name in FACES],
]
""" Only `idle` and `hello` talk, every pose blinks. Each prompt is followed by `ONLY`. """


# Functions
def main() -> None:
	source = derim(cut_out(read_frame(SOURCE_FRAME), matte_name=str(SOURCE_FRAME)))
	sprites = {"idle": cut_out(edit("idle", source, f"{CLEAN} {KEEP}"))}
	for drawing in DRAWINGS:
		sprites[drawing.name] = cut_out(edit(drawing.name, sprites["idle"], f"{drawing.prompt} {KEEP}"))
	for name in HANDS:
		sprites[name] = keep_hands(sprites[name], sprites["idle"], name)

	for rig in RIGS:
		# Closed eyes defeat the iris templates, and the edit leaves her head where the base sprite had it
		donor = cut_out(edit(rig.name, sprites[rig.base], f"{rig.prompt} {ONLY}"), eyes=CANVAS_EYES)
		sprites[rig.name] = transplant(sprites[rig.base], donor, rig.part)

	for path in ASSETS.glob("*.png"):
		path.unlink()
	for name, rgba in sprites.items():
		finished = rgba if name.endswith("_blink") else stamp_sparks(rgba)
		bgra = cv2.cvtColor((bottom_fade(finished) * 255).round().astype(np.uint8), cv2.COLOR_RGBA2BGRA)
		cv2.imwrite(str(ASSETS / f"{name}.png"), bgra, [cv2.IMWRITE_PNG_COMPRESSION, 9])
	for name in FACES:
		print(f"{name}: irises {eye_offset(sprites[name]):.2f} px from the canvas eyes")


def keep_hands(pose: MatLike, idle: MatLike, name: str) -> MatLike:
	""" The pose with `idle` painted over its box in `HANDS` and the kept hands laid on top, RGBA in [0, 1]. """
	x0, y0, x1, y1 = HANDS[name]
	erase = np.zeros(pose.shape[:2], np.float32)
	erase[y0:y1, x0:x1] = 1
	erase = cv2.GaussianBlur(erase, (0, 0), 6)[..., None]
	under = pose * (1 - erase) + idle * erase

	png = cv2.imread(str(Path(__file__).with_name("hands") / f"{name}.png"), cv2.IMREAD_UNCHANGED)
	hands = cv2.cvtColor(png, cv2.COLOR_BGRA2RGBA).astype(np.float32) / 255
	alpha = hands[..., 3:]
	opacity = alpha + under[..., 3:] * (1 - alpha)
	color = (hands[..., :3] * alpha + under[..., :3] * under[..., 3:] * (1 - alpha)) / np.maximum(opacity, 1e-6)
	return np.dstack([color, opacity])


def stamp_sparks(rgba: MatLike) -> MatLike:
	""" The sprite with the white cross in each pupil inpainted away and the Claude logo drawn over where it was. """
	white = ((rgba[..., :3].min(axis=2) > 0.78) & (rgba[..., 3] > 0.9)).astype(np.uint8)
	cross = np.zeros_like(white)
	centers: list[tuple[float, float]] = []
	for x, y in (LEFT, RIGHT):
		x0, y0 = round(x) - 14, round(y) - 16
		count, labels, stats, centroids = cv2.connectedComponentsWithStats(white[y0:y0 + 28, x0:x0 + 28])
		largest = max(range(1, count), key=lambda label: stats[label, cv2.CC_STAT_AREA])
		cross[y0:y0 + 28, x0:x0 + 28][labels == largest] = 1
		centers.append((x0 + centroids[largest][0], y0 + centroids[largest][1]))
	rgb = (rgba[..., :3] * 255).round().astype(np.uint8)

	stamped = rgba.copy()
	stamped[..., :3] = cv2.inpaint(rgb, cv2.dilate(cross, np.ones((3, 3), np.uint8)), 2, cv2.INPAINT_TELEA).astype(np.float32) / 255
	png = cv2.imdecode(np.frombuffer(svg_to_bytes(svg_path=str(SPARK)), np.uint8), cv2.IMREAD_UNCHANGED)
	spark = png[..., 3].astype(np.float32) / 255
	for x, y in centers:
		shift = np.float32([[1, 0, x - spark.shape[1] / 2], [0, 1, y - spark.shape[0] / 2]])
		alpha = cv2.warpAffine(spark, shift, (rgba.shape[1], rgba.shape[0]))[..., None]
		stamped[..., :3] = stamped[..., :3] * (1 - alpha) + alpha
	return stamped


def eye_offset(rgba: MatLike) -> float:
	""" How far the irises found in the sprite sit from the canvas eyes, in canvas pixels, for the worse of the two. """
	on_white = rgba[..., :3] * rgba[..., 3:] + (1 - rgba[..., 3:])
	found = find_eyes(cv2.resize((on_white * 255).round().astype(np.uint8), None, fx=3, fy=3, interpolation=cv2.INTER_LANCZOS4))
	return max(float(np.hypot(x / 3 - cx, y / 3 - cy)) for (x, y), (cx, cy) in ((found.left, LEFT), (found.right, RIGHT)))


if __name__ == "__main__":
	main()

