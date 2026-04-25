"""
Import contract tests for the Stage 5 package split.

The public compatibility path remains ``modules.gemini_extractor.GeneInfoPipeline``
while new code imports ``modules.stage5.pipeline.Stage5Pipeline`` directly.
"""

import sys
from pathlib import Path


_PYTHON_ROOT = Path(__file__).parent.parent
if str(_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(_PYTHON_ROOT))


def test_stage5_pipeline_imports_from_new_package():
    from modules.stage5.pipeline import Stage5Pipeline

    assert Stage5Pipeline.__name__ == "Stage5Pipeline"


def test_gemini_extractor_compatibility_alias():
    from modules.gemini_extractor import GeneInfoPipeline
    from modules.stage5.pipeline import Stage5Pipeline

    assert GeneInfoPipeline is Stage5Pipeline


def test_gemini_extractor_shim_exposes_config_for_existing_patches():
    from modules import gemini_extractor

    assert hasattr(gemini_extractor, "config")
    assert hasattr(gemini_extractor.config, "GEMINI_API_KEY")
