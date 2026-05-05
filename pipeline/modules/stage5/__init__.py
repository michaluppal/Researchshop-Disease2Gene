"""Legacy import package for per-paper extraction.

New code should import from ``modules.paper_analysis``. This package remains so
older imports that reference the former ``modules.stage5`` path keep working.
"""

from ..paper_analysis import PaperAnalysisPipeline, Stage5Pipeline

__all__ = ["PaperAnalysisPipeline", "Stage5Pipeline"]
