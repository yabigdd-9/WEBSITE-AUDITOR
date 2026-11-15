"""Regression tests for cloud-safe uncompressed HTTP fetches."""
import unittest

import httpx

from auditor_toolkit.common import Fetcher


class CloudFetchEncodingTests(unittest.TestCase):
    def test_identity_encoding_prevents_malformed_compression(self):
        headers_seen = []

        def handler(request):
            headers_seen.append(request.headers.get("accept-encoding"))
            if request.headers.get("accept-encoding") != "identity":
                return httpx.Response(
                    200,
                    headers={"content-encoding": "gzip"},
                    content=b"not gzip",
                )
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                content=b"<html><title>Test</title></html>",
            )

        fetcher = Fetcher(
            allow_private=True,
            transport=httpx.MockTransport(handler),
            min_interval=0,
        )
        try:
            response = fetcher.get("https://example.com/")
        finally:
            fetcher.close()
        self.assertEqual(headers_seen, ["identity"])
        self.assertEqual(response.status_code, 200)
        self.assertIn("<title>Test</title>", response.text)

    def test_identity_is_preserved_on_redirects(self):
        seen = []

        def handler(request):
            seen.append(request.headers.get("accept-encoding"))
            if request.url.host == "example.com":
                return httpx.Response(
                    302,
                    headers={"location": "https://www.example.com/"},
                )
            return httpx.Response(200, content=b"ready")

        fetcher = Fetcher(
            allow_private=True,
            transport=httpx.MockTransport(handler),
            min_interval=0,
        )
        try:
            result = fetcher.get("https://example.com/")
        finally:
            fetcher.close()
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.text, "ready")
        self.assertEqual(seen, ["identity", "identity"])


if __name__ == "__main__":
    unittest.main()
