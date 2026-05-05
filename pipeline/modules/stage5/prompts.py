"""Legacy import shim for per-paper prompt constants."""

from ..paper_analysis import prompts as _prompts

globals().update({k: v for k, v in vars(_prompts).items() if not k.startswith("__")})
