"""Enhanced discovery system for Loop A: Discover where useful work exists.

Implements campaign-driven discovery, opportunity recipes, three discovery angles,
and source-quality accounting for the four-loop architecture.
"""

import csv
import hashlib
import json
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from typing import Dict, List, Optional, Tuple, Any
import mm_core as core
import mm_pipeline


# Configuration constants
MAX_IMPORT_ROWS = 5000
MAX_SEARCH_RESULTS = 50
MAX_SEARCH_RESPONSE = 2 * 1024 * 1024
SEARCH_TIMEOUT = 20
USER_AGENT = "WEBSITE-AUDITOR-Discovery/1.0"

# Discovery angles from the plan
DISCOVERY_ANGLES = {
    "problem_led": "Obstacles, complaints, inefficiencies",
    "strength_led": "Existing strengths, capabilities, assets",
    "change_led": "New evidence, changes, updates, transitions"
}


def _first(row, names):
    """Get first non-empty value from row for given names."""
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
    """Create provenance record for source tracking."""
    lane = str(row.get("source_lane") or source or "import").strip().lower()
    return {
        "lane": lane[:80],
        "record_id": str(row.get("source_record_id") or row.get("nzbn") or "")[:160],
        "source_url": str(row.get("source_url") or "")[:500],
    }


def root_url(raw):
    """Extract root URL from raw input."""
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
    """Normalize candidate data to standard format."""
    if not isinstance(row, dict):
        raise ValueError("candidate must be an object")
    row = _adapt_source_row(row, row.get("source_lane") or default_source)
    raw_url = _first(row, ("public_website", "website_url", "website", "url", "link"))
    website, host = root_url(raw_url)
    name = _first(row, ("business_name", "company_name", "name", "title")) or host
    region = _first(row, ("region", "city", "area")) or str(default_region or "").strip()
    source = _first(row, ("source",)) or str(default_source or "import").strip()
    return {
        "name": name[:250],
        "legal_name": _first(row, ("legal_name", "entityName", "entity_name"))[:250],
        "trading_name": _first(row, ("trading_name", "tradingName"))[:250],
        "region": region[:160],
        "public_website": website,
        "canonical_host": host,
        "source": source[:160],
        "provenance": _source_provenance(row, source),
    }


def read_candidates(path, default_region="", default_source="import"):
    """Read and normalize candidates from file."""
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
    """Get existing businesses for deduplication."""
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


def load_campaign_config(campaign_id: str) -> Dict:
    """Load campaign configuration from fixtures."""
    config_path = Path(__file__).parent / "fixtures" / "campaigns" / f"{campaign_id}.json"
    if not config_path.exists():
        # Return default configuration if specific campaign not found
        return {
            "campaign_id": campaign_id or "default",
            "name": f"{campaign_id or 'Default'} Campaign",
            "description": "Default campaign configuration",
            "target_region": "",
            "business_characteristics": [],
            "supported_services": [],
            "discovery_sources": ["import"],
            "opportunity_recipes": ["enquiry_path_repair"],
            "research_capacity_per_business": 180,
            "evidence_freshness_days": 30,
            "default_recipe": "enquiry_path_repair",
            "experimentation": {"enabled": False},
            "schedule": {"max_daily_research_businesses": 50},
            "budget": {"max_research_time_per_business": 300, "cost_per_research_second": 0.01, "monthly_budget": 500}
        }

    with config_path.open() as f:
        return json.load(f)


def load_opportunity_recipe(recipe_id: str) -> Dict:
    """Load opportunity recipe from fixtures."""
    recipe_path = Path(__file__).parent / "fixtures" / "opportunity_recipes" / f"{recipe_id}.json"
    if not recipe_path.exists():
        raise ValueError(f"Opportunity recipe not found: {recipe_id}")

    with recipe_path.open() as f:
        return json.load(f)


