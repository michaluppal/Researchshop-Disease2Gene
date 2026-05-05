"""
Import contract tests for the per-paper extraction package.

The public compatibility path remains ``modules.gemini_extractor.GeneInfoPipeline``
while new code imports ``modules.paper_analysis.pipeline.PaperAnalysisPipeline`` directly.
"""

import sys
from pathlib import Path


_PYTHON_ROOT = Path(__file__).parent.parent
if str(_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(_PYTHON_ROOT))


def test_paper_analysis_pipeline_imports_from_package():
    from modules.paper_analysis.pipeline import PaperAnalysisPipeline

    assert PaperAnalysisPipeline.__name__ == "PaperAnalysisPipeline"


def test_gemini_extractor_compatibility_alias():
    from modules.gemini_extractor import GeneInfoPipeline
    from modules.paper_analysis.pipeline import PaperAnalysisPipeline, Stage5Pipeline

    assert GeneInfoPipeline is PaperAnalysisPipeline
    assert Stage5Pipeline is PaperAnalysisPipeline


def test_legacy_stage5_import_still_aliases_new_pipeline():
    from modules.paper_analysis.pipeline import PaperAnalysisPipeline
    from modules.stage5.pipeline import Stage5Pipeline

    assert Stage5Pipeline is PaperAnalysisPipeline


def test_gemini_extractor_shim_exposes_config_for_existing_patches():
    from modules import gemini_extractor

    assert hasattr(gemini_extractor, "config")
    assert hasattr(gemini_extractor.config, "GEMINI_API_KEY")
