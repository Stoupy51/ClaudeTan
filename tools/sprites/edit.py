""" Sprites redrawn by Qwen-Image-Edit-2511 with its 4-step Lightning LoRA merged, run by Nunchaku in int4: about 30 s each on 12 GB.

Nunchaku 1.3 predates both 2511 and diffusers 0.41. The patches below load a checkpoint recompressed with a SVD rank per layer,
and give the transformer the 2511 forward, where the tokens of the reference image are modulated at timestep 0 (`zero_cond_t`).
"""
# Imports
import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from math import prod
from typing import Any

import cv2
import numpy as np
import torch
from cv2.typing import MatLike
from diffusers.models.transformers.transformer_qwenimage import compute_text_seq_len_from_mask
from diffusers.pipelines.qwenimage import pipeline_qwenimage_edit_plus
from nunchaku import NunchakuQwenImageTransformer2DModel
from nunchaku.models.linear import SVDQW4A4Linear
from nunchaku.models.transformers.transformer_qwenimage import NunchakuQwenImageTransformerBlock
from PIL import Image

from canvas import LEFT, RIGHT, WIDTH as CANVAS_WIDTH, upscale4
from eyes import Eyes
from sources import WORK, fetch

# Constants
WIDTH, HEIGHT = 864, 608
""" The canvas padded to the multiple of 16 the editor works in. """
PAD: int = (WIDTH - CANVAS_WIDTH) // 2
BACKGROUND: float = 232 / 255
""" The plain light gray she is drawn on, which the matte removes afterwards. """
CANVAS_EYES: Eyes = Eyes(left=(4 * (LEFT[0] + PAD), 4 * LEFT[1]), right=(4 * (RIGHT[0] + PAD), 4 * RIGHT[1]))
""" Where the canvas eyes land in an edited frame, for edits that leave her head in place. """
TRANSFORMER_URL: str = (
	"https://huggingface.co/wazimondo/Qwen_image_edit_2511_int4/resolve/main/"
	"nunchaku_qwen_image_edit_2511_quality_r64_lightning4steps_q128o64m64_int4.safetensors"
)
PIPELINE_REPO: str = "ovedrive/Qwen-Image-Edit-2511-4bit"
""" Text encoder, quantized to 4 bits by bitsandbytes, and VAE. """
BLOCKS_ON_GPU: int = 20
""" Transformer blocks kept on the GPU out of 60, the others streamed from RAM: 10.3 GiB at peak. """


# Classes
@dataclass(frozen=True)
class Drawing:
	""" A sprite the image editor draws from the first pose. """
	name: str
	prompt: str


# Functions
def edit(name: str, sprite: MatLike, prompt: str) -> MatLike:
	""" RGB uint8 frame of the sprite redrawn by the prompt, enlarged 4 times like a video frame, cached in `.work/edits/`.

	Args:
		sprite: RGBA canvas, values in [0, 1].
	"""
	on_gray = sprite[..., :3] * sprite[..., 3:] + BACKGROUND * (1 - sprite[..., 3:])
	padded = np.pad(on_gray, ((0, 0), (PAD, WIDTH - CANVAS_WIDTH - PAD), (0, 0)), constant_values=BACKGROUND)
	reference = (padded * 255).round().astype(np.uint8)
	path = WORK / "edits" / f"{name}_{hashlib.sha1(reference.tobytes() + prompt.encode()).hexdigest()[:8]}.png"
	if not path.exists():
		drawn: MatLike = pipeline()(
			image=[Image.fromarray(reference)], prompt=prompt, num_inference_steps=4, true_cfg_scale=1.0,
			width=WIDTH, height=HEIGHT, generator=torch.Generator().manual_seed(0), output_type="np",
		).images[0]
		path.parent.mkdir(parents=True, exist_ok=True)
		cv2.imwrite(str(path), cv2.cvtColor((drawn * 255).round().astype(np.uint8), cv2.COLOR_RGB2BGR))
	image = cv2.imread(str(path))
	assert image is not None
	enlarged = upscale4(cv2.cvtColor(image, cv2.COLOR_BGR2RGB).astype(np.float32) / 255)
	return (enlarged * 255).round().astype(np.uint8)


@cache
def pipeline() -> pipeline_qwenimage_edit_plus.QwenImageEditPlusPipeline:
	# The reference image would otherwise be resized to 1 MP, twice the tokens of the canvas
	pipeline_qwenimage_edit_plus.VAE_IMAGE_SIZE = WIDTH * HEIGHT
	transformer = NunchakuQwenImageTransformer2DModel.from_pretrained(fetch(TRANSFORMER_URL))
	transformer.set_offload(True, use_pin_memory=False, num_blocks_on_gpu=BLOCKS_ON_GPU)
	editor = pipeline_qwenimage_edit_plus.QwenImageEditPlusPipeline.from_pretrained(
		PIPELINE_REPO, transformer=transformer, dtype=torch.bfloat16, cache_dir=WORK / "hf",
	)
	editor.enable_model_cpu_offload()
	return editor


