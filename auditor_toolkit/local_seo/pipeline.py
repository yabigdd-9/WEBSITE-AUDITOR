"""Local SEO pipeline orchestrator.

Coordinates: extract NAP → extract schema → detect location pages → classify
service area → check consistency → optionally corroborate externally → score
→ output findings.

Escalation strategy: cheap checks first, expensive geo lookup only if needed.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .schema import (
    GeoCoordinates,
    NormalizedAddress,
    NormalizedPhone,
)


@dataclass(frozen=True)
class PipelineResult:
    """Complete output of a local SEO audit pipeline run."""

    run_id: str
    started_at: str
    completed_at: str
    duration_seconds: float
    entity: dict[str, Any] | None = None
    location_pages: list[dict[str, Any]] = field(default_factory=list)
    service_area_classification: dict[str, Any] = field(default_factory=dict)
    consistency_findings: list[dict[str, Any]] = field(default_factory=list)
    corroboration: dict[str, Any] = field(default_factory=dict)
    geo_corroboration: list[dict[str, Any]] = field(default_factory=list)
    scored_findings: list[dict[str, Any]] = field(default_factory=list)
    scoring_summary: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": round(self.duration_seconds, 2),
            "entity": self.entity,
            "location_pages": self.location_pages,
            "service_area_classification": self.service_area_classification,
            "consistency_findings": self.consistency_findings,
            "corroboration": self.corroboration,
            "geo_corroboration": self.geo_corroboration,
            "scored_findings": self.scored_findings,
            "scoring_summary": self.scoring_summary,
            "errors": self.errors,
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class LocalSEOPipeline:
    """Orchestrates the full local SEO audit pipeline.

    Usage:
        pipeline = LocalSEOPipeline(run_id="v38-001")
        result = pipeline.run(
            html=html_content,
            url="https://example.com/contact",
            sitemap_urls=[...],
            external_evidence=[...],
        )
    """

    def __init__(
        self,
        run_id: str | None = None,
        default_region: str = "NZ",
        enable_geo_lookup: bool = False,
        enable_external_corroboration: bool = False,
    ) -> None:
        self.run_id = run_id or self._generate_run_id()
        self.default_region = default_region
        self.enable_geo_lookup = enable_geo_lookup
        self.enable_external_corroboration = enable_external_corroboration
        self._started_at = ""
        self._errors: list[str] = []
        self._warnings: list[str] = []

    def run(
        self,
        html: str = "",
        url: str = "",
        sitemap_urls: list[str] | None = None,
        external_evidence: list[Any] | None = None,
        geocoder_fn: Any = None,
    ) -> PipelineResult:
        """Run the full pipeline.

        Args:
            html: Main page HTML (contact/homepage).
            url: URL of the main page.
            sitemap_urls: URLs to scan for location pages.
            external_evidence: Pre-fetched external evidence records.
            geocoder_fn: Optional callable(normalized_address) -> GeoCoordinates.
        """
        self._started_at = datetime.now(timezone.utc).isoformat()
        start = time.monotonic()

        # Phase 1: Extract NAP from main page (cheap)
        nap_data = self._extract_nap(html, url)

        # Phase 2: Extract schema from main page (cheap)
        schema_data = self._extract_schema(html, url)

        # Phase 3: Detect location pages (requires sitemap)
        location_pages: list[dict[str, Any]] = []
        if sitemap_urls:
            location_pages = self._detect_location_pages(sitemap_urls)

        # Phase 4: Classify service area (cheap)
        sa_classification = self._classify_service_area(
            nap_data, schema_data
        )

        # Phase 5: Check consistency (cheap)
        consistency_findings = self._check_consistency(
            nap_data, schema_data
        )

        # Phase 6: Geo corroboration (expensive — only if enabled)
        geo_results: list[dict[str, Any]] = []
        if self.enable_geo_lookup and geocoder_fn and schema_data.get("geo"):
            geo_results = self._corroborate_geo(
                schema_data.get("geo"),
                schema_data.get("address"),
                geocoder_fn,
            )

        # Phase 7: External corroboration (expensive — only if enabled)
        corroboration_result: dict[str, Any] = {}
        if self.enable_external_corroboration and external_evidence:
            corroboration_result = self._corroborate_external(
                nap_data, external_evidence
            )

        # Phase 8: Score findings
        scored, summary = self._score_all(
            consistency_findings,
            schema_data,
            geo_results,
        )

        elapsed = time.monotonic() - start
        completed_at = datetime.now(timezone.utc).isoformat()

        return PipelineResult(
            run_id=self.run_id,
            started_at=self._started_at,
            completed_at=completed_at,
            duration_seconds=elapsed,
            entity=self._build_entity(nap_data, schema_data),
            location_pages=location_pages,
            service_area_classification=sa_classification,
            consistency_findings=consistency_findings,
            corroboration=corroboration_result,
            geo_corroboration=geo_results,
            scored_findings=[f.to_dict() for f in scored],
            scoring_summary=summary.to_dict(),
            errors=self._errors,
            warnings=self._warnings,
        )

    @staticmethod
    def _generate_run_id() -> str:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return f"local-seo-{ts}"

    # ------------------------------------------------------------------
    # Phase 1: NAP extraction
    # ------------------------------------------------------------------

    def _extract_nap(self, html: str, url: str) -> dict[str, Any]:
        """Extract NAP from page HTML."""
        try:
            from .adapters.website import extract_nap_from_html
            return extract_nap_from_html(html, url)
        except ImportError:
            self._warnings.append("website adapter not available — using basic extraction")
            return _basic_nap_extract(html, url)
        except Exception as exc:
            self._errors.append(f"NAP extraction failed: {exc}")
            return {}

    # ------------------------------------------------------------------
    # Phase 2: Schema extraction
    # ------------------------------------------------------------------

    def _extract_schema(self, html: str, url: str) -> dict[str, Any]:
        """Extract LocalBusiness schema from page HTML."""
        try:
            from .local_schema import extract_local_business_from_html
            entities = extract_local_business_from_html(html, url)
            if not entities:
                return {"has_schema": False, "entities": []}

            first = entities[0]
            return {
                "has_schema": True,
                "entities": entities,
                "name": first.get("name", ""),
                "address": first.get("address"),
                "phones": first.get("phones", []),
                "geo": first.get("geo"),
                "opening_hours": first.get("opening_hours", []),
                "schema_url": first.get("url", ""),
                "entity_type": first.get("entity_type", []),
            }
        except Exception as exc:
            self._errors.append(f"Schema extraction failed: {exc}")
            return {"has_schema": False, "entities": [], "error": str(exc)}

    # ------------------------------------------------------------------
    # Phase 3: Location page detection
    # ------------------------------------------------------------------

    def _detect_location_pages(self, urls: list[str]) -> list[dict[str, Any]]:
        """Detect location pages from a list of URLs."""
        try:
            from .location_pages import scan_urls_for_location_patterns
            matching = scan_urls_for_location_patterns(urls)
            return [
                {"url": u, "classification": "location", "confidence": 0.5}
                for u in matching
            ]
        except Exception as exc:
            self._errors.append(f"Location page detection failed: {exc}")
            return []

    # ------------------------------------------------------------------
    # Phase 4: Service area classification
    # ------------------------------------------------------------------

    def _classify_service_area(
        self,
        nap_data: dict[str, Any],
        schema_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Classify the business type."""
        try:
            from .service_area import classify_service_area

            has_addr = bool(nap_data.get("address"))
            schema_addr = schema_data.get("address")
            schema_has_addr = bool(
                schema_addr
                and (
                    getattr(schema_addr, "normalized", "")
                    or getattr(schema_addr, "raw", "")
                )
            )

            analysis = classify_service_area(
                has_address=has_addr,
                address_visible=has_addr,
                page_text=nap_data.get("page_text", ""),
                schema_has_address=schema_has_addr,
                schema_has_service_area=schema_data.get("has_service_area", False),
            )

            return {
                "classification": analysis.classification,
                "confidence": analysis.confidence,
                "reasons": analysis.reasons,
            }
        except Exception as exc:
            self._errors.append(f"Service area classification failed: {exc}")
            return {}

    # ------------------------------------------------------------------
    # Phase 5: Consistency checking
    # ------------------------------------------------------------------

    def _check_consistency(
        self,
        nap_data: dict[str, Any],
        schema_data: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Check schema vs visible content consistency."""
        try:
            from .consistency import check_nap_consistency, contradictions_to_findings

            contradictions = check_nap_consistency(
                schema_name=schema_data.get("name", ""),
                schema_address=schema_data.get("address"),
                schema_phones=schema_data.get("phones"),
                schema_hours=schema_data.get("opening_hours"),
                schema_geo=schema_data.get("geo"),
                schema_url=schema_data.get("schema_url", ""),
                visible_name=nap_data.get("name", ""),
                visible_address=nap_data.get("address"),
                visible_phones=nap_data.get("phones"),
                visible_hours=nap_data.get("opening_hours"),
            )

            return contradictions_to_findings(
                contradictions,
                source_url=nap_data.get("source_url", ""),
                page_url=nap_data.get("url", ""),
            )
        except Exception as exc:
            self._errors.append(f"Consistency check failed: {exc}")
            return []

    # ------------------------------------------------------------------
    # Phase 6: Geo corroboration
    # ------------------------------------------------------------------

    def _corroborate_geo(
        self,
        schema_geo: GeoCoordinates | None,
        address: NormalizedAddress | None,
        geocoder_fn: Any,
    ) -> list[dict[str, Any]]:
        """Corroborate geo coordinates via external geocoder."""
        if not schema_geo or not address:
            return []

        try:
            from .geo import address_cache_key, cache_geo, corroborate_geo, get_cached_geo

            cache_key = address_cache_key(address)
            cached = get_cached_geo(cache_key)
            if cached:
                return [cached.to_dict()]

            geocoder_result = geocoder_fn(address)
            if not geocoder_result:
                return []

            result = corroborate_geo(schema_geo, geocoder_result, address)
            cache_geo(cache_key, result)
            return [result.to_dict()]
        except Exception as exc:
            self._errors.append(f"Geo corroboration failed: {exc}")
            return []

    # ------------------------------------------------------------------
    # Phase 7: External corroboration
    # ------------------------------------------------------------------

    def _corroborate_external(
        self,
        nap_data: dict[str, Any],
        external_records: list[Any],
    ) -> dict[str, Any]:
        """Corroborate against external evidence."""
        try:
            from .corroboration import corroborate_record

            result = corroborate_record(
                canonical_name=nap_data.get("name", ""),
                canonical_address_normalized=nap_data.get("address_normalized", ""),
                canonical_phone_e164=nap_data.get("phone_e164", ""),
                external_records=external_records,
            )
            return result.to_dict()
        except Exception as exc:
            self._errors.append(f"External corroboration failed: {exc}")
            return {}

    # ------------------------------------------------------------------
    # Phase 8: Scoring
    # ------------------------------------------------------------------

    def _score_all(
        self,
        consistency_findings: list[dict[str, Any]],
        schema_data: dict[str, Any],
        geo_results: list[dict[str, Any]],
    ) -> tuple:
        """Score all findings and build summary."""
        from .scoring import (
            ScoredFinding,
            build_scoring_summary,
            detect_missing_geo,
            detect_missing_schema,
            detect_schema_visible_conflict,
            score_finding,
        )

        scored: list[ScoredFinding] = []
        scored.extend(_score_consistency(consistency_findings, score_finding))
        scored.extend(
            _score_schema(
                consistency_findings,
                schema_data,
                detect_missing_schema,
                detect_missing_geo,
                detect_schema_visible_conflict,
            )
        )
        scored.extend(_score_geo_conflicts(geo_results, score_finding))

        summary = build_scoring_summary(scored)
        return scored, summary


    # ------------------------------------------------------------------
    # Entity builder
    # ------------------------------------------------------------------

    def _build_entity(
        self,
        nap_data: dict[str, Any],
        schema_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Build a unified entity representation."""
        try:
            from .identity import build_identity

            name = nap_data.get("name") or schema_data.get("name", "")
            raw_evidence: list[tuple[str, str]] = []

            if name:
                raw_evidence.append((name, "visible"))
            if schema_data.get("name"):
                raw_evidence.append((schema_data["name"], "schema"))

            entity = build_identity(
                business_id=f"biz-{self.run_id}",
                names=raw_evidence,
                emails=[nap_data["email"]] if nap_data.get("email") else None,
                schema_entities=schema_data.get("entities"),
            )
            return entity.to_dict()
        except Exception:
            return {
                "business_id": f"biz-{self.run_id}",
                "canonical_name": nap_data.get("name") or schema_data.get("name", ""),
            }


# ---------------------------------------------------------------------------
# Fallback basic NAP extractor (when adapter is unavailable)
# ---------------------------------------------------------------------------


def _basic_nap_extract(html: str, url: str) -> dict[str, Any]:
    """Minimal NAP extraction using BeautifulSoup."""
    import re

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text()

    # Simple name extraction from title
    title = ""
    title_tag = soup.find("title")
    if title_tag and title_tag.string:
        title = title_tag.string.strip()

    # Phone extraction (NZ format)
    phones: list[NormalizedPhone] = []
    phone_patterns = re.findall(r'\+64\d{8,10}|\(\d{2}\)\s?\d{3,4}\s?\d{3,4}', text)
    for p in phone_patterns[:3]:
        try:
            from .phone import normalize_phone
            phones.append(normalize_phone(p, source="basic_extract"))
        except Exception:
            pass

    return {
        "name": title,
        "url": url,
        "source_url": url,
        "phones": phones,
        "page_text": text[:5000],
        "address": None,
        "address_normalized": "",
        "phone_e164": phones[0].e164 if phones else "",
    }


def _score_consistency(findings: list[dict[str, Any]], score_finding: Any) -> list[Any]:
    scored = []
    for finding in findings:
        result = score_finding(
            defect_key=finding.get("defect_key", ""),
            source_url=finding.get("source_url", ""),
            page_url=finding.get("page_url", ""),
            confidence=finding.get("confidence", 0.8),
            detail=finding.get("observed", ""),
        )
        if result:
            scored.append(result)
    return scored


def _score_schema(
    findings: list[dict[str, Any]],
    schema_data: dict[str, Any],
    detect_missing_schema: Any,
    detect_missing_geo: Any,
    detect_schema_visible_conflict: Any,
) -> list[Any]:
    scored = []
    if not schema_data.get("has_schema"):
        result = detect_missing_schema(has_schema=False)
        if result:
            scored.append(result)
    elif not schema_data.get("geo"):
        result = detect_missing_geo(has_geo=False)
        if result:
            scored.append(result)
    if findings:
        result = detect_schema_visible_conflict(findings)
        if result:
            scored.append(result)
    return scored


def _score_geo_conflicts(geo_results: list[dict[str, Any]], score_finding: Any) -> list[Any]:
    scored = []
    for geo in geo_results:
        if geo.get("status") != "MATERIAL_CONFLICT":
            continue
        result = score_finding(
            defect_key="schema_visible_conflict",
            confidence=0.9,
            detail=f"Geo coordinates conflict: {geo.get('detail', '')}",
        )
        if result:
            scored.append(result)
    return scored
