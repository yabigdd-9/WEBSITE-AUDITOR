import pytest

from auditor_toolkit.opportunity import FORMULA_VERSION, opportunity_formula


def test_commercial_opportunity_formula_is_deterministic_and_separate():
    result = opportunity_formula(
        need=0.8,
        business_value=0.5,
        contactability=0.9,
        fixability=0.75,
        confidence=0.95,
        effort=0.25,
    )

    assert result["formula_version"] == FORMULA_VERSION == "opportunity-v1"
    assert result["opportunity_score"] == 20.5
    assert result["components"] == {
        "need": 0.8,
        "business_value": 0.5,
        "contactability": 0.9,
        "fixability": 0.75,
        "confidence": 0.95,
        "effort": 0.25,
    }
    assert result["inputs_used"] == result["components"]
    assert "technical_score" not in result


@pytest.mark.parametrize(
    "value",
    [None, True, False, float("nan"), float("inf"), -0.01, 1.01, "unknown"],
)
def test_commercial_opportunity_rejects_invalid_components(value):
    with pytest.raises(ValueError):
        opportunity_formula(value, 1, 1, 1, 1, 0)


def test_unverified_contactability_cannot_create_commercial_opportunity():
    result = opportunity_formula(1, 1, 0, 1, 1, 0)

    assert result["opportunity_score"] == 0
