"""Legacy import shim for per-paper candidate helpers."""

from ..paper_analysis import candidates as _candidates

globals().update({k: v for k, v in vars(_candidates).items() if not k.startswith("__")})
