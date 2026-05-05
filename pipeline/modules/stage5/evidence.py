"""Legacy import shim for per-paper evidence helpers."""

from ..paper_analysis import evidence as _evidence

globals().update({k: v for k, v in vars(_evidence).items() if not k.startswith("__")})
