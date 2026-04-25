"""Stage 5 per-paper extraction pipeline.

This package owns the per-paper candidate discovery, Gemini extraction,
grounding, validation, evidence backfill, and metadata annotation flow.
"""

from .pipeline import Stage5Pipeline

__all__ = ["Stage5Pipeline"]