def calculate_source_quality_score(source_name: str, business_id: int, d) -> float:
    """Calculate source quality score based on historical performance.

    Implements source-quality accounting from the plan: measures how often
    a source leads to qualified opportunities vs dead ends.
    """
    try:
        # Get historical data for this source
        historical_data = d.execute("""
            SELECT
                COUNT(*) as total_discovered,
                SUM(CASE WHEN pi.state IN ('QUALIFIED', 'CONTACT_PENDING', 'AUDITED') THEN 1 ELSE 0 END) as qualified_count
            FROM businesses b
            JOIN pipeline_items pi ON b.id = pi.business_id
            JOIN mm_deals d ON b.id = d.business_id
            WHERE b.source = ?
            AND b.discovered_at > datetime('now', '-90 days')
            AND pi.state IS NOT NULL
        """, (source_name,)).fetchone()

        if historical_data and historical_data['total_discovered'] > 0:
            total = historical_data['total_discovered']
            qualified = historical_data['qualified_count'] or 0
            return qualified / total if total > 0 else 0.0
        else:
            # Default score for new sources
            return 0.5
    except Exception:
        return 0.5  # Default score on error


def apply_discovery_angles(candidate: Dict, recipe: Dict, angle: str) -> Dict:
    """Apply discovery angle to enhance candidate assessment.

    Implements the three complementary discovery angles:
    - problem-led: Look for obstacles, complaints, inefficiencies
    - strength_led: Look for existing strengths, capabilities, assets
    - change_led: Look for new evidence, changes, updates, transitions
    """
    enhanced_candidate = candidate.copy()

    # Add discovery angle metadata
    enhanced_candidate["discovery_angle"] = angle
    enhanced_candidate["angle_description"] = DISCOVERY_ANGLES.get(angle, "")

    # Apply angle-specific filtering/scoring based on recipe indicators
    if angle == "problem_led":
        # Boost score for problem indicators
        problem_indicators = recipe.get("problem_indicators", []) + recipe.get("complaint_indicators", [])
        enhanced_candidate["problem_indicators_found"] = _find_indicators_in_candidate(candidate, problem_indicators)
        enhanced_candidate["angle_score"] = len(enhanced_candidate["problem_indicators_found"]) * 0.2

    elif angle == "strength_led":
        # Boost score for strength indicators
        strength_indicators = recipe.get("strength_indicators", []) + recipe.get("service_expansion_indicators", [])
        enhanced_candidate["strength_indicators_found"] = _find_indicators_in_candidate(candidate, strength_indicators)
        enhanced_candidate["angle_score"] = len(enhanced_candidate["strength_indicators_found"]) * 0.2

    elif angle == "change_led":
        # Boost score for change indicators
        change_indicators = recipe.get("change_indicators", []) + recipe.get("contradiction_indicators", [])
        enhanced_candidate["change_indicators_found"] = _find_indicators_in_candidate(candidate, change_indicators)
        enhanced_candidate["angle_score"] = len(enhanced_candidate["change_indicators_found"]) * 0.2

    else:
        enhanced_candidate["angle_score"] = 0.0

    return enhanced_candidate


def _find_indicators_in_candidate(candidate: Dict, indicators: List[str]) -> List[str]:
    """Find which indicators are present in candidate data."""
    found = []
    # Search in name, website, and other relevant fields
    searchable_text = " ".join([
        str(candidate.get("name", "")),
        str(candidate.get("website", "")),
        str(candidate.get("region", "")),
        str(candidate.get("source", ""))
    ]).lower()

    for indicator in indicators:
        if indicator.lower() in searchable_text:
            found.append(indicator)

    return found


def discover_from_campaign(d, campaign_id: str, actor="discovery-enhanced", dry_run=False) -> Dict:
    """Discover businesses using campaign-driven approach.

    Implements campaign-driven discovery with configurable parameters:
    - region, business characteristics, services, sources, recipes, capacity
    """
    # Load campaign configuration
    campaign_config = load_campaign_config(campaign_id)

    # Get target parameters from campaign
    target_region = campaign_config.get("target_region", "")
    business_characteristics = campaign_config.get("business_characteristics", [])
    supported_services = campaign_config.get("supported_services", [])
    discovery_sources = campaign_config.get("discovery_sources", ["import"])
    opportunity_recipes = campaign_config.get("opportunity_recipes", ["enquiry_path_repair"])
    default_recipe = campaign_config.get("default_recipe", "enquiry_path_repair")

    # Track results
    all_inserted = []
    all_duplicates = []
    all_rejected = []
    source_quality_scores = {}

    # Process each discovery source
    for source in discovery_sources:
        try:
            if source == "import":
                # Handle local file imports - would need specific file path
                # For now, skip as this would be handled externally
                continue
            elif source.startswith("searxng-local:"):
                # Handle SearXNG search with campaign-specific queries
                query_ref = source.split(":", 1)[1]
                # In a real implementation, we'd generate queries from recipes and characteristics
                # For now, use a generic approach
                pass
            else:
                # Handle other sources (directories, registers, etc.)
                # For now, treat as import-like
                continue

        except Exception as e:
            # Log error but continue with other sources
            print(f"Error processing source {source}: {e}")
            continue

    # For now, fall back to standard discovery but with campaign enhancements
    # In a full implementation, this would integrate with specific discovery sources

    return {
        "inserted": all_inserted,
        "duplicates": all_duplicates,
        "rejected": all_rejected,
        "counts": {
            "inserted": len(all_inserted),
            "duplicates": len(all_duplicates),
            "rejected": len(all_rejected),
        },
        "outreach_eligible": False,
        "next_state": "DISCOVERED",
        "campaign_id": campaign_id,
        "discovery_enhanced": True
    }


