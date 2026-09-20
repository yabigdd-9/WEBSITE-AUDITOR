from auditor_core.ecommerce import ecommerce_checks


def test_non_ecommerce_page_is_not_flagged():
    defects, evidence = ecommerce_checks("<html><h1>Consulting</h1></html>", base_url="https://example.co.nz/")
    assert defects == []
    assert evidence["ecommerce_detected"] is False


def test_ecommerce_page_flags_missing_schema_policy_and_gst():
    html = '<html><body><button>Add to cart</button><a href="/checkout">Checkout</a></body></html>'
    defects, evidence = ecommerce_checks(html, base_url="https://shop.example.co.nz/")
    messages = {item["defect"] for item in defects}
    assert "Ecommerce product schema not detected" in messages
    assert "Shipping or returns information not clearly detected" in messages
    assert "GST pricing clarity not detected" in messages
    assert evidence["ecommerce_detected"] is True


def test_insecure_checkout_is_high_confidence_signal():
    html = '<html><body><a href="http://shop.example.co.nz/checkout">Checkout</a> Shipping Returns GST</body></html>'
    defects, evidence = ecommerce_checks(html, base_url="https://shop.example.co.nz/")
    assert any("insecure checkout/payment" in item["defect"] for item in defects)
    assert evidence["insecure_checkout_urls"] == ["http://shop.example.co.nz/checkout"]


def test_product_schema_and_policy_signals_are_recorded():
    html = """
    <html><body>
    <script type="application/ld+json">
    {"@context":"https://schema.org","@type":"Product","name":"Widget"}
    </script>
    Add to cart. Shipping and Returns. Prices include GST. Secure checkout.
    <div class="reviews">Reviews</div>
    </body></html>
    """
    defects, evidence = ecommerce_checks(html, base_url="https://shop.example.co.nz/")
    assert not any(item["defect"] == "Ecommerce product schema not detected" for item in defects)
    assert evidence["product_schema_present"] is True
    assert evidence["gst_signal"] is True
    assert evidence["review_signal_count"] == 1
