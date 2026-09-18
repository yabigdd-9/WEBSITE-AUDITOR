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
    def test_get_contents_highlights_only(self):
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
        self.assertEqual(results[0]["url"], "https://example.co.nz/page")
        mock_exa.get_contents.assert_called_once_with(["https://example.co.nz/page"], highlights=True)

    def test_get_contents_with_text(self):
        mock_result = MagicMock()
        mock_result.title = "Page"
        mock_result.url = "https://example.co.nz/page"
        mock_result.id = None
        mock_result.published_date = None
        mock_result.author = None
        mock_result.score = None
        mock_result.text = "Full page text"
        mock_response = MagicMock()
        mock_response.results = [mock_result]
        mock_exa = MagicMock()
        mock_exa.get_contents = MagicMock(return_value=mock_response)
        with patch("exa_py.Exa", return_value=mock_exa):
            client = mm_exa.ExaSearch(api_key="fake-key")
            results = client.get_contents(["https://example.co.nz/page"], text={"max_characters": 5000})
        self.assertEqual(results[0].get("text"), "Full page text")
        mock_exa.get_contents.assert_called_once_with(["https://example.co.nz/page"], highlights=True, text={"max_characters": 5000})

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


class TestExaAgent(unittest.TestCase):
    """Tests for the Agent API wrapper."""

    def _make_mock_agent_client(self):
        mock_exa = MagicMock()
        return mock_exa

    def test_agent_init_requires_key(self):
        with patch.dict("os.environ", {}, clear=True):
            with patch("mm_exa._load_dotenv", return_value={}):
                with self.assertRaises(RuntimeError):
                    mm_exa.ExaAgent()

    def test_create_run(self):
        mock_run = MagicMock()
        mock_run.id = "agent_run_abc123"
        mock_run.status = "running"
        mock_exa = self._make_mock_agent_client()
        mock_exa.agent.runs.create = MagicMock(return_value=mock_run)
        with patch("exa_py.Exa", return_value=mock_exa):
            agent = mm_exa.ExaAgent(api_key="fake-key")
            result = agent.create_run(
                query="find plumbing companies",
                output_schema={"type": "object"},
            )
        self.assertEqual(result["run_id"], "agent_run_abc123")
        self.assertEqual(result["status"], "running")

    def test_create_run_with_budget(self):
        mock_run = MagicMock()
        mock_run.id = "agent_run_budget"
        mock_run.status = "running"
        mock_exa = self._make_mock_agent_client()
        mock_exa.agent.runs.create = MagicMock(return_value=mock_run)
        with patch("exa_py.Exa", return_value=mock_exa):
            agent = mm_exa.ExaAgent(api_key="fake-key")
            result = agent.create_run(
                query="test",
                output_schema={"type": "object"},
                max_cost_dollars=2.0,
            )
        # Verify budget was passed
        call_kwargs = mock_exa.agent.runs.create.call_args[1]
        self.assertEqual(call_kwargs["budget"], {"max_cost_dollars": 2.0})

    def test_poll_run_completed(self):
        mock_output = MagicMock()
        mock_output.text = "Found 5 companies"
        mock_output.structured = {"companies": []}
        mock_output.grounding = []
        mock_run = MagicMock()
        mock_run.id = "agent_run_abc"
        mock_run.status = "completed"
        mock_run.query = "find companies"
        mock_run.effort = "auto"
        mock_run.output = mock_output
        mock_run.cost_dollars = 0.5
        mock_run.stop_reason = "schema_satisfied"
        mock_run.created_at = "2024-01-01"
        mock_run.finished_at = "2024-01-01"
        mock_exa = self._make_mock_agent_client()
        mock_exa.agent.runs.get = MagicMock(return_value=mock_run)
        with patch("exa_py.Exa", return_value=mock_exa):
            agent = mm_exa.ExaAgent(api_key="fake-key")
            result = agent.poll_run("agent_run_abc", max_wait_seconds=1)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["output"]["text"], "Found 5 companies")

    def test_poll_run_failed(self):
        mock_run = MagicMock()
        mock_run.id = "agent_run_fail"
        mock_run.status = "failed"
        mock_run.error = "Budget exceeded"
        mock_run.query = "test"
        mock_run.effort = "low"
        mock_run.created_at = None
        mock_run.finished_at = None
        mock_run.cost_dollars = None
        mock_run.stop_reason = None
        mock_exa = self._make_mock_agent_client()
        mock_exa.agent.runs.get = MagicMock(return_value=mock_run)
        with patch("exa_py.Exa", return_value=mock_exa):
            agent = mm_exa.ExaAgent(api_key="fake-key")
            result = agent.poll_run("agent_run_fail", max_wait_seconds=1)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"], "Budget exceeded")

    def test_list_runs(self):
        mock_run1 = MagicMock()
        mock_run1.id = "r1"
        mock_run1.status = "completed"
        mock_run1.query = "q1"
        mock_run1.effort = "auto"
        mock_run1.created_at = None
        mock_run1.finished_at = None
        mock_run1.cost_dollars = 1.0
        mock_run1.stop_reason = None
        mock_resp = MagicMock()
        mock_resp.results = [mock_run1]
        mock_exa = self._make_mock_agent_client()
        mock_exa.agent.runs.list = MagicMock(return_value=mock_resp)
        with patch("exa_py.Exa", return_value=mock_exa):
            agent = mm_exa.ExaAgent(api_key="fake-key")
            result = agent.list_runs()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["run_id"], "r1")

    def test_cancel_run(self):
        mock_run = MagicMock()
        mock_run.id = "agent_run_cancel"
        mock_run.status = "cancelled"
        mock_run.query = "test"
        mock_run.effort = "auto"
        mock_run.created_at = None
        mock_run.finished_at = None
        mock_run.cost_dollars = None
        mock_run.stop_reason = None
        mock_exa = self._make_mock_agent_client()
        mock_exa.agent.runs.cancel = MagicMock(return_value=mock_run)
        with patch("exa_py.Exa", return_value=mock_exa):
            agent = mm_exa.ExaAgent(api_key="fake-key")
            result = agent.cancel_run("agent_run_cancel")
        self.assertEqual(result["status"], "cancelled")


if __name__ == "__main__":
    unittest.main()
