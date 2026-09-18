"""Tests for mm_exa. All tests mock the Exa client — no real API calls."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "money-machine"))
import mm_exa


class TestApiKeyResolution(unittest.TestCase):
    def test_key_from_env(self):
        with patch.dict("os.environ", {"EXA_API_KEY": "test-key"}):
            self.assertEqual(mm_exa.get_api_key(), "test-key")

    def test_key_missing_raises_on_init(self):
        with patch.dict("os.environ", {}, clear=True):
            with patch("mm_exa._load_dotenv", return_value={}):
                with self.assertRaises(RuntimeError):
                    mm_exa.ExaSearch()

    def test_key_from_dotenv_when_env_unset(self):
        fake_env = {"EXA_API_KEY": "dotenv-key"}
        with patch.dict("os.environ", {}, clear=True):
            with patch("mm_exa._load_dotenv", return_value=fake_env):
                client = mm_exa.ExaSearch()
                self.assertEqual(client._api_key, "dotenv-key")


class TestExaSearchInit(unittest.TestCase):
    def test_explicit_key_bypasses_env_lookup(self):
        with patch("mm_exa.get_api_key") as mock_get_key:
            with patch("exa_py.Exa"):
                client = mm_exa.ExaSearch(api_key="explicit-key")
                self.assertEqual(client._api_key, "explicit-key")
                mock_get_key.assert_not_called()

    def test_missing_sdk_raises_runtime_error(self):
        with patch.dict("os.environ", {"EXA_API_KEY": "key"}):
            with patch.dict("sys.modules", {"exa_py": None}):
                with self.assertRaises(RuntimeError) as ctx:
                    mm_exa.ExaSearch()
                self.assertIn("exa-py not installed", str(ctx.exception))


class TestSearch(unittest.TestCase):
    def _make_mock_client(self, results=None):
        mock_result = MagicMock()
        mock_result.id = "r1"
        mock_result.title = "Test Result"
        mock_result.url = "https://example.co.nz"
        mock_result.published_date = "2024-01-01"
        mock_result.author = "Author"
        mock_result.score = 0.95
        mock_result.highlights = ["excerpt"]
        mock_response = MagicMock()
        mock_response.results = results or [mock_result]
        mock_exa = MagicMock()
        mock_exa.search = MagicMock(return_value=mock_response)
        return mock_exa

    def test_search_returns_dicts(self):
        mock_exa = self._make_mock_client()
        with patch("exa_py.Exa", return_value=mock_exa):
            client = mm_exa.ExaSearch(api_key="fake-key")
            results = client.search("plumbing Auckland")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Test Result")

    def test_search_passes_correct_params(self):
        mock_exa = self._make_mock_client(results=[])
        with patch("exa_py.Exa", return_value=mock_exa):
            client = mm_exa.ExaSearch(api_key="fake-key")
            client.search("test query", num_results=5)
        mock_exa.search.assert_called_once_with("test query", type="auto", num_results=5, contents={"highlights": True})

    def test_empty_query_raises(self):
        with patch("exa_py.Exa"):
            client = mm_exa.ExaSearch(api_key="fake-key")
            with self.assertRaises(ValueError):
                client.search("")

    def test_invalid_num_results_raises(self):
        with patch("exa_py.Exa"):
            client = mm_exa.ExaSearch(api_key="fake-key")
            with self.assertRaises(ValueError):
                client.search("test", num_results=0)
            with self.assertRaises(ValueError):
                client.search("test", num_results=101)


class TestStructuredOutput(unittest.TestCase):
    def test_search_with_output_schema(self):
        mock_output = MagicMock()
        mock_output.content = {"companies": [{"name": "Exa"}]}
        mock_output.grounding = []
        mock_response = MagicMock()
        mock_response.results = []
        mock_response.output = mock_output
        mock_exa = MagicMock()
        mock_exa.search = MagicMock(return_value=mock_response)
        schema = {"type": "object", "properties": {"companies": {"type": "array", "items": {"type": "object"}}}}
        with patch("exa_py.Exa", return_value=mock_exa):
            client = mm_exa.ExaSearch(api_key="fake-key")
            result = client.search_with_output_schema("test", output_schema=schema)
        self.assertEqual(result["output"]["content"]["companies"][0]["name"], "Exa")

    def test_schema_required(self):
        with patch("exa_py.Exa"):
            client = mm_exa.ExaSearch(api_key="fake-key")
            with self.assertRaises(ValueError):
                client.search_with_output_schema("test", output_schema={})


class TestGetContents(unittest.TestCase):
    def test_get_contents_for_urls(self):
        mock_result = MagicMock()
        mock_result.title = "Page"
        mock_result.url = "https://example.co.nz/page"
        mock_result.id = None
        mock_result.published_date = None
        mock_result.author = None
        mock_result.score = None
        mock_response = MagicMock()
        mock_response.results = [mock_result]
        mock_exa = MagicMock()
        mock_exa.get_contents = MagicMock(return_value=mock_response)
        with patch("exa_py.Exa", return_value=mock_exa):
            client = mm_exa.ExaSearch(api_key="fake-key")
            results = client.get_contents(["https://example.co.nz/page"])
        self.assertEqual(len(results), 1)

    def test_get_contents_validates_urls(self):
        with patch("exa_py.Exa"):
            client = mm_exa.ExaSearch(api_key="fake-key")
            with self.assertRaises(ValueError):
                client.get_contents(["ftp://bad.com"])


class TestCheckAvailable(unittest.TestCase):
    def test_unavailable_when_no_key(self):
        with patch.dict("os.environ", {}, clear=True):
            with patch("mm_exa._load_dotenv", return_value={}):
                result = mm_exa.check_exa_available()
                self.assertFalse(result["available"])

    def test_unavailable_when_no_sdk(self):
        with patch.dict("os.environ", {"EXA_API_KEY": "key"}):
            with patch.dict("sys.modules", {"exa_py": None}):
                result = mm_exa.check_exa_available()
                self.assertFalse(result["available"])


class TestSearchConvenienceFn(unittest.TestCase):
    def test_search_exa(self):
        mock_result = MagicMock()
        mock_result.title = "Convenience"
        mock_result.url = "https://example.co.nz"
        mock_result.id = "c1"
        mock_result.published_date = None
        mock_result.author = None
        mock_result.score = None
        mock_response = MagicMock()
        mock_response.results = [mock_result]
        mock_exa = MagicMock()
        mock_exa.search = MagicMock(return_value=mock_response)
        with patch("exa_py.Exa", return_value=mock_exa):
            results = mm_exa.search_exa("test", num_results=3, api_key="key")
        self.assertEqual(len(results), 1)


if __name__ == "__main__":
    unittest.main()