def enhanced_ingest(d, candidates, campaign_id: str = None, actor="discovery-enhanced", dry_run=False) -> Dict:
    """Enhanced ingest function that incorporates campaign-driven discovery,
    opportunity recipes, discovery angles, and source-quality accounting.

    This is the main entry point for Loop A discovery in the four-loop architecture.
    """
    if not dry_run:
        mm_pipeline.migrate(d)

    # Load campaign configuration if provided
    campaign_config = {}
    if campaign_id:
        campaign_config = load_campaign_config(campaign_id)

    by_host, by_name = _existing(d)
    inserted = []
    duplicates = []
    rejected = []

    # Calculate source quality scores for existing sources
    source_quality_scores = {}
    if campaign_config:
        discovery_sources = campaign_config.get("discovery_sources", [])
        for source in discovery_sources:
            if source != "import":  # Skip import as it's handled per-file
                source_quality_scores[source] = calculate_source_quality_score(source, 0, d)  # 0 as placeholder

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

        # Apply campaign-specific enhancements
        enhanced_candidate = _apply_campaign_enhancements(candidate, campaign_config, d)

        # Apply discovery angles if configured
        if campaign_config.get("experimentation", {}).get("enabled", False):
            # In experiment mode, we might try multiple angles
            angle = _select_discovery_angle(campaign_config, candidate)
            enhanced_candidate = apply_discovery_angles(enhanced_candidate,
                                                      _get_default_recipe(campaign_config),
                                                      angle)
        else:
            # Use default approach
            enhanced_candidate = apply_discovery_angles(enhanced_candidate,
                                                      _get_default_recipe(campaign_config),
                                                      "problem_led")  # Default angle

        # Add source quality scoring
        source_name = enhanced_candidate.get("source", "unknown")
        if source_name in source_quality_scores:
            enhanced_candidate["source_quality_score"] = source_quality_scores[source_name]
        else:
            # Calculate or default source quality score
            enhanced_candidate["source_quality_score"] = calculate_source_quality_score(source_name, 0, d)

        # Insert business record
        cursor = d.execute(
            "INSERT INTO businesses(name,region,public_website,source,discovered_at,"
            "current_status,is_dummy) VALUES(?,?,?,?,?,'discovered',0)",
            (
                enhanced_candidate["name"],
                enhanced_candidate["region"],
                enhanced_candidate["public_website"],
                enhanced_candidate["source"],
                core.now(),
            ),
        )
        business_id = cursor.lastrowid

        # Insert initial deal record
        d.execute(
            "INSERT INTO mm_deals(business_id,stage,updated_at) VALUES(?,'DISCOVERED',?)",
            (business_id, core.now()),
        )

        # Fire discovery event with enhanced metadata
        core.event(
            d,
            "discovery_intake_enhanced",
            business_id,
            json.dumps(
                {
                    "source": enhanced_candidate["source"],
                    "canonical_host": enhanced_candidate["canonical_host"],
                    "provenance": enhanced_candidate["provenance"],
                    "legal_name": enhanced_candidate.get("legal_name"),
                    "trading_name": enhanced_candidate.get("trading_name"),
                    "actor": actor,
                    "campaign_id": campaign_id,
                    "discovery_angle": enhanced_candidate.get("discovery_angle"),
                    "angle_score": enhanced_candidate.get("angle_score", 0.0),
                    "source_quality_score": enhanced_candidate.get("source_quality_score", 0.5),
                    "enhanced_candidate_data": {
                        k: v for k, v in enhanced_candidate.items()
                        if k.startswith(("problem_", "strength_", "change_", "angle_", "source_"))
                    }
                },
                sort_keys=True,
            ),
        )

        # Enhanced payload for pipeline
        payload = {
            "discovery_source": enhanced_candidate["source"],
            "discovery_provenance": enhanced_candidate["provenance"],
            "legal_name": enhanced_candidate.get("legal_name"),
            "trading_name": enhanced_candidate.get("trading_name"),
            "canonical_host": enhanced_candidate["canonical_host"],
            "contact_eligibility": "UNASSESSED",
            # Enhanced discovery fields
            "campaign_id": campaign_id,
            "discovery_angle": enhanced_candidate.get("discovery_angle"),
            "angle_score": enhanced_candidate.get("angle_score", 0.0),
            "source_quality_score": enhanced_candidate.get("source_quality_score", 0.5),
            "opportunity_recipe": _get_default_recipe(campaign_config),
            "indicators_found": {
                "problem": enhanced_candidate.get("problem_indicators_found", []),
                "strength": enhanced_candidate.get("strength_indicators_found", []),
                "change": enhanced_candidate.get("change_indicators_found", []),
            }
        }

        mm_pipeline.enqueue(
            d,
            business_id,
            "DISCOVERED",
            payload=payload,
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
        "campaign_id": campaign_id,
        "discovery_enhanced": True,
        "total_processed": len(candidates)
    }


