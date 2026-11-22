import base64
import stat

import pytest

from auditor_toolkit.tls_renewal import ACMEAccount, ACMEClient


def test_certificate_request_uses_private_key_and_der_csr(tmp_path, monkeypatch):
    x509 = pytest.importorskip("cryptography.x509")
    monkeypatch.chdir(tmp_path)
    client = ACMEClient("admin@example.test", tmp_path / "account.key")
    client.account = ACMEAccount(client.email, client.account_key_path)
    new_order = "https://ca.example.test/new-order"
    certificate = "https://ca.example.test/cert"
    monkeypatch.setattr(client, "_get_directory", lambda: {"newOrder": new_order})
    monkeypatch.setattr(client, "_get_finalize_url", lambda _: certificate)
    sent_csrs = []

    def post(url, payload):
        if url == new_order:
            assert payload["identifiers"] == [
                {"type": "dns", "value": "example.test"},
                {"type": "dns", "value": "www.example.test"},
            ]
            return {"location": "https://ca.example.test/order"}, "nonce"
        if url == new_order + "/finalize":
            encoded = payload["csr"]
            der = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
            sent_csrs.append(x509.load_der_x509_csr(der))
            return {}, "nonce"
        assert url == certificate
        return {"certificate": "fixture certificate"}, "nonce"

    monkeypatch.setattr(client, "_post", post)
    key = tmp_path / "site.key"
    result = client.request_certificate(["example.test", "www.example.test"], key)
    original_key = key.read_bytes()
    assert result.status == "valid"
    assert result.certificate_path.read_text() == "fixture certificate"
    assert stat.S_IMODE(key.stat().st_mode) == 0o600
    client.request_certificate(["example.test", "www.example.test"], key)
    assert key.read_bytes() == original_key
    assert len(sent_csrs) == 2
    for csr in sent_csrs:
        assert csr.is_signature_valid
        san = csr.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        assert san.value.get_values_for_type(x509.DNSName) == ["example.test", "www.example.test"]


def test_certificate_request_requires_dns_names(tmp_path):
    client = ACMEClient("admin@example.test", tmp_path / "account.key")
    with pytest.raises(ValueError, match="valid DNS names"):
        client.request_certificate([], tmp_path / "site.key")
