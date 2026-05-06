"""
Import contract tests for the per-paper extraction package.

Public code imports ``modules.paper_analysis.pipeline.PaperAnalysisPipeline`` directly.
"""

import sys
from pathlib import Path


_PYTHON_ROOT = Path(__file__).parent.parent
if str(_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(_PYTHON_ROOT))


def test_paper_analysis_pipeline_imports_from_package():
    from modules.paper_analysis.pipeline import PaperAnalysisPipeline

    assert PaperAnalysisPipeline.__name__ == "PaperAnalysisPipeline"


def test_paper_analysis_pipeline_imports_from_package_root():
    from modules.paper_analysis import PaperAnalysisPipeline
    from modules.paper_analysis.pipeline import PaperAnalysisPipeline as PipelineImplementation

    assert PaperAnalysisPipeline is PipelineImplementation