def load_mixed_ranks(
	self: NunchakuQwenImageTransformer2DModel, state_dict: Mapping[str, Any], strict: bool = True, assign: bool = False,
) -> Any:
	""" `load_state_dict` resizing each low-rank branch to the checkpoint's, where Nunchaku builds them all with one rank. """
	for key, down in state_dict.items():
		if key.endswith(".proj_down"):
			module = self.get_submodule(key.removesuffix(".proj_down"))
			assert isinstance(module, SVDQW4A4Linear)
			module.rank = down.shape[1]
			module.proj_down = torch.nn.Parameter(module.proj_down.new_empty(module.in_features, module.rank))
			module.proj_up = torch.nn.Parameter(module.proj_up.new_empty(module.out_features, module.rank))
	return torch.nn.Module.load_state_dict(self, state_dict, strict, assign)


def transformer_forward(
	self: NunchakuQwenImageTransformer2DModel, hidden_states: torch.Tensor, encoder_hidden_states: torch.Tensor,
	encoder_hidden_states_mask: torch.Tensor | None, timestep: torch.Tensor, img_shapes: list[list[tuple[int, int, int]]],
	**ignored: object,
) -> tuple[torch.Tensor]:
	""" diffusers 0.41 `QwenImageTransformer2DModel.forward` with `zero_cond_t`, on Nunchaku's streamed blocks. """
	device = hidden_states.device
	timestep = timestep.to(hidden_states.dtype)
	# First the target tokens, at the real timestep, then the tokens of the reference images, at timestep 0
	reference = torch.tensor([[0] * prod(shapes[0]) + [1] * sum(map(prod, shapes[1:])) for shapes in img_shapes], device=device)
	hidden_states = self.img_in(hidden_states)
	encoder_hidden_states = self.txt_in(self.txt_norm(encoder_hidden_states))
	text_length, _, text_mask = compute_text_seq_len_from_mask(encoder_hidden_states, encoder_hidden_states_mask)
	temb = self.time_text_embed(torch.cat([timestep, timestep * 0]), hidden_states)
	rotary = self.pos_embed(img_shapes, max_txt_seq_len=text_length, device=device)

	stream = torch.cuda.current_stream()
	self.offload_manager.set_device(device)
	self.offload_manager.initialize(stream)
	for index in range(len(self.transformer_blocks)):
		with torch.cuda.stream(stream):
			block = self.offload_manager.get_block(index)
			encoder_hidden_states, hidden_states = block(hidden_states, encoder_hidden_states, text_mask, temb, rotary, reference)
		self.offload_manager.step(stream)

	output = self.proj_out(self.norm_out(hidden_states, temb.chunk(2)[0]))
	torch.cuda.empty_cache()
	return (output,)


def block_forward(
	self: NunchakuQwenImageTransformerBlock, hidden_states: torch.Tensor, encoder_hidden_states: torch.Tensor,
	text_mask: torch.Tensor | None, temb: torch.Tensor, rotary: tuple[torch.Tensor, torch.Tensor], reference: torch.Tensor,
) -> tuple[torch.Tensor, torch.Tensor]:
	""" One double-stream block: the text stream is modulated at the real timestep only, the image stream per token. """
	img_mod1, img_mod2 = per_parameter(self.img_mod(temb)).chunk(2, dim=-1)
	txt_mod1, txt_mod2 = per_parameter(self.txt_mod(temb.chunk(2)[0])).chunk(2, dim=-1)

	img_modulated, img_gate1 = modulate(self.img_norm1(hidden_states), img_mod1, reference)
	txt_modulated, txt_gate1 = modulate(self.txt_norm1(encoder_hidden_states), txt_mod1)
	img_attention, txt_attention = self.attn(
		hidden_states=img_modulated, encoder_hidden_states=txt_modulated, encoder_hidden_states_mask=text_mask,
		image_rotary_emb=rotary,
	)
	hidden_states = hidden_states + img_gate1 * img_attention
	encoder_hidden_states = encoder_hidden_states + txt_gate1 * txt_attention

	img_modulated, img_gate2 = modulate(self.img_norm2(hidden_states), img_mod2, reference)
	txt_modulated, txt_gate2 = modulate(self.txt_norm2(encoder_hidden_states), txt_mod2)
	return encoder_hidden_states + txt_gate2 * self.txt_mlp(txt_modulated), hidden_states + img_gate2 * self.img_mlp(img_modulated)


def per_parameter(mod_params: torch.Tensor) -> torch.Tensor:
	""" Nunchaku's [B, dim * 6] modulation, interleaved by channel, reordered to diffusers' 6 consecutive parameters. """
	return mod_params.view(mod_params.shape[0], -1, 6).transpose(1, 2).reshape(mod_params.shape[0], -1)


def modulate(x: torch.Tensor, mod_params: torch.Tensor, reference: torch.Tensor | None = None) -> tuple[torch.Tensor, torch.Tensor]:
	""" Shifted and scaled tokens and their gate; Nunchaku folds the 1 of `1 + scale` into its weights.

	Args:
		reference: 1 for the tokens taking the second half of the batch of parameters, the one at timestep 0.
	"""
	shift, scale, gate = (p.unsqueeze(1) for p in mod_params.chunk(3, dim=-1))
	if reference is not None:
		half, second = shift.shape[0] // 2, reference.unsqueeze(-1) == 1
		shift, scale, gate = (torch.where(second, p[half:], p[:half]) for p in (shift, scale, gate))
	return x * scale + shift, gate


NunchakuQwenImageTransformer2DModel.load_state_dict = load_mixed_ranks
NunchakuQwenImageTransformer2DModel.forward = transformer_forward
NunchakuQwenImageTransformerBlock.forward = block_forward

