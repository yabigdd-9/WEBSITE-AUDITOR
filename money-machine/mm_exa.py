"""Exa search integration for WEBSITE-AUDITOR money-machine pipeline.

Evidence-first, fail-closed: external search results can only corroborate,
never replace first-party observation. No model inference, no fabricated data.
"""
import json
import os
import re
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


class ExaAgent:
    """Exa Agent API wrapper for multi-step research workflows.

    Unlike ExaSearch (single-shot), Agent runs are async: create returns a
    run ID immediately. The caller must poll until terminal status.

    Use this for: list-building, enrichment, multi-hop research.
    """

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or get_api_key()
        if not self._api_key:
            raise RuntimeError("EXA_API_KEY not configured.")
        try:
            from exa_py import Exa
            self._client = Exa(api_key=self._api_key)
        except ImportError:
            raise RuntimeError("exa-py not installed. Run: pip install exa-py")

    def create_run(self, query: str, output_schema: dict[str, Any],
                   effort: str = "auto", max_cost_dollars: Optional[float] = None,
                   input_data: Optional[list] = None,
                   previous_run_id: Optional[str] = None) -> dict[str, Any]:
        """Create an agent run. Returns immediately with run ID."""
        kwargs: dict[str, Any] = {
            "query": query, "effort": effort, "output_schema": output_schema,
        }
        if max_cost_dollars is not None:
            kwargs["budget"] = {"max_cost_dollars": max_cost_dollars}
        if input_data:
            kwargs["input"] = {"data": input_data}
        if previous_run_id:
            kwargs["previous_run_id"] = previous_run_id
        run = self._client.agent.runs.create(**kwargs)
        return {"run_id": run.id, "status": run.status}

    def poll_run(self, run_id: str, max_wait_seconds: int = 120,
                 poll_interval: int = 4) -> dict[str, Any]:
        """Poll a run until terminal status. Blocks caller."""
        import time
        start = time.time()
        while time.time() - start < max_wait_seconds:
            run = self._client.agent.runs.get(run_id)
            if run.status in ("completed", "failed", "cancelled"):
                return self._run_to_dict(run)
            time.sleep(poll_interval)
        # Timeout — return current state
        run = self._client.agent.runs.get(run_id)
        d = self._run_to_dict(run)
        d["timed_out"] = True
        return d

    def get_run(self, run_id: str) -> dict[str, Any]:
        """Get current run state."""
        run = self._client.agent.runs.get(run_id)
        return self._run_to_dict(run)

    def list_runs(self, limit: int = 10) -> list[dict[str, Any]]:
        """List recent agent runs."""
        resp = self._client.agent.runs.list(limit=limit)
        return [self._run_to_dict(r) for r in resp.results]

    def cancel_run(self, run_id: str) -> dict[str, Any]:
        """Cancel a running agent."""
        run = self._client.agent.runs.cancel(run_id)
        return self._run_to_dict(run)

    @staticmethod
    def _run_to_dict(run) -> dict[str, Any]:
        """Convert an agent run object to a dict."""
        d: dict[str, Any] = {
            "run_id": run.id,
            "status": run.status,
            "query": getattr(run, "query", None),
            "effort": getattr(run, "effort", None),
            "created_at": getattr(run, "created_at", None),
            "finished_at": getattr(run, "finished_at", None),
            "cost_dollars": getattr(run, "cost_dollars", None),
            "stop_reason": getattr(run, "stop_reason", None),
        }
        if hasattr(run, "output") and run.output:
            output = run.output
            d["output"] = {
                "text": getattr(output, "text", None),
                "structured": getattr(output, "structured", None),
                "grounding": getattr(output, "grounding", None),
            }
        if hasattr(run, "error") and run.error:
            d["error"] = run.error
        return d


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


def _parse_yaml_simple(text: str) -> dict:
    """Parse simple YAML (our config format). No dependency on PyYAML."""
    result: dict = {}
    stack: list = [(result, -1)]  # (current_dict, indent_level)
    
    for line in text.splitlines():
        stripped = line.rstrip()
        if not stripped or stripped.startswith('#'):
            continue
        indent = len(line) - len(stripped)
        # Pop stack to find parent
        while len(stack) > 1 and stack[-1][1] >= indent:
            stack.pop()
        parent_dict = stack[-1][0]
        # Parse key: value
        if ':' in stripped:
            key, _, val = stripped.partition(':')
            key = key.strip().strip('"').strip("'")
            val = val.strip().strip('"').strip("'")
            if val == '':
                # Sub-dict
                new_dict: dict = {}
                parent_dict[key] = new_dict
                stack.append((new_dict, indent))
            else:
                # Value — try int/float/bool
                if val.lower() == 'true':
                    parent_dict[key] = True
                elif val.lower() == 'false':
                    parent_dict[key] = False
                else:
                    try:
                        if '.' in val:
                            parent_dict[key] = float(val)
                        else:
                            parent_dict[key] = int(val)
                    except ValueError:
                        parent_dict[key] = val
        elif stripped.startswith('- '):
            # List item
            val = stripped[2:].strip().strip('"').strip("'")
            # Find or create list at current parent
            if '_list' not in parent_dict:
                parent_dict['_list'] = []
            parent_dict['_list'].append(val)
    return result


def load_exa_config() -> dict[str, Any]:
    """Load exa.yaml config. Returns empty dict if not present."""
    config_path = Path(__file__).resolve().parent / "config" / "exa.yaml"
    if not config_path.exists():
        return {}
    try:
        text = config_path.read_text()
        return _parse_yaml_simple(text)
    except Exception:
        return {}


def _extract_regions_from_text(text: str) -> dict[str, list[str]]:
    """Extract regions and their queries from raw YAML text (fallback)."""
    regions: dict[str, list[str]] = {}
    current_region = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        # Top-level key (no indent)
        if not line.startswith(' ') and ':' in stripped:
            key = stripped.split(':')[0].strip()
            if key not in ('defaults',):
                current_region = key
                regions[current_region] = []
        elif current_region and stripped.startswith('- '):
            query = stripped[2:].strip().strip('"').strip("'")
            regions[current_region].append(query)
    return regions


def get_regions_from_config() -> list[str]:
    """Get list of regions from exa.yaml config."""
    config = load_exa_config()
    regions = config.get('regions', {})
    if regions:
        return list(regions.keys())
    # Fallback: parse raw text
    config_path = Path(__file__).resolve().parent / "config" / "exa.yaml"
    if config_path.exists():
        return list(_extract_regions_from_text(config_path.read_text()).keys())
    return []


def get_queries_for_region(region: str) -> list[dict[str, Any]]:
    """Get search queries and params for a region from config."""
    config = load_exa_config()
    defaults = config.get('defaults', {})
    regions = config.get('regions', {})
    region_config = regions.get(region, {})
    queries = region_config.get('queries', [])
    params = {
        'effort': region_config.get('effort', defaults.get('effort', 'auto')),
        'max_cost_dollars': region_config.get('max_cost_dollars', defaults.get('max_cost_dollars', 5.0)),
        'num_results': region_config.get('num_results', defaults.get('num_results', 10)),
        'type': region_config.get('type', defaults.get('type', 'auto')),
        'source': region_config.get('source', defaults.get('source', 'exa-search')),
    }
    return [{'query': q, **params} for q in queries]
