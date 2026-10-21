""" The words of the demo video. """
# Imports
from screenplay import Chapter, Words

# Constants
ENGLISH: Words = Words(
	language="en",
	tagline="Talk to Claude Code. She answers on your screen.",
	outro="Runs on your Claude subscription, with Whisper on your GPU.",
	you="You",
	chapters=(
		Chapter(title="Ask out loud", subtitle="Whisper transcribes you locally, Claude Code does the work"),
		Chapter(title="Permissions by voice", subtitle="Say yes or no without touching the keyboard"),
		Chapter(title="Background work", subtitle="Long tasks go to an agent while she waits as a pill"),
		Chapter(title="Any language", subtitle="Whisper detects it, Claude answers in it"),
		Chapter(title="Make her yours", subtitle="Drag her anywhere, and set her voice from the tray"),
	),
	question="Hey Claude, what's on my screen? Done.",
	reply=("You have VS Code open on actions.py, ", "and my icon is by the clock."),
	spoken_reply="ブイエスコードが開いてるね!",
	cleanup="Hey Claude, delete the build folder, over.",
	cleanup_tool="Delete the build folder",
	yes="Yes.",
	cleaned="The build folder is gone, 212 MB freed.",
	dark_mode="Hey Claude, add a dark mode, over.",
	handed_off="An agent is on it, I'll tell you when it's done.",
	dark_mode_done="Dark mode is in, and the tests pass.",
	tests="Hey Claude, run the tests in the background, over.",
	tests_done="All 128 tests pass.",
)

