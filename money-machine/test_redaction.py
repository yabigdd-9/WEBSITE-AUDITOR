import mm_redaction
from mm_model_router import prepare_external_prompt


def test_prompt_redacts_sensitive_material_and_preserves_safety():
    result = prepare_external_prompt("Contact jane@example.co.nz at +64 21 555 123. api_key=SECRET1234567890")
    assert "jane@example.co.nz" not in result["prompt"]
    assert "SECRET1234567890" not in result["prompt"]
    assert result["secret_detected"] is True
    assert result["human_review_required"] is True
    assert result["paid_calls"] == 0
    assert result["model_cost_usd"] == 0.0


def test_prompt_size_is_bounded():
    try:
        mm_redaction.prepare_prompt("x" * 100, max_chars=10)
    except ValueError as exc:
        assert "size limit" in str(exc)
    else:
        raise AssertionError("oversized prompt should be rejected")
