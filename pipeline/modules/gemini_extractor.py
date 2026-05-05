"""Backward-compatible Gemini extractor import shim.

Historically the per-paper extraction coordinator lived in this module as
``GeneInfoPipeline``. New code should import ``PaperAnalysisPipeline`` from
``modules.paper_analysis.pipeline``; this shim keeps old imports and test patches working.
"""

from . import config
from .paper_analysis.pipeline import PaperAnalysisPipeline, Stage5Pipeline

GeneInfoPipeline = PaperAnalysisPipeline

__all__ = ["GeneInfoPipeline", "PaperAnalysisPipeline", "Stage5Pipeline", "config"]
