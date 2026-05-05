"""Legacy import shim for per-paper context helpers."""

from ..paper_analysis import context as _context

globals().update({k: v for k, v in vars(_context).items() if not k.startswith("__")})
