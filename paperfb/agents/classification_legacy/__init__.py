"""Classification agent — public API.

Downstream code (orchestrator, tests) should import only from here.
"""
from paperfb.agents.classification_legacy.agent import classify_manuscript
from paperfb.contracts import ClassificationResult

__all__ = ["classify_manuscript", "ClassificationResult"]
