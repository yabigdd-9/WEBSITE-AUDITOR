#!/usr/bin/env python3
"""Deterministic prospect discovery and intake.

Discovery is intentionally separated from outreach. Inputs only become
DISCOVERED pipeline items. No email address, approval, message, or send state is
created here.

Supported sources:
  * local CSV/JSON imports (for NZBN/curated source exports)
  * a self-hosted SearXNG JSON endpoint bound to loopback

Search-result titles are treated as hints only. Canonical public website host is
the dedupe identity until later pipeline stages collect stronger evidence.
"""
from __future__ import annotations

import csv
import hashlib
import ipaddress
import json
import sqlite3
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

import mm_core as core
import mm_pipeline

MAX_IMPORT_ROWS = 5000
MAX_SEARCH_RESULTS = 50
MAX_SEARCH_RESPONSE = 2 * 1024 * 1024
SEARCH_TIMEOUT = 20
USER_AGENT = "WEBSITE-AUDITOR-Discovery/1.0"


def _first(row, names):
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""



def _adapt_source_row(row, lane):
    """Normalize common export shapes without trusting them as identity proof."""
    if not isinstance(row, dict):
        return row
    # Rows produced by this adapter are already canonical; do not erase
    # legal/trading names or source record IDs on a second normalization pass.
    if row.get("source_lane") and "source_record_id" in row:
        return dict(row)
    lane = str(lane or "").strip().lower()
    if lane == "osm" or "tags" in row:
        tags = row.get("tags") if isinstance(row.get("tags"), dict) else {}
        return {
            "name": tags.get("name") or tags.get("official_name") or "",
            "website": tags.get("website") or tags.get("contact:website") or "",
            "region": (
                tags.get("addr:city")
                or tags.get("addr:suburb")
                or tags.get("addr:district")
                or tags.get("addr:region")
                or ""
            ),
            "source": "osm-import",
            "source_record_id": str(row.get("id") or ""),
            "source_url": "",
            "source_lane": "osm",
        }
    if lane == "nzbn" or any(k in row for k in ("nzbn", "entityName", "entity_name")):
        trading = row.get("tradingName") or row.get("trading_name") or ""
        return {
            "name": row.get("entityName") or row.get("entity_name") or trading or row.get("name") or "",
            "legal_name": row.get("entityName") or row.get("entity_name") or "",
            "trading_name": trading,
            "website": (
                row.get("website")
                or row.get("websiteUrl")
                or row.get("website_url")
                or row.get("public_website")
                or ""
            ),
            "region": row.get("region") or row.get("city") or row.get("addressRegion") or "",
            "source": "nzbn-import",
            "source_record_id": str(row.get("nzbn") or row.get("NZBN") or row.get("id") or ""),
            "source_url": str(row.get("source_url") or ""),
            "source_lane": "nzbn",
        }
    return dict(row)


def _source_provenance(row, source):
    lane = str(row.get("source_lane") or source or "import").strip().lower()
    return {
        "lane": lane[:80],
        "record_id": str(row.get("source_record_id") or row.get("nzbn") or "")[:160],
        "source_url": str(row.get("source_url") or "")[:500],
    }

def root_url(raw):
    value = str(raw or "").strip()
    if not value:
        raise ValueError("website is required")
    if "://" not in value:
        value = "https://" + value
    host = core.public_url(value)
    parsed = urlsplit(value)
    scheme = parsed.scheme.lower()
    return urlunsplit((scheme, parsed.netloc, "/", "", "")), host


def normalize_candidate(row, default_region="", default_source="import"):
    if not isinstance(row, dict):
        raise ValueError("candidate must be an object")
    row = _adapt_source_row(row, row.get("source_lane") or default_source)
    raw_url = _first(row, ("public_website", "website_url", "website", "url", "link"))
    website, host = root_url(raw_url)
    name = _first(row, ("business_name", "company_name", "name", "title")) or host
    region = _first(row, ("region", "city", "area")) or str(default_region or "").strip()
    source = _first(row, ("source",)) or str(default_source or "import").strip()
    normalized_name = name.strip().casefold()
    return {
        "name": name[:250],
        "normalized_name": normalized_name,
        "legal_name": _first(row, ("legal_name", "entityName", "entity_name"))[:250],
        "trading_name": _first(row, ("trading_name", "tradingName"))[:250],
        "region": region[:160],
        "public_website": website,
        "canonical_host": host,
        "source": source[:160],
        "provenance": _source_provenance(row, source),
    }


