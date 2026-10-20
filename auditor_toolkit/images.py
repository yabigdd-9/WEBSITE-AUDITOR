"""Image markup evidence; this does not measure rendered image performance."""

from __future__ import annotations

import hashlib
from collections import Counter
from typing import Any
from urllib.parse import urlsplit

from bs4 import BeautifulSoup, Tag

from .checks import Finding, dedupe_findings

CHECK_VERSION = "2"
MAX_HTML_CHARACTERS = 8 * 1024 * 1024
MAX_IMAGES = 2000
MAX_PICTURE_SOURCES = 2000
MAX_ATTRIBUTE_CHARACTERS = 2048
ASCII_WHITESPACE = "\t\n\f\r "
IMAGE_ATTRIBUTES = (
    "src",
    "srcset",
    "sizes",
    "loading",
    "fetchpriority",
    "width",
    "height",
    "decoding",
)
SOURCE_ATTRIBUTES = ("srcset", "sizes", "type", "media", "width", "height")


def _attribute(tag: Tag, name: str) -> str | None:
    value = tag.get(name)
    return value if isinstance(value, str) else None


def _nonempty(value: str | None) -> bool:
    return bool(value is not None and value.strip(ASCII_WHITESPACE))


def _positive_dimension(value: str | None) -> bool:
    return bool(value and value.isascii() and value.isdecimal() and any(c != "0" for c in value))


def _enum(value: str | None, keywords: set[str], default: str) -> dict[str, str | bool]:
    # Enumerated attribute keywords are ASCII case insensitive, not whitespace stripped.
    lowered = value.lower() if value is not None else None
    return {
        "specified": value is not None,
        "keyword_valid": lowered in keywords,
        "effective_state_hint": lowered if lowered in keywords else default,
    }


def _attributes(tag: Tag, names: tuple[str, ...]) -> dict[str, Any]:
    values = {name: _attribute(tag, name) for name in names}
    truncated = {
        name: hashlib.sha256(value.encode()).hexdigest()
        for name, value in values.items()
        if value is not None and len(value) > MAX_ATTRIBUTE_CHARACTERS
    }
    return {
        "values": {
            name: value[:MAX_ATTRIBUTE_CHARACTERS] if value is not None else None
            for name, value in values.items()
        },
        "truncated_attribute_sha256": truncated,
    }


def _format_hint(src: str | None) -> str | None:
    if not src:
        return None
    try:
        path = urlsplit(src).path.lower()
    except ValueError:
        return None
    # A URL extension is a hint, never verified MIME type or measured byte savings.
    if src.lower().startswith("data:"):
        return "data_url_unverified"
    return next(
        (
            suffix[1:]
            for suffix in (".avif", ".webp", ".png", ".jpeg", ".jpg", ".gif", ".svg")
            if path.endswith(suffix)
        ),
        None,
    )


def _review_finding(
    key: str,
    title: str,
    url: str,
    selector: str,
    observed: str,
    action: str,
    confidence: str = "observed",
) -> Finding:
    return Finding(
        key,
        title,
        "Review the captured image markup",
        "low",
        url,
        check="images",
        selector=selector,
        confidence=confidence,
        evidence_source="static-dom:" + selector,
        observed=observed,
        business_impact="Image delivery may need correction; user impact is not measured.",
        remediation_action=action,
        remediation_automation="HUMAN_REVIEW",
        effort_band="S",
    )


