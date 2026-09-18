"""Exa search integration for WEBSITE-AUDITOR money-machine pipeline.

Evidence-first, fail-closed: external search results can only corroborate,
never replace first-party observation. No model inference, no fabricated data.
"""
import json
import os
from pathlib import Path
from typing import Any, Optional


def _load_dotenv() -> dict:
    """Load key=value pairs from .env if present (no python-dotenv dependency)."""
    env: dict[str, str] = {}
    candidates = [
        Path(__file__).resolve().parent.parent / ".env",
        Path.cwd() / ".env",
    ]
    for path in candidates:
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            env[key.strip()] = val.strip().strip('"').strip("'")
    return env


def get_api_key() -> Optional[str]:
    """Resolve EXA_API_KEY from environment or .env files."""
    key = os.environ.get("EXA_API_KEY")
    if key:
        return key
    return _load_dotenv().get("EXA_API_KEY")


class ExaSearch:
    """Thin wrapper around the Exa Python SDK.

    Fail-closed: if the SDK or key is missing, search() raises RuntimeError
    rather than fabricating results.
    """

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or get_api_key()
        if not self._api_key:
            raise RuntimeError(
                "EXA_API_KEY not configured. Set it in environment or .env file."
            )
        try:
            from exa_py import Exa

            self._client = Exa(api_key=self._api_key)
        except ImportError:
            raise RuntimeError(
                "exa-py not installed. Run: pip install exa-py"
            )

    def search(
        self,
        query: str,
        num_results: int = 10,
        type_: str = "auto",
    ) -> list[dict[str, Any]]:
        """Run a search and return raw results as plain dicts.

        No model inference is performed. Results are Exa's retrieval output
        and must be independently verified before use in the pipeline.
        """
        if not query or not query.strip():
            raise ValueError("Query must be a non-empty string")
        if not (1 <= num_results <= 100):
            raise ValueError("num_results must be between 1 and 100")

        response = self._client.search(
            query,
            type=type_,
            num_results=num_results,
            contents={"highlights": True},
        )
        return [self._to_dict(r) for r in response.results]

    def search_with_output_schema(
        self,
        query: str,
        output_schema: dict[str, Any],
        num_results: int = 10,
        type_: str = "auto",
        system_prompt: Optional[str] = None,
    ) -> dict[str, Any]:
        """Run a search with structured output (Exa LLM synthesis).

        The caller MUST treat output.content as a hypothesis requiring
        independent verification. Grounding metadata is included.
        """
        if not query or not query.strip():
            raise ValueError("Query must be a non-empty string")
        if not output_schema:
            raise ValueError("output_schema is required")

        kwargs: dict[str, Any] = {
            "query": query,
            "type": type_,
            "num_results": num_results,
            "output_schema": output_schema,
            "contents": {"highlights": True},
        }
        if system_prompt:
            kwargs["system_prompt"] = system_prompt

        response = self._client.search(**kwargs)
        output = response.output
        content = getattr(output, "content", None) if output else None
        grounding = getattr(output, "grounding", None) if output else None

        serializable_grounding = None
        if grounding is not None:
            try:
                json.dumps(grounding)
                serializable_grounding = grounding
            except (TypeError, ValueError):
                serializable_grounding = str(grounding)

        return {
            "results": [self._to_dict(r) for r in response.results],
            "output": {
                "content": content,
                "grounding": serializable_grounding,
            },
        }

    def get_contents(
        self,
        urls: list[str],
        highlights: bool = True,
        text: Any = None,
    ) -> list[dict[str, Any]]:
        """Fetch content for already-known URLs."""
        if not urls:
            return []
        if not all(u.startswith(("http://", "https://")) for u in urls):
            raise ValueError("All URLs must be http:// or https://")

        kwargs: dict[str, Any] = {"highlights": highlights}
        if text is not None:
            kwargs["text"] = text
        response = self._client.get_contents(urls, **kwargs)
        return [self._to_dict(r) for r in response.results]

    @staticmethod
    def _to_dict(result) -> dict[str, Any]:
        """Convert an Exa result object to a plain dict."""
        d: dict[str, Any] = {
            "id": getattr(result, "id", None),
            "title": getattr(result, "title", None),
            "url": getattr(result, "url", None),
            "published_date": getattr(result, "published_date", None),
            "author": getattr(result, "author", None),
            "score": getattr(result, "score", None),
        }
        for attr in ("highlights", "text", "summary", "highlight_scores"):
            val = getattr(result, attr, None)
            if val is not None:
                d[attr] = val
        return d


def search_exa(
    query: str,
    num_results: int = 10,
    api_key: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Convenience: one-shot search without instantiating ExaSearch."""
    return ExaSearch(api_key=api_key).search(query, num_results=num_results)


def check_exa_available() -> dict[str, Any]:
    """Health check — used by CLI and tests. Never raises."""
    result = {
        "available": False,
        "api_key_present": bool(get_api_key()),
        "sdk_installed": False,
        "error": None,
    }
    try:
        import exa_py  # noqa: F401

        result["sdk_installed"] = True
    except ImportError as e:
        result["error"] = f"exa-py not installed: {e}"
        return result

    if not result["api_key_present"]:
        result["error"] = "EXA_API_KEY not configured"
        return result

    result["available"] = True
    return result
