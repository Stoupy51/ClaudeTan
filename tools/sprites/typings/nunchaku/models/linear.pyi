import torch

class SVDQW4A4Linear(torch.nn.Module):
	in_features: int
	out_features: int
	rank: int
	proj_down: torch.nn.Parameter
	proj_up: torch.nn.Parameter
