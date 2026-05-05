"""Legacy import shim for the per-paper extraction coordinator."""

from ..paper_analysis.pipeline import PaperAnalysisPipeline, Stage5Pipeline

__all__ = ["PaperAnalysisPipeline", "Stage5Pipeline"]