def analyse_html(html: str, url: str, headers: dict) -> tuple[list[Finding], dict[str, Any]]:
    """Inspect supplied HTML only; never fetch assets, infer layout or invent a score.

    Selectors identify nodes in this static parse. Browser DOM identity must be
    checked before any remediation; parser repair and script execution may differ.
    """
    if not isinstance(html, str) or len(html) > MAX_HTML_CHARACTERS:
        raise ValueError("Image analysis requires HTML within the declared character limit")
    soup = BeautifulSoup(html, "html.parser")
    images = soup.find_all("img")
    if len(images) > MAX_IMAGES:
        raise ValueError("Image element limit exceeded; coverage is incomplete")
    if (
        sum(1 for tag in soup.find_all("source") if tag.find_parent("picture"))
        > MAX_PICTURE_SOURCES
    ):
        raise ValueError("Picture source limit exceeded; coverage is incomplete")
    records: list[dict[str, Any]] = []
    findings: list[Finding] = []
    counts: Counter[str] = Counter()
    pictures = {id(tag): index for index, tag in enumerate(soup.find_all("picture"), 1)}
    for index, image in enumerate(images, 1):
        selector = f"xpath=(//img)[{index}]"
        inactive = image.find_parent(["template", "noscript"]) is not None
        if inactive:
            counts["template_or_noscript_images_excluded"] += 1
            continue
        loading = _enum(_attribute(image, "loading"), {"lazy", "eager"}, "eager")
        priority = _enum(_attribute(image, "fetchpriority"), {"high", "low", "auto"}, "auto")
        counts["loading_" + str(loading["effective_state_hint"])] += 1
        if loading["specified"] and not loading["keyword_valid"]:
            counts["invalid_loading_keyword"] += 1
        if priority["specified"] and not priority["keyword_valid"]:
            counts["invalid_fetchpriority_keyword"] += 1
        sources = []
        parent = image.parent
        if isinstance(parent, Tag) and parent.name == "picture":
            for source_index, source in enumerate(parent.find_all("source", recursive=False), 1):
                # Only preceding direct source siblings participate in this image's selection.
                if not any(sibling is image for sibling in source.next_siblings):
                    continue
                source_selector = (
                    f"xpath=(//picture)[{pictures[id(parent)]}]/source[{source_index}]"
                )
                usable = _nonempty(_attribute(source, "srcset"))
                sources.append(
                    {
                        "selector": source_selector,
                        "attributes": _attributes(source, SOURCE_ATTRIBUTES),
                        "nonempty_srcset_declared": usable,
                    }
                )
                if not usable:
                    findings.append(
                        _review_finding(
                            "picture_source_empty_srcset",
                            "Picture source has no nonempty srcset",
                            url,
                            source_selector,
                            "Preceding picture source declares no nonempty image candidate string.",
                            "Review this source; provide valid candidates or remove the unused source. The img fallback may still load.",
                        )
                    )
        responsive = _nonempty(_attribute(image, "srcset")) or any(
            source["nonempty_srcset_declared"] for source in sources
        )
        explicit_dimensions = _positive_dimension(
            _attribute(image, "width")
        ) and _positive_dimension(_attribute(image, "height"))
        hint = _format_hint(_attribute(image, "src"))
        counts["responsive_markup_declared" if responsive else "no_responsive_markup_declared"] += 1
        counts[
            "positive_img_dimensions_declared"
            if explicit_dimensions
            else "no_positive_img_dimension_pair"
        ] += 1
        if hint:
            counts["src_extension_hint_" + hint] += 1
        if loading["effective_state_hint"] == "lazy" and priority["effective_state_hint"] == "high":
            counts["lazy_high_priority_review"] += 1
            findings.append(
                _review_finding(
                    "image_lazy_high_priority_review",
                    "Image combines lazy loading with high fetch priority",
                    url,
                    selector,
                    'loading="lazy" and fetchpriority="high" are both declared.',
                    "Measure initial viewport and LCP role. Use eager loading for a confirmed initial-viewport image; review high priority for an offscreen image.",
                    confidence="heuristic",
                )
            )
        records.append(
            {
                "source_ordinal": index,
                "selector": selector,
                "selector_scope": "static_parse_requires_browser_confirmation",
                "attributes": _attributes(image, IMAGE_ATTRIBUTES),
                "picture_sources": sources,
                "loading": loading,
                "fetchpriority": priority,
                "nonempty_responsive_markup_declared": responsive,
                "positive_img_dimension_pair_declared": explicit_dimensions,
                "src_extension_hint_not_verified_mime": hint,
                "rendered_measurements": {
                    "viewport_position": None,
                    "lcp_role": None,
                    "selected_source": None,
                    "transfer_bytes": None,
                    "decode_time_ms": None,
                    "layout_shift": None,
                },
            }
        )
    return dedupe_findings(findings), {
        "method": "static-image-markup-v2",
        "check_version": CHECK_VERSION,
        "scope": "supplied_html_img_elements",
        "status": "observed_static_markup" if records else "no_active_img_markup",
        "html_sha256": hashlib.sha256(html.encode()).hexdigest(),
        "source_img_elements": len(images),
        "total_images": len(records),
        "counts": dict(sorted(counts.items())),
        "images": records,
        "performance_score": None,
        "field_core_web_vitals": None,
        "limitations": [
            "No browser rendering, CSS layout, selected-image or asset-byte measurement.",
            "Nonempty srcset is an observation, not validation of candidates, sizes or media queries.",
            "No responsive markup, no dimensions or a PNG/JPEG extension alone is not a defect.",
            "CSS background images and script-created images are outside this static img scope.",
            "No blanket lazy-loading recommendation; initial-viewport/LCP placement requires rendered evidence.",
            "Template/noscript descendants are excluded; scripting-disabled rendering is not inspected.",
        ],
    }