def read_candidates(path, default_region="", default_source="import"):
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("discovery input exceeds 20 MiB")

    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))
    elif suffix in {".json", ".jsonl"}:
        if suffix == ".jsonl":
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        else:
            doc = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(doc, dict):
                if isinstance(doc.get("results"), list):
                    rows = doc["results"]
                elif isinstance(doc.get("elements"), list):
                    rows = [_adapt_source_row(row, "osm") for row in doc["elements"]]
                elif isinstance(doc.get("items"), list):
                    rows = [_adapt_source_row(row, default_source) for row in doc["items"]]
                else:
                    rows = []
            else:
                rows = doc
    else:
        raise ValueError("discovery input must be .csv, .json, or .jsonl")

    if not isinstance(rows, list):
        raise ValueError("discovery input must contain a list of rows")
    if len(rows) > MAX_IMPORT_ROWS:
        raise ValueError(f"discovery input exceeds {MAX_IMPORT_ROWS} rows")

    normalized = []
    rejected = []
    for index, row in enumerate(rows, 1):
        try:
            normalized.append(normalize_candidate(row, default_region, default_source))
        except (ValueError, TypeError) as exc:
            rejected.append({"row": index, "reason": str(exc)[:200]})
    return normalized, rejected


def _existing(d):
    by_host = {}
    by_name = {}
    for row in d.execute("SELECT id,name,public_website FROM businesses WHERE is_dummy=0"):
        name = (row["name"] or "").strip().casefold()
        if name:
            by_name[name] = row["id"]
        if row["public_website"]:
            try:
                host = core.public_url(row["public_website"])
            except ValueError:
                continue
            by_host[host] = row["id"]
    return by_host, by_name


def ingest(d, candidates, actor="discovery-v2", dry_run=False):
    """Dedupe and enqueue candidates. Returns a deterministic intake summary."""
    if not dry_run:
        mm_pipeline.migrate(d)
    by_host, by_name = _existing(d)
    inserted = []
    duplicates = []
    rejected = []

    for index, raw in enumerate(candidates, 1):
        try:
            candidate = normalize_candidate(raw, raw.get("region", ""), raw.get("source", actor))
        except (ValueError, TypeError, AttributeError) as exc:
            rejected.append({"row": index, "reason": str(exc)[:200]})
            continue

        host = candidate["canonical_host"]
        name_key = candidate["name"].strip().casefold()
        existing_id = by_host.get(host) or by_name.get(name_key)
        if existing_id:
            duplicates.append({
                "row": index,
                "business_id": existing_id,
                "canonical_host": host,
            })
            continue

        if dry_run:
            virtual_id = -(len(inserted) + 1)
            inserted.append({
                "business_id": virtual_id,
                "canonical_host": host,
                "dry_run": True,
            })
            by_host[host] = virtual_id
            by_name[name_key] = virtual_id
            continue

        cursor = d.execute(
            "INSERT INTO businesses(name,region,public_website,source,discovered_at,"
            "current_status,is_dummy) VALUES(?,?,?,?,?,'discovered',0)",
            (
                candidate["name"],
                candidate["region"],
                candidate["public_website"],
                candidate["source"],
                core.now(),
            ),
        )
        business_id = cursor.lastrowid
        core.ensure_business_columns(d)
        d.execute(
            "UPDATE businesses SET canonical_host=?, normalized_name=? WHERE id=?",
            (host, candidate["name"].strip().casefold(), business_id),
        )
        d.execute(
            "INSERT INTO mm_deals(business_id,stage,updated_at) VALUES(?,'DISCOVERED',?)",
            (business_id, core.now()),
        )
        core.event(
            d,
            "discovery_intake",
            business_id,
            json.dumps(
                {
                    "source": candidate["source"],
                    "canonical_host": host,
                    "provenance": candidate["provenance"],
                    "legal_name": candidate.get("legal_name"),
                    "trading_name": candidate.get("trading_name"),
                    "actor": actor,
                },
                sort_keys=True,
            ),
        )
        mm_pipeline.enqueue(
            d,
            business_id,
            "DISCOVERED",
            payload={
                "discovery_source": candidate["source"],
                "discovery_provenance": candidate["provenance"],
                "legal_name": candidate.get("legal_name"),
                "trading_name": candidate.get("trading_name"),
                "canonical_host": host,
                "contact_eligibility": "UNASSESSED",
            },
        )
        inserted.append({"business_id": business_id, "canonical_host": host})
        by_host[host] = business_id
        by_name[name_key] = business_id

    return {
        "inserted": inserted,
        "duplicates": duplicates,
        "rejected": rejected,
        "counts": {
            "inserted": len(inserted),
            "duplicates": len(duplicates),
            "rejected": len(rejected),
        },
        "outreach_eligible": False,
        "next_state": "DISCOVERED",
    }