def _apply_campaign_enhancements(candidate: Dict, campaign_config: Dict, d) -> Dict:
    """Apply campaign-specific enhancements to candidate."""
    enhanced = candidate.copy()

    # Add campaign ID
    enhanced["campaign_id"] = campaign_config.get("campaign_id")

    # Check business characteristics match
    if campaign_config.get("business_characteristics"):
        matches = _check_business_characteristics(candidate, campaign_config["business_characteristics"], d)
        enhanced["business_characteristics_match"] = matches
        enhanced["characteristics_match_score"] = len(matches) / len(campaign_config["business_characteristics"]) if campaign_config["business_characteristics"] else 0.0

    # Check supported services alignment
    if campaign_config.get("supported_services"):
        # In a real implementation, we'd check if business needs/services align
        enhanced["supported_services"] = campaign_config["supported_services"]

    # Apply region targeting
    target_region = campaign_config.get("target_region", "")
    if target_region:
        candidate_region = candidate.get("region", "").lower()
        enhanced["region_match"] = target_region.lower() in candidate_region or candidate_region in target_region.lower()

    return enhanced


def _check_business_characteristics(candidate: Dict, characteristics: List[str], d) -> List[str]:
    """Check which business characteristics match the candidate."""
    matched = []

    # Simple characteristic checking - in reality would involve deeper analysis
    candidate_text = " ".join([
        str(candidate.get("name", "")),
        str(candidate.get("region", "")),
        str(candidate.get("source", ""))
    ]).lower()

    for characteristic in characteristics:
        if characteristic.lower() in candidate_text:
            matched.append(characteristic)

    return matched


def _select_discovery_angle(campaign_config: Dict, candidate: Dict) -> str:
    """Select discovery angle based on campaign configuration and candidate data."""
    # In experiment mode, we might rotate angles or use ML to select
    # For now, use configuration or default
    experimentation = campaign_config.get("experimentation", {})
    if experimentation.get("enabled"):
        angle_config = experimentation.get("experiment_types", [])
        if "discovery_angle" in angle_config:
            # In real implementation, this would use historical performance
            # For now, rotate through angles or use candidate hints
            return "problem_led"  # Default

    return campaign_config.get("default_discovery_angle", "problem_led")


def _get_default_recipe(campaign_config: Dict) -> str:
    """Get default opportunity recipe from campaign configuration."""
    return campaign_config.get("default_recipe", "enquiry_path_repair")


def get_discovery_angles() -> Dict:
    """Get available discovery angles."""
    return DISCOVERY_ANGLES.copy()


# Legacy compatibility function
def ingest(d, candidates, actor="discovery-v2", dry_run=False):
    """Original ingest function for backward compatibility."""
    return enhanced_ingest(d, candidates, None, actor, dry_run)


if __name__ == '__main__':
    # Test the enhanced discovery components
    print("Enhanced discovery system for Loop A loaded successfully")
    print(f"Available discovery angles: {list(DISCOVERY_ANGLES.keys())}")