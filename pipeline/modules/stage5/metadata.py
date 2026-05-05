"""Legacy import shim for per-paper metadata helpers."""

from ..paper_analysis import metadata as _metadata

globals().update({k: v for k, v in vars(_metadata).items() if not k.startswith("__")})
