from pathlib import Path
from typing import Literal, Self

import numpy as np
import torch
from numpy.typing import NDArray
from PIL import Image

VAE_IMAGE_SIZE: int

class QwenImagePipelineOutput:
	images: NDArray[np.float32]

class QwenImageEditPlusPipeline:
	@classmethod
	def from_pretrained(cls, pretrained_model_name_or_path: str, *, transformer: torch.nn.Module, dtype: torch.dtype, cache_dir: Path) -> Self: ...
	def enable_model_cpu_offload(self) -> None: ...
	def __call__(
		self, *, image: list[Image.Image], prompt: str, num_inference_steps: int, true_cfg_scale: float,
		width: int, height: int, generator: torch.Generator, output_type: Literal["np"],
	) -> QwenImagePipelineOutput: ...
