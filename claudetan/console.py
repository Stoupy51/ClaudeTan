""" The terminal the command-line entry points print to. """
# Imports
import ctypes

# Constants
STD_OUTPUT_HANDLE: int = -11
ENABLE_VIRTUAL_TERMINAL_PROCESSING: int = 0x4


# Functions
def enable_colors() -> None:
	""" Turns on color codes in the console, which Windows' classic console prints as text otherwise. """
	kernel32 = ctypes.windll.kernel32
	console = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
	mode = ctypes.c_uint32()
	if kernel32.GetConsoleMode(console, ctypes.byref(mode)):
		kernel32.SetConsoleMode(console, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING)