def _loopback_endpoint(endpoint):
    parsed = urlsplit(str(endpoint or "").strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "http" or host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("SearXNG endpoint must be loopback HTTP")
    if parsed.username or parsed.password:
        raise ValueError("SearXNG endpoint credentials are not allowed in URL")
    if parsed.port is not None and not 1 <= parsed.port <= 65535:
        raise ValueError("invalid SearXNG port")
    return parsed.geturl().rstrip("/")


def searxng_candidates(query, region, endpoint="http://127.0.0.1:8888", limit=20):
    query = str(query or "").strip()
    if not query or len(query) > 200:
        raise ValueError("query must contain 1-200 characters")
    region = str(region or "").strip()
    if not region:
        raise ValueError("region is required")
    limit = max(1, min(int(limit), MAX_SEARCH_RESULTS))
    endpoint = _loopback_endpoint(endpoint)

    params = urlencode({
        "q": query,
        "format": "json",
        "categories": "general",
        "language": "en-NZ",
        "safesearch": "1",
    })
    request = Request(
        endpoint + "/search?" + params,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urlopen(request, timeout=SEARCH_TIMEOUT) as response:
        body = response.read(MAX_SEARCH_RESPONSE + 1)
    if len(body) > MAX_SEARCH_RESPONSE:
        raise ValueError("SearXNG response exceeds size limit")
    document = json.loads(body.decode("utf-8"))
    results = document.get("results", [])
    if not isinstance(results, list):
        raise ValueError("invalid SearXNG JSON response")

    candidates = []
    seen = set()
    query_ref = hashlib.sha256(query.encode("utf-8")).hexdigest()[:12]
    for result in results:
        if len(candidates) >= limit or not isinstance(result, dict):
            break
        try:
            website, host = root_url(result.get("url"))
        except ValueError:
            continue
        if host in seen:
            continue
        seen.add(host)
        candidates.append({
            "name": host,
            "region": region,
            "public_website": website,
            "source": f"searxng-local:{query_ref}",
            "canonical_host": host,
        })
    return candidates


def normalize_intake_url(url):
    """Normalize and validate an intake URL according to v32 canonicalization rules.

    Allowed transformations:
    - trim whitespace
    - prepend https:// to valid bare domain
    - lowercase hostname
    - strip fragments
    - strip userinfo
    - normalize canonical host

    Reject:
    - garbage
    - private IP
    - loopback IP
    - .example
    - .invalid
    - .test
    - example.com
    - example.net
    - example.org

    Returns normalized URL string on success.
    Raises ValueError on rejection.
    """
    if not isinstance(url, str):
        raise ValueError("URL must be a string")

    # Trim whitespace
    value = url.strip()
    if not value:
        raise ValueError("website is required")

    # Prepend https:// if no scheme present
    if "://" not in value:
        value = "https://" + value

    # Parse URL
    try:
        parsed = urlsplit(value)
    except Exception as e:
        raise ValueError(f"invalid URL: {e}")

    # Validate scheme
    if parsed.scheme not in ('https', 'http'):
        raise ValueError('Public HTTP(S) website URL required')

    # Extract and validate host
    host = parsed.hostname
    if not host:
        raise ValueError('Public HTTP(S) website URL required')

    # Lowercase hostname and remove www prefix
    host = host.lower().removeprefix('www.')

    # Reject username/password in URL (userinfo)
    if parsed.username or parsed.password:
        raise ValueError('username/password in URL not allowed')

    # Validate port
    if parsed.port not in (None, 80, 443):
        raise ValueError('Port must be None, 80, or 443 for public websites')

    # Reject localhost and internal domains
    if host == 'localhost' or host.endswith(('.local', '.internal')):
        raise ValueError('Private website URL rejected')

    # Reject private IP addresses
    try:
        ip_addr = ipaddress.ip_address(host)
        if not ip_addr.is_global:
            raise ValueError('Private IP rejected')
    except ValueError as e:
        # Check if this is from ipaddress.ip_address failing (not an IP address)
        # or if it's our own 'Private IP rejected' error
        if 'Private IP rejected' in str(e):
            raise  # Re-raise our own private IP error
        # Otherwise, it's not an IP address, which is fine for hostnames
        pass
    except Exception as e:
        # Re-raise if it's a different ValueError
        if 'AddressValueError' in str(e):
            raise

    # Reject reserved and example TLDs/domains
    host_parts = host.split('.')
    if len(host_parts) >= 2:
        # Check for reserved TLDs
        tld = host_parts[-1]
        if tld in ('example', 'invalid', 'test'):
            raise ValueError(f'reserved TLD "{tld}" not allowed')

        # Check for example domains
        if len(host_parts) >= 2:
            domain = '.'.join(host_parts[-2:])
            if domain in ('example.com', 'example.net', 'example.org'):
                raise ValueError(f'example domain "{domain}" not allowed')

    # Reconstruct URL without fragments, userinfo, with normalized host
    # Keep the original path and query, but remove fragment
    normalized = urlunsplit((
        parsed.scheme,
        host,  # already lowercased
        parsed.path or '/',  # ensure path exists
        parsed.query,  # keep query parameters
        ''  # remove fragment
    ))

    return normalized


def _business_fk_references(d):
    """Dynamically discover (table, column) pairs referencing businesses(id)."""
    refs = []
    for row in d.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        table = row[0]
        if table == "businesses" or table.startswith("sqlite_"):
            continue
        for fk in d.execute(f"PRAGMA foreign_key_list({table})"):
            # fk: (id, seq, ref_table, from_column, to_column, ...)
            if fk[2] == "businesses" and fk[3]:
                refs.append((table, fk[3]))
    return refs


def dedupe_businesses(d, actor="dedupe-v1", dry_run=False):
    """Merge duplicate businesses on the canonical key, transactionally.

    Canonical key: (canonical_host, normalized_name, region). The lowest valid
    canonical ID survives. Foreign keys are repointed to the survivor; rows
    that would violate a UNIQUE constraint are left pointing at the retained
    suppressed business and reported as conflicts. Duplicates are marked with
    suppression_reason='duplicate_of:<ID>' and current_status='suppressed';
    their pipeline items are parked in SUPPRESSED. Nothing is ever deleted.

    Idempotent: a second run finds every duplicate already suppressed and
    performs no further mutation.
    """
    core.ensure_business_columns(d)
    ts = core.now()

    rows = [
        dict(r)
        for r in d.execute(
            "SELECT id, name, public_website, region, is_dummy, suppression_reason "
            "FROM businesses ORDER BY id"
        )
    ]

    groups = {}
    for row in rows:
        host = ""
        if row["public_website"]:
            try:
                host = core.public_url(row["public_website"])
            except ValueError:
                host = ""
        norm = (row["name"] or "").strip().casefold()
        region = (row["region"] or "").strip().casefold()
        if not dry_run:
            d.execute(
                "UPDATE businesses SET canonical_host=?, normalized_name=? WHERE id=?",
                (host or None, norm or None, row["id"]),
            )
        if row["is_dummy"] or row["suppression_reason"] or not host or not norm:
            continue
        groups.setdefault((host, norm, region), []).append(row["id"])

    merges = []
    for ids in groups.values():
        if len(ids) > 1:
            for dup in ids[1:]:
                merges.append({"survivor_id": ids[0], "duplicate_id": dup})

    if dry_run:
        return {
            "actor": actor,
            "dry_run": True,
            "merges": merges,
            "deleted": 0,
        }

    refs = _business_fk_references(d)
    repointed = {}
    conflicts = {}
    for merge in merges:
        survivor, dup = merge["survivor_id"], merge["duplicate_id"]
        for table, column in refs:
            if table == "pipeline_items":
                continue  # parked below; PK makes blind repointing unsafe
            for r in d.execute(
                f"SELECT rowid FROM {table} WHERE {column}=?", (dup,)
            ).fetchall():
                try:
                    d.execute(
                        f"UPDATE {table} SET {column}=? WHERE rowid=?",
                        (survivor, r[0]),
                    )
                    repointed[table] = repointed.get(table, 0) + 1
                except sqlite3.IntegrityError as exc:
                    if "UNIQUE constraint failed" not in str(exc):
                        raise  # not a conflict: abort so the caller rolls back
                    # Survivor already holds an equivalent unique row; keep the
                    # duplicate's row attached to the retained suppressed record.
                    conflicts[table] = conflicts.get(table, 0) + 1

        d.execute(
            "UPDATE businesses SET suppression_reason=?, current_status='suppressed' "
            "WHERE id=? AND suppression_reason IS NULL",
            (f"duplicate_of:{survivor}", dup),
        )

        item = d.execute(
            "SELECT state FROM pipeline_items WHERE business_id=?", (dup,)
        ).fetchone()
        if item and item["state"] != "SUPPRESSED":
            d.execute(
                "UPDATE pipeline_items SET state='SUPPRESSED', next_retry_at=NULL, "
                "lease_owner=NULL, lease_until=NULL, updated_at=? WHERE business_id=?",
                (ts, dup),
            )
            d.execute(
                "INSERT INTO pipeline_events(business_id,from_state,to_state,"
                "actor,reason,evidence,event_at) VALUES(?,?,?,?,?,?,?)",
                (
                    dup,
                    item["state"],
                    "SUPPRESSED",
                    actor,
                    f"duplicate_of:{survivor}",
                    json.dumps(
                        {"survivor_id": survivor, "duplicate_id": dup},
                        sort_keys=True,
                    ),
                    ts,
                ),
            )

    return {
        "actor": actor,
        "dry_run": False,
        "merges": merges,
        "merged": len(merges),
        "repointed": repointed,
        "conflicts": conflicts,
        "deleted": 0,
    }
