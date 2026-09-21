"""One local YAML/JSON configuration; URLs identify exact sites, never guessed clients."""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo


def site_url(value):
    parsed = urlsplit(str(value))
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Client URL must be an absolute HTTP(S) URL without credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("Client URL must not include a query string or fragment")
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", "", ""))


def load_config(path):
    path = Path(path).resolve()
    if path.stat().st_size > 1_000_000:
        raise ValueError("Agency configuration exceeds 1 MB")
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        try:
            import yaml
        except ImportError:
            raise ValueError("Install PyYAML or use the equivalent JSON configuration") from None
        data = yaml.safe_load(text)
    return validate_config(data, path.parent)


def validate_config(data, base=None):
    if not isinstance(data, dict):
        raise ValueError("Agency configuration must be a mapping")
    # Copy before normalizing so the caller can safely reuse the original configuration.
    try:
        data = json.loads(json.dumps(data))
    except (TypeError, ValueError) as exc:
        raise ValueError("Config values must be plain strings, numbers, lists or mappings") from exc
    if not isinstance(data.get("clients"), list) or not all(
        isinstance(c, dict) for c in data["clients"]
    ):
        raise ValueError("clients must be a list of client mappings")
    for section in ("agency", "contact", "reporting"):
        if section in data and not isinstance(data[section], dict):
            raise ValueError(f"{section} must be a mapping")
    agency = data.setdefault("agency", {})
    for key, default in [
        ("name", "Website Agency"),
        ("primary_color", "#0f766e"),
        ("secondary_color", "#142c3b"),
    ]:
        agency.setdefault(key, default)
    for key in ("primary_color", "secondary_color"):
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", str(agency[key])):
            raise ValueError(f"agency.{key} must be a six-digit hex color")
    data.setdefault("timezone", "Pacific/Auckland")
    ZoneInfo(data["timezone"])
    reporting = data.setdefault("reporting", {})
    reporting.setdefault("enabled", True)
    if not isinstance(reporting["enabled"], bool):
        raise ValueError("reporting.enabled must be a boolean")
    if reporting.get("auto_send") or reporting.get("schedule_enabled"):
        raise ValueError(
            "This release generates drafts only; auto_send and schedule_enabled must be false"
        )
    data.setdefault("contact", {})
    for value in [data["contact"].get("email", "")] + [
        c.get("email", "") for c in data.get("clients", [])
    ]:
        if not isinstance(value, str) or "\r" in value or "\n" in value:
            raise ValueError("Email fields cannot contain newlines")
        if value and not re.fullmatch(r"[^\s<>@,;]+@[^\s<>@,;]+\.[^\s<>@,;]+", value):
            raise ValueError("Use one plain email address in each email field")
    clients = data.get("clients")
    if not isinstance(clients, list) or not clients:
        raise ValueError("Configure at least one explicit client")
    ids, urls = set(), set()
    for client in clients:
        identity = client.get("id", "")
        if (
            not isinstance(identity, str)
            or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", identity)
            or identity in ids
        ):
            raise ValueError(
                "Each client needs a unique lowercase id (letters, digits, underscore, hyphen)"
            )
        client["url"] = site_url(client["url"])
        if client["url"] in urls:
            raise ValueError("Duplicate client URL; configure one client per exact site URL")
        client.setdefault("name", identity)
        client.setdefault("profile", "static")
        if not isinstance(client["name"], str) or any(c in client["name"] for c in "\r\n"):
            raise ValueError("Client name must be one line")
        ids.add(identity)
        urls.add(client["url"])
    # Embed only bounded raster logos. No SVG scripts, remote fetches, or arbitrary local URLs.
    agency.pop("logo_data", None)
    if agency.get("logo"):
        path = (Path(base or ".") / agency["logo"]).resolve()
        agency["logo"] = str(path)
        body = path.read_bytes()
        if len(body) > 2_000_000:
            raise ValueError("Logo exceeds 2 MB")
        mime = (
            "image/png"
            if body.startswith(b"\x89PNG\r\n\x1a\n")
            else "image/jpeg"
            if body.startswith(b"\xff\xd8\xff")
            else None
        )
        if not mime:
            raise ValueError("Logo must be PNG or JPEG")
        agency["logo_data"] = f"data:{mime};base64," + base64.b64encode(body).decode()
    return data


def get_client(config, identity):
    for client in config["clients"]:
        if client["id"] == identity:
            return client
    raise ValueError("Unknown configured client: " + identity)
