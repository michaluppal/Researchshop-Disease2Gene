"""Backward-compatible Stage 5 import shim.

Historically the per-paper Stage 5 coordinator lived in this module as
``GeneInfoPipeline``. New code should import ``Stage5Pipeline`` from
``modules.stage5.pipeline``; this shim keeps old imports and test patches working.
"""

from . import config
from .stage5.pipeline import Stage5Pipeline

GeneInfoPipeline = Stage5Pipeline

__all__ = ["GeneInfoPipeline", "Stage5Pipeline", "config"]
