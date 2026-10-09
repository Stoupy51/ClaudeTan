import torch

class PreTrainedConfig: ...

class AutoConfig:
	@classmethod
	def from_pretrained(cls, pretrained_model_name_or_path: str, *, trust_remote_code: bool) -> PreTrainedConfig: ...

class AutoModelForImageSegmentation:
	@classmethod
	def from_config(cls, config: PreTrainedConfig, *, trust_remote_code: bool) -> torch.nn.Module: ...
