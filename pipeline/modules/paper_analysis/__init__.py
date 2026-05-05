"""Per-paper extraction pipeline package.

This package owns the per-paper candidate discovery, Gemini extraction,
grounding, validation, evidence backfill, and metadata annotation flow.
"""

from .pipeline import PaperAnalysisPipeline, Stage5Pipeline

__all__ = ["PaperAnalysisPipeline", "Stage5Pipeline"]
