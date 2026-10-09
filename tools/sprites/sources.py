""" Everything the pipeline downloads, cached in `.work/`: the source video and its frames, and model files. """
# Imports
import subprocess
import sys
import urllib.request
from pathlib import Path

import cv2
from cv2.typing import MatLike

# Constants
WORK: Path = Path(__file__).resolve().parent / ".work"
""" Downloads, decoded frames and cached mattes, ignored by git. """
VIDEO_URL: str = "https://www.youtube.com/watch?v=_m38WbRlzv0"
VIDEO_FORMAT: str = "313"
""" YouTube's 3840x2160 VP9 stream. Every frame number in the pipeline counts frames of its 30 fps timeline. """
FPS: int = 30


# Functions
def fetch(url: str) -> Path:
	""" Local copy of a file, downloaded on first use. """
	path = WORK / url.rsplit("/", 1)[-1]
	if not path.exists():
		path.parent.mkdir(parents=True, exist_ok=True)
		urllib.request.urlretrieve(url, path)
	return path


def read_frame(n: int) -> MatLike:
	""" RGB frame `n` of the video, decoded once and kept as a PNG. """
	path = WORK / "frames" / f"{n}.png"
	if not path.exists():
		video = WORK / "source_4k.webm"
		if not video.exists():
			download = [sys.executable, "-m", "yt_dlp", "--js-runtimes", "node", "-f", VIDEO_FORMAT, "-o", str(video), VIDEO_URL]
			subprocess.run(download, check=True)
		path.parent.mkdir(parents=True, exist_ok=True)
		# Seeking half a frame early is what makes ffmpeg land exactly on frame n
		seek = f"{(n - 0.5) / FPS:.4f}"
		subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", seek, "-i", str(video), "-frames:v", "1", str(path)], check=True)
	image = cv2.imread(str(path))
	assert image is not None
	return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

