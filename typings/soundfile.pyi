from io import BytesIO
from os import PathLike

import numpy as np

def read(file: str | PathLike[str] | BytesIO, dtype: str = "float64") -> tuple[np.ndarray[tuple[int], np.dtype[np.float32]], int]: ...
