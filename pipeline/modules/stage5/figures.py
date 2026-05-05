"""Legacy import shim for per-paper figure helpers."""

from ..paper_analysis import figures as _figures

globals().update({k: v for k, v in vars(_figures).items() if not k.startswith("__")})
