"""Integration tests for proof prototype evaluation via v36 adapter."""


from auditor_toolkit.proof.adapters.ai_generator import (
    configure,
    generate_ai_prototype,
    is_available,
    validate_with_evaluator,
)
from auditor_toolkit.proof.adapters.v36_evaluator import (
    evaluate_prototype,
    get_evaluation_verdict,
)
from auditor_toolkit.proof.prototype import PrototypeManifest

# ---------------------------------------------------------------------------
# v36 evaluator
# ---------------------------------------------------------------------------

def test_evaluate_prototype_basic_pass():
    manifest = PrototypeManifest(
        patch_id="p1",
        finding_id="f001",
        patch_type="CSS_PATCH",
        target=".subtitle",
        before_value="color: #999",
        after_value="color: #1a1a2e",
        generated_by="deterministic",
    )
    finding = {"finding_id": "f001", "selector": ".subtitle"}

    result = evaluate_prototype(manifest, finding)
    assert "pass" in result
    assert "score" in result
    assert "grader" in result
    # Basic evaluator should pass when all fields are present and match
    assert result["pass"] is True


def test_evaluate_prototype_no_target():
    manifest = PrototypeManifest(
        patch_id="p2",
        finding_id="f002",
        patch_type="CSS_PATCH",
        target="",  # empty target
        before_value="x",
        after_value="y",
    )
    finding = {"finding_id": "f002", "selector": ".test"}

    result = evaluate_prototype(manifest, finding)
    assert result["pass"] is False


def test_evaluate_prototype_no_after_value():
    manifest = PrototypeManifest(
        patch_id="p3",
        finding_id="f003",
        patch_type="CSS_PATCH",
        target=".test",
        before_value="x",
        after_value="",  # empty
    )
    finding = {"finding_id": "f003", "selector": ".test"}

    result = evaluate_prototype(manifest, finding)
    assert result["pass"] is False


def test_evaluate_prototype_target_mismatch():
    manifest = PrototypeManifest(
        patch_id="p4",
        finding_id="f004",
        patch_type="CSS_PATCH",
        target=".wrong",
        before_value="x",
        after_value="y",
    )
    finding = {"finding_id": "f004", "selector": ".expected"}

    result = evaluate_prototype(manifest, finding)
    assert result["pass"] is False


def test_get_evaluation_verdict_pass():
    assert get_evaluation_verdict({"pass": True, "score": 0.95}) == "PASS"


def test_get_evaluation_verdict_inconclusive():
    assert get_evaluation_verdict({"pass": True, "score": 0.5}) == "INCONCLUSIVE"


def test_get_evaluation_verdict_fail():
    assert get_evaluation_verdict({"pass": False, "score": 0.0}) == "FAIL"


# ---------------------------------------------------------------------------
# AI generator
# ---------------------------------------------------------------------------

def test_ai_generator_disabled_by_default():
    assert is_available() is False


def test_ai_generator_not_available_without_api_key():
    configure(enabled=True)
    assert is_available() is False
    configure(enabled=False)  # reset


def test_ai_generator_enabled_with_key():
    configure(enabled=True, api_key="test-key")
    assert is_available() is True
    configure(enabled=False, api_key="")  # reset


def test_generate_ai_prototype_disabled():
    finding = {
        "finding_id": "f001",
        "selector": ".test",
        "confidence": 0.95,
        "claim": "Test finding",
    }
    result = generate_ai_prototype(finding)
    assert result is None  # disabled by default


def test_generate_ai_prototype_low_confidence():
    configure(enabled=True, api_key="test-key", min_confidence=0.90)
    finding = {
        "finding_id": "f002",
        "selector": ".test",
        "confidence": 0.50,  # below threshold
        "claim": "Low confidence finding",
    }
    result = generate_ai_prototype(finding)
    assert result is None
    configure(enabled=False, api_key="")


def test_generate_ai_prototype_high_confidence():
    configure(enabled=True, api_key="test-key", min_confidence=0.90)
    finding = {
        "finding_id": "f003",
        "selector": ".test",
        "confidence": 0.95,
        "claim": "High confidence finding",
    }
    result = generate_ai_prototype(finding)
    assert result is not None
    assert result.generated_by == "ai"
    assert result.finding_id == "f003"
    configure(enabled=False, api_key="")


def test_validate_with_evaluator():
    manifest = PrototypeManifest(
        patch_id="p5",
        finding_id="f005",
        patch_type="CSS_PATCH",
        target=".test",
        before_value="x",
        after_value="y",
        generated_by="deterministic",
    )
    finding = {"finding_id": "f005", "selector": ".test"}

    result = validate_with_evaluator(manifest, finding)
    assert "valid" in result
    assert "evaluator" in result


# ---------------------------------------------------------------------------
# End-to-end: finding → patch → evaluate
# ---------------------------------------------------------------------------

def test_finding_to_patch_to_evaluate():
    """Full pipeline: create a patch from a finding and evaluate it."""
    finding = {
        "finding_id": "f010",
        "selector": ".subtitle",
        "confidence": 0.95,
        "claim": "Poor text contrast",
    }

    # 1. Create deterministic patch (patches.py version takes css, finding)
    from auditor_toolkit.proof.patches import patch_poor_contrast as patches_poor_contrast
    patched, manifest = patches_poor_contrast(
        ".subtitle { color: #999; }", finding
    )

    # 2. Evaluate the prototype
    result = evaluate_prototype(manifest, finding)
    assert result["pass"] is True

    # 3. Get verdict
    verdict = get_evaluation_verdict(result)
    assert verdict == "PASS"


def test_finding_to_patch_to_evaluate_mismatch():
    """Evaluation should fail when patch target doesn't match finding."""
    finding = {
        "finding_id": "f011",
        "selector": ".expected",
    }
    manifest = PrototypeManifest(
        patch_id="p6",
        finding_id="f011",
        patch_type="CSS_PATCH",
        target=".wrong-target",
        before_value="x",
        after_value="y",
    )

    result = evaluate_prototype(manifest, finding)
    assert result["pass"] is False
    assert get_evaluation_verdict(result) == "FAIL"
