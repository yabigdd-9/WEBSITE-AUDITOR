import pytest

from auditor_toolkit.identity import assess_business_identity, identity_confidence


def test_high_identity_requires_multiple_corroborating_signals():
    result = assess_business_identity(
        business_name="Koru Plumbing",
        legal_name="Koru Plumbing Limited",
        website="https://www.koruplumbing.co.nz/contact",
        nzbn_name="Koru Plumbing Limited",
        email="office@koruplumbing.co.nz",
        region_match=True,
        address_match=True,
        phone_match=True,
        website_brand_match=True,
    )
    assert result["canonical_domain"] == "koruplumbing.co.nz"
    assert result["signals"]["domain_name_match"] is True
    assert result["signals"]["nzbn_match"] is True
    assert result["signals"]["email_domain_match"] is True
    assert result["status"] == "HIGH"
    assert result["outreach_identity_eligible"] is True
    assert result["confidence"] == 1.0


def test_single_domain_string_match_is_not_enough():
    result = identity_confidence(
        {
            "domain_name_match": True,
            "website_brand_match": None,
            "nzbn_match": None,
            "email_domain_match": None,
            "region_match": None,
            "address_match": None,
            "phone_match": None,
        }
    )
    assert result["status"] == "LOW"
    assert result["outreach_identity_eligible"] is False


def test_material_identity_conflict_blocks_high_status():
    result = identity_confidence(
        {
            "domain_name_match": True,
            "website_brand_match": True,
            "nzbn_match": False,
            "email_domain_match": True,
            "region_match": True,
            "address_match": True,
            "phone_match": True,
        }
    )
    assert "nzbn_match" in result["conflicts"]
    assert result["status"] != "HIGH"
    assert result["outreach_identity_eligible"] is False


def test_email_domain_mismatch_is_explicit_conflict():
    result = assess_business_identity(
        business_name="Koru Plumbing",
        website="https://koruplumbing.co.nz",
        email="owner@different.example",
        website_brand_match=True,
        region_match=True,
    )
    assert result["signals"]["email_domain_match"] is False
    assert "email_domain_match" in result["conflicts"]


def test_unknown_identity_signal_fails_hard():
    with pytest.raises(ValueError, match="Unknown identity signals"):
        identity_confidence({"made_up_match": True})
