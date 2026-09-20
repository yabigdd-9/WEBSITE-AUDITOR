from bs4 import BeautifulSoup

import auditor_core.passive as passive


def test_accessibility_basics_detects_lang_labels_and_button_names():
    soup = BeautifulSoup(
        '<html><body><form><input id="email"></form><button><span></span></button></body></html>',
        "html.parser",
    )
    defects, evidence = passive.accessibility_basics(soup)
    messages = [item["defect"] for item in defects]
    assert "Missing HTML lang attribute" in messages
    assert "1 form control(s) missing accessible labels" in messages
    assert "1 button(s) missing accessible names" in messages
    assert evidence["unlabeled_form_controls"] == 1


def test_accessibility_basics_accepts_labelled_controls():
    soup = BeautifulSoup(
        '<html lang="en"><body><label for="email">Email</label><input id="email"><button>Send</button></body></html>',
        "html.parser",
    )
    defects, evidence = passive.accessibility_basics(soup)
    assert defects == []
    assert evidence["html_lang"] == "en"


def test_cookie_security_only_flags_observed_cookie_attributes():
    defects, evidence = passive.cookie_security(
        {"Set-Cookie": "session=abc; HttpOnly; Path=/"},
        is_https=True,
    )
    messages = [item["defect"] for item in defects]
    assert "Observed cookie without Secure attribute" in messages
    assert "Observed cookie without SameSite attribute" in messages
    assert evidence["httponly_attribute_observed"] is True


def test_nz_business_signals_find_phone_and_address():
    signals = passive.nz_business_signals(
        "Call +64 3 555 1234 at 12 High Street, Christchurch 8011",
        '<a href="https://example.co.nz">NZ</a>',
    )
    assert signals["nz_phone_count"] >= 1
    assert signals["postal_address_signal"] is True
    assert signals["nz_domain"] is True


def test_email_dns_findings_are_conservative(monkeypatch):
    records = {
        "example.co.nz": [],
        "_dmarc.example.co.nz": [],
        "google._domainkey.example.co.nz": [],
        "default._domainkey.example.co.nz": [],
        "selector1._domainkey.example.co.nz": [],
        "selector2._domainkey.example.co.nz": [],
    }
    monkeypatch.setattr(passive, "_txt_records", lambda name, timeout=4.0: records.get(name, []))
    defects, evidence = passive.email_dns_security("example.co.nz", email_signal=True)
    assert {item["defect"] for item in defects} == {
        "No SPF record detected",
        "No DMARC record detected",
    }
    assert evidence["spf_present"] is False
    assert evidence["dmarc_present"] is False


def test_email_dns_does_not_claim_missing_records_without_email_signal(monkeypatch):
    monkeypatch.setattr(passive, "_txt_records", lambda name, timeout=4.0: [])
    defects, evidence = passive.email_dns_security("example.co.nz", email_signal=False)
    assert defects == []
    assert evidence["email_signal"] is False
    assert evidence["dkim_common_selector_hits"] == {}
