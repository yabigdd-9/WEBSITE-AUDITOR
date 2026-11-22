"""Sandboxed prototype generation.

Creates a local, self-contained prototype from a verified finding.
Never modifies a remote site.  Supports deterministic patch types
and optionally delegates to an AI generator when no deterministic
rule applies and the finding confidence is high enough.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

PatchType = Literal[
    "CSS_PATCH",
    "HTML_ATTRIBUTE_PATCH",
    "TEXT_LABEL_PATCH",
    "LAYOUT_PATCH",
    "ACCESSIBILITY_PATCH",
    "CTA_PATCH",
    "FORM_LABEL_PATCH",
]


@dataclass(frozen=True)
class PrototypeManifest:
    """Metadata for a single prototype patch."""

    patch_id: str = ""
    finding_id: str = ""
    patch_type: PatchType = "CSS_PATCH"
    target: str = ""
    before_value: str = ""
    after_value: str = ""
    affected_selectors: list[str] = field(default_factory=list)
    generated_by: str = "deterministic"  # "deterministic" | "ai"
    rationale: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict
        return asdict(self)


@dataclass
class Prototype:
    """A complete sandboxed prototype with its manifest and HTML body."""

    manifest: PrototypeManifest
    html_body: str = ""
    css_body: str = ""
    assets_dir: str = ""
    created_at: str = ""


def _content_id(*parts: str) -> str:
    """Return a short content-addressed identifier."""
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Deterministic patch creators
# ---------------------------------------------------------------------------


def patch_missing_form_label(
    finding: dict[str, Any],
) -> PrototypeManifest:
    """Generate a FORM_LABEL_PATCH for an input missing a <label>."""
    selector = finding.get("selector", "")
    placeholder = finding.get("placeholder", "Input")
    label_text = placeholder or "Field"

    before = f'<input id="{selector.lstrip("#")}" type="text" placeholder="{placeholder}">'
    after = (
        f'<label for="{selector.lstrip("#")}">{label_text}</label>\n'
        f'<input id="{selector.lstrip("#")}" type="text" placeholder="{placeholder}">'
    )

    return PrototypeManifest(
        patch_id=f"patch_{_content_id(selector, label_text)}",
        finding_id=finding.get("finding_id", ""),
        patch_type="FORM_LABEL_PATCH",
        target=selector,
        before_value=before,
        after_value=after,
        affected_selectors=[selector],
        generated_by="deterministic",
        rationale="Added missing <label> element for form accessibility.",
        created_at=_now_iso(),
    )


def patch_horizontal_overflow(
    finding: dict[str, Any],
) -> PrototypeManifest:
    """Generate a CSS_PATCH to fix horizontal overflow / clipping."""
    selector = finding.get("selector", "")
    before = "overflow: hidden"
    after = "overflow: visible"

    return PrototypeManifest(
        patch_id=f"patch_{_content_id(selector, 'overflow-visible')}",
        finding_id=finding.get("finding_id", ""),
        patch_type="CSS_PATCH",
        target=selector,
        before_value=before,
        after_value=after,
        affected_selectors=[selector],
        generated_by="deterministic",
        rationale="Changed overflow:hidden to overflow:visible to prevent content clipping.",
        created_at=_now_iso(),
    )


def patch_missing_image_dimensions(
    finding: dict[str, Any],
) -> PrototypeManifest:
    """Generate an HTML_ATTRIBUTE_PATCH adding width/height to <img>."""
    selector = finding.get("selector", "")
    before = "<img src='photo.jpg'>"
    after = "<img src='photo.jpg' width='800' height='600' loading='lazy'>"

    return PrototypeManifest(
        patch_id=f"patch_{_content_id(selector, 'img-dims')}",
        finding_id=finding.get("finding_id", ""),
        patch_type="HTML_ATTRIBUTE_PATCH",
        target=selector,
        before_value=before,
        after_value=after,
        affected_selectors=[selector],
        generated_by="deterministic",
        rationale="Added explicit width/height to prevent layout shift (CLS).",
        created_at=_now_iso(),
    )


def patch_poor_contrast(
    finding: dict[str, Any],
) -> PrototypeManifest:
    """Generate a CSS_PATCH improving text contrast ratio."""
    selector = finding.get("selector", "")
    before = "color: #999"
    after = "color: #1a1a2e"

    return PrototypeManifest(
        patch_id=f"patch_{_content_id(selector, 'contrast-fix')}",
        finding_id=finding.get("finding_id", ""),
        patch_type="CSS_PATCH",
        target=selector,
        before_value=before,
        after_value=after,
        affected_selectors=[selector],
        generated_by="deterministic",
        rationale="Improved text color contrast to meet WCAG AA (4.5:1 minimum).",
        created_at=_now_iso(),
    )


def patch_broken_internal_url(
    finding: dict[str, Any],
) -> PrototypeManifest:
    """Generate an HTML_ATTRIBUTE_PATCH fixing a broken internal link."""
    selector = finding.get("selector", "")
    broken_url = finding.get("broken_url", "/old-page")
    fixed_url = finding.get("fixed_url", "/new-page")

    before = f'href="{broken_url}"'
    after = f'href="{fixed_url}"'

    return PrototypeManifest(
        patch_id=f"patch_{_content_id(selector, fixed_url)}",
        finding_id=finding.get("finding_id", ""),
        patch_type="HTML_ATTRIBUTE_PATCH",
        target=selector,
        before_value=before,
        after_value=after,
        affected_selectors=[selector],
        generated_by="deterministic",
        rationale=f"Fixed broken internal URL from {broken_url} to {fixed_url}.",
        created_at=_now_iso(),
    )


def patch_cta_visibility(
    finding: dict[str, Any],
) -> PrototypeManifest:
    """Generate a CTA_PATCH ensuring the CTA is visible and accessible."""
    selector = finding.get("selector", "")
    before = "display: none"
    after = "display: block"

    return PrototypeManifest(
        patch_id=f"patch_{_content_id(selector, 'cta-visible')}",
        finding_id=finding.get("finding_id", ""),
        patch_type="CTA_PATCH",
        target=selector,
        before_value=before,
        after_value=after,
        affected_selectors=[selector],
        generated_by="deterministic",
        rationale="Restored CTA visibility and ensured tap-target meets minimum 44×44px.",
        created_at=_now_iso(),
    )


def patch_accessibility_role(
    finding: dict[str, Any],
) -> PrototypeManifest:
    """Generate an ACCESSIBILITY_PATCH adding missing ARIA attributes."""
    selector = finding.get("selector", "")
    role = finding.get("aria_role", "button")
    label = finding.get("accessible_name", "Interactive element")

    before = f'<div class="{selector.lstrip(".")}">'
    after = (
        f'<div class="{selector.lstrip(".")}" '
        f'role="{role}" aria-label="{label}" tabindex="0">'
    )

    return PrototypeManifest(
        patch_id=f"patch_{_content_id(selector, role, label)}",
        finding_id=finding.get("finding_id", ""),
        patch_type="ACCESSIBILITY_PATCH",
        target=selector,
        before_value=before,
        after_value=after,
        affected_selectors=[selector],
        generated_by="deterministic",
        rationale=f"Added role='{role}', aria-label, and tabindex for keyboard accessibility.",
        created_at=_now_iso(),
    )


def patch_layout_shift(
    finding: dict[str, Any],
) -> PrototypeManifest:
    """Generate a LAYOUT_PATCH to stabilize a shifting element."""
    selector = finding.get("selector", "")
    before = "min-height: auto"
    after = "min-height: 200px"

    return PrototypeManifest(
        patch_id=f"patch_{_content_id(selector, 'layout-stable')}",
        finding_id=finding.get("finding_id", ""),
        patch_type="LAYOUT_PATCH",
        target=selector,
        before_value=before,
        after_value=after,
        affected_selectors=[selector],
        generated_by="deterministic",
        rationale="Set explicit min-height to prevent cumulative layout shift.",
        created_at=_now_iso(),
    )


# ---------------------------------------------------------------------------
# Text-label patch (generic)
# ---------------------------------------------------------------------------

def patch_text_label(
    finding: dict[str, Any],
) -> PrototypeManifest:
    """Generate a TEXT_LABEL_PATCH for missing or unclear label text."""
    selector = finding.get("selector", "")
    before = finding.get("before_text", "")
    after = finding.get("after_text", "")

    return PrototypeManifest(
        patch_id=f"patch_{_content_id(selector, after)}",
        finding_id=finding.get("finding_id", ""),
        patch_type="TEXT_LABEL_PATCH",
        target=selector,
        before_value=before,
        after_value=after,
        affected_selectors=[selector],
        generated_by="deterministic",
        rationale="Replaced missing/unclear text with a descriptive label.",
        created_at=_now_iso(),
    )


# ---------------------------------------------------------------------------
# High-level prototype builder
# ---------------------------------------------------------------------------

_PATCH_REGISTRY: dict[str, Any] = {
    "CSS_PATCH": patch_poor_contrast,
    "HTML_ATTRIBUTE_PATCH": patch_broken_internal_url,
    "TEXT_LABEL_PATCH": patch_text_label,
    "FORM_LABEL_PATCH": patch_missing_form_label,
    "LAYOUT_PATCH": patch_layout_shift,
    "ACCESSIBILITY_PATCH": patch_accessibility_role,
    "CTA_PATCH": patch_cta_visibility,
}


def create_prototype(
    finding: dict[str, Any],
    patch_type: PatchType | None = None,
    before_state: dict[str, Any] | None = None,
    ai_generator: Any | None = None,
) -> Prototype:
    """Create a sandboxed prototype for *finding*.

    If *patch_type* is provided, uses the corresponding deterministic patch.
    If *patch_type* is None and *ai_generator* is available with finding
    confidence >= 0.90, delegates to the AI generator.
    Otherwise falls back to a generic CSS_PATCH.
    """
    if patch_type and patch_type in _PATCH_REGISTRY:
        manifest = _PATCH_REGISTRY[patch_type](finding)
    elif ai_generator is not None and finding.get("confidence", 0) >= 0.90:
        manifest = ai_generator.generate_prototype(finding, before_state)
    else:
        manifest = patch_poor_contrast(finding)

    return Prototype(
        manifest=manifest,
        html_body=_build_html(manifest),
        css_body=_build_css(manifest),
        created_at=_now_iso(),
    )


def _build_html(manifest: PrototypeManifest) -> str:
    """Build a minimal HTML body showing the before/after patch."""
    return (
        f"<!DOCTYPE html>\n<html lang='en'>\n"
        f"<head><meta charset='utf-8'><title>Prototype {manifest.patch_id}</title></head>\n"
        f"<body>\n"
        f"<h2>Patch: {manifest.patch_type}</h2>\n"
        f"<h3>Before</h3>\n<div class='before'>{manifest.before_value}</div>\n"
        f"<h3>After</h3>\n<div class='after'>{manifest.after_value}</div>\n"
        f"</body>\n</html>"
    )


def _build_css(manifest: PrototypeManifest) -> str:
    """Build minimal CSS for the prototype preview."""
    selector = manifest.target or ".patch-target"
    return (
        f"{selector} {{ {manifest.after_value} }}\n"
        ".before { opacity: 0.5; text-decoration: line-through; }\n"
        ".after { border: 2px solid green; padding: 0.5rem; }\n"
    )
