from pathlib import Path
from typing import Self

import torch

class CPUOffloadManager:
	def set_device(self, device: torch.device) -> None: ...
	def initialize(self, stream: torch.cuda.Stream) -> None: ...
	def get_block(self, block_idx: int) -> torch.nn.Module: ...
	def step(self, compute_stream: torch.cuda.Stream) -> None: ...

class NunchakuQwenImageTransformerBlock(torch.nn.Module):
	img_mod: torch.nn.Module
	txt_mod: torch.nn.Module
	img_norm1: torch.nn.Module
	img_norm2: torch.nn.Module
	txt_norm1: torch.nn.Module
	txt_norm2: torch.nn.Module
	attn: torch.nn.Module
	img_mlp: torch.nn.Module
	txt_mlp: torch.nn.Module

class NunchakuQwenImageTransformer2DModel(torch.nn.Module):
	offload_manager: CPUOffloadManager
	img_in: torch.nn.Module
	txt_in: torch.nn.Module
	txt_norm: torch.nn.Module
	time_text_embed: torch.nn.Module
	pos_embed: torch.nn.Module
	transformer_blocks: torch.nn.ModuleList
	norm_out: torch.nn.Module
	proj_out: torch.nn.Module
	@classmethod
	def from_pretrained(cls, pretrained_model_name_or_path: str | Path) -> Self: ...
	def set_offload(self, offload: bool, *, use_pin_memory: bool, num_blocks_on_gpu: int) -> None: ...
