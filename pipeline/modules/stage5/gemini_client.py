"""Legacy import shim for per-paper Gemini client helpers."""

from ..paper_analysis import gemini_client as _gemini_client

globals().update({k: v for k, v in vars(_gemini_client).items() if not k.startswith("__")})
