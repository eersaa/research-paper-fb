import json

from paperfb.handoffs import classify_to_profile
from paperfb.schemas import CCSClass, ClassificationResult, Keywords


def _ctx():
    """Stub ContextVariables — a plain dict; AG2's ContextVariables is dict-like.
    The handoff function must accept dict-style read/write so we can unit-test it
    without instantiating the AG2 class.
    """
    return {}


def test_classify_to_profile_writes_full_classification_to_context():
    cr = ClassificationResult(
        keywords=Keywords(extracted_from_paper=["x"], synthesised=[]),
        classes=[CCSClass(path="A → B", weight="High", rationale="r")],
    )
    ctx = _ctx()
    result = classify_to_profile(cr.model_dump_json(), ctx)
    saved = ClassificationResult.model_validate(ctx["classification"])
    assert saved == cr
    # Curated message goes downstream
    assert "A → B" in result.message
    # Keywords MUST NOT leak into the downstream prompt (spec §4.1)
    assert "x" not in result.message


def test_classify_to_profile_message_lists_only_class_paths():
    cr = ClassificationResult(
        keywords=Keywords(extracted_from_paper=[], synthesised=["k1"]),
        classes=[
            CCSClass(path="A → B", weight="High", rationale="r1"),
            CCSClass(path="C → D", weight="Low", rationale="r2"),
        ],
    )
    result = classify_to_profile(cr.model_dump_json(), _ctx())
    assert "A → B" in result.message
    assert "C → D" in result.message
    # Rationales stay in context_variables, not in the downstream message
    assert "r1" not in result.message
