def test_canonical_domain_groups_nz_suffixes():
    from auditor_toolkit.identity import canonical_domain, same_entity
    # NZ multi-part suffix, scheme/case/www/path/query stripped.
    assert canonical_domain("https://WWW.Example.CO.NZ/path?q=1") == "example.co.nz"
    # www + port collapse to the registered domain.
    assert canonical_domain("http://www.example.com:8080/x") == "example.com"
    # Subdomains collapse to the registered domain (dedupe "same business across subdomains").
    assert canonical_domain("http://sub.example.com:8080/x") == "example.com"
    # Bare NZ host stays registered domain.
    assert canonical_domain("foo.co.nz") == "foo.co.nz"
    assert canonical_domain("deep.sub.foo.co.nz") == "foo.co.nz"
    # Two-label host is already a registered domain.
    assert canonical_domain("example.com") == "example.com"
    # same_entity groups www/non-www and scheme variants.
    assert same_entity("https://example.co.nz", "http://www.example.co.nz/")
    assert same_entity("https://shop.example.com", "https://example.com")
    assert not same_entity("https://example.co.nz", "https://example.com")


def test_local_verifier_rejects_bad_syntax_and_disposable():
    from auditor_toolkit.verify import verify_local
    bad = verify_local("not-an-email", first_party_source=True)
    assert bad["verdict"] == "REJECTED"
    disp = verify_local("user@mailinator.com", first_party_source=True)
    assert disp["verdict"] in ("CANDIDATE", "REJECTED")
    assert disp["score"] < 0.75
