"""Deterministic patch rules.

Each function takes raw HTML or CSS content and a finding dict, then
returns (patched_content, patch_manifest_entry).  Patches are purely
local transformations — they never touch a live site.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

from auditor_toolkit.proof.prototype import PrototypeManifest

_OVERFLOW_HIDDEN = "overflow: hidden"
_OVERFLOW_VISIBLE = "overflow: visible"


def _content_id(*parts: str) -> str:
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_manifest(
    finding: dict[str, Any],
    patch_type: str,
    target: str,
    before: str,
    after: str,
    rationale: str,
) -> PrototypeManifest:
    return PrototypeManifest(
        patch_id=f"patch_{_content_id(target, patch_type)}",
        finding_id=finding.get("finding_id", ""),
        patch_type=patch_type,  # type: ignore[arg-type]
        target=target,
        before_value=before,
        after_value=after,
        affected_selectors=[finding.get("selector", "")],
        generated_by="deterministic",
        rationale=rationale,
        created_at=_now_iso(),
    )


# ---------------------------------------------------------------------------
# Patch: missing form label
# ---------------------------------------------------------------------------

def patch_missing_form_label(
    html: str,
    finding: dict[str, Any],
) -> tuple[str, PrototypeManifest]:
    """Inject a <label> before an <input> that has no associated label.

    Uses the input's *id*, *placeholder*, or *name* attribute to derive
    label text.
    """
    selector = finding.get("selector", "")
    input_id = selector.lstrip("#") if selector.startswith("#") else ""

    if input_id:
        targeted = _patch_input_by_id(html, finding, input_id)
        if targeted is not None:
            return targeted

    # Fallback: find an input in the page and derive the label from that input.
    input_match = re.search(r'<input([^>]*)>', html)
    if input_match:
        return _patch_first_input(html, finding, selector, input_match)

    return html, _make_manifest(
        finding, "FORM_LABEL_PATCH", selector,
        html, html,
        "No injectable <input> found; label patch not applicable.",
    )


def _label_for_input(attrs: str, fallback_id: str) -> tuple[str, str]:
    placeholder = re.search(r'placeholder=["\']([^"\']+)["\']', attrs)
    name = re.search(r'name=["\']([^"\']+)["\']', attrs)
    input_id_match = re.search(r'id=["\']([^"\']+)["\']', attrs)
    input_id = input_id_match.group(1) if input_id_match else (name.group(1) if name else fallback_id)
    label = placeholder.group(1) if placeholder else input_id.replace("-", " ").title()
    return input_id, label


def _patch_input_by_id(html: str, finding: dict[str, Any], input_id: str):
    pattern = rf'<input([^>]*\bid=["\']{re.escape(input_id)}["\'][^>]*)>'
    match = re.search(pattern, html, re.I)
    if not match:
        return None
    full_tag = match.group(0)
    actual_id, label = _label_for_input(match.group(1), input_id)
    label_html = f'<label for="{actual_id}">{label}</label>\n'
    patched = html[:match.start()] + label_html + full_tag + html[match.end():]
    return patched, _make_manifest(
        finding,
        "FORM_LABEL_PATCH",
        finding.get("selector", ""),
        full_tag,
        label_html + full_tag,
        f"Added <label for='{actual_id}'> for form accessibility.",
    )


def _patch_first_input(html: str, finding: dict[str, Any], selector: str, match: re.Match):
    full_tag = match.group(0)
    input_id, label = _label_for_input(match.group(1), "field")
    label_html = f'<label for="{input_id}">{label}</label>\n'
    patched = html[:match.start()] + label_html + html[match.start():]
    return patched, _make_manifest(
        finding,
        "FORM_LABEL_PATCH",
        selector or f"#{input_id}",
        full_tag,
        label_html + full_tag,
        f"Added <label for='{input_id}'> for form accessibility.",
    )


# ---------------------------------------------------------------------------
# Patch: horizontal overflow
# ---------------------------------------------------------------------------

def patch_horizontal_overflow(
    html: str,
    finding: dict[str, Any],
) -> tuple[str, PrototypeManifest]:
    """Replace overflow:hidden with overflow:visible on the target element."""
    selector = finding.get("selector", "")
    target_class = selector.lstrip(".") if selector.startswith(".") else selector

    # Inline style
    before_inline = _OVERFLOW_HIDDEN
    after_inline = _OVERFLOW_VISIBLE
    patched = html.replace(_OVERFLOW_HIDDEN, _OVERFLOW_VISIBLE, 1)

    if patched != html:
        return patched, _make_manifest(
            finding, "CSS_PATCH", selector,
            before_inline, after_inline,
            "Changed overflow:hidden to overflow:visible to prevent content clipping.",
        )

    # CSS rule in <style> block
    style_pattern = rf'({re.escape(target_class)}\s*\{{[^}}]*?)overflow\s*:\s*hidden([^}}]*\}})'
    match = re.search(style_pattern, html, re.IGNORECASE)
    if match:
        _ = match.group(0)  # noqa: F841  # documented in manifest
        replacement = match.group(1) + "overflow: visible" + match.group(2)
        patched = html[:match.start()] + replacement + html[match.end():]
        return patched, _make_manifest(
            finding, "CSS_PATCH", selector,
            _OVERFLOW_HIDDEN, _OVERFLOW_VISIBLE,
            "Changed overflow:hidden to overflow:visible in stylesheet.",
        )

    # Fallback: wrap in a container with overflow:visible
    wrapper = f'<div style="overflow:visible">{html}</div>'
    return wrapper, _make_manifest(
        finding, "CSS_PATCH", selector,
        html, "overflow:visible wrapper applied",
        "Applied overflow:visible wrapper as fallback.",
    )


# ---------------------------------------------------------------------------
# Patch: missing image dimensions
# ---------------------------------------------------------------------------

def patch_missing_image_dimensions(
    html: str,
    finding: dict[str, Any],
) -> tuple[str, PrototypeManifest]:
    """Add width and height attributes to <img> tags missing them."""
    selector = finding.get("selector", "")

    def _add_dims(m: re.Match) -> str:
        tag = m.group(0)
        if "width=" in tag and "height=" in tag:
            return tag  # already has dimensions
        src_match = re.search(r'src=["\']([^"\']+)["\']', tag)
        _ = src_match.group(1) if src_match else "unknown"
        new_tag = tag[:-1] + ' width="800" height="600" loading="lazy">'
        return new_tag

    if selector:
        # Target specific image
        id_attr = selector.lstrip("#")
        pattern = rf'<img([^>]*id=["\']{re.escape(id_attr)}["\'][^>]*)>'
        match = re.search(pattern, html)
        if match:
            original = match.group(0)
            patched_tag = _add_dims(match)
            patched = html[:match.start()] + patched_tag + html[match.end():]
            return patched, _make_manifest(
                finding, "HTML_ATTRIBUTE_PATCH", selector,
                original, patched_tag,
                "Added width/height/loading attributes to prevent layout shift.",
            )

    # Patch all images missing dimensions — two-pass to avoid variable-width lookbehind
    def _add_dims_all(m: re.Match) -> str:
        tag = m.group(0)
        if "width=" in tag and "height=" in tag:
            return tag
        new_tag = tag[:-1] + ' width="800" height="600" loading="lazy">'
        return new_tag

    patched = re.sub(r'<img[^>]*>', _add_dims_all, html)
    if patched != html:
        return patched, _make_manifest(
            finding, "HTML_ATTRIBUTE_PATCH", selector or "img",
            "<img>", "<img width='800' height='600' loading='lazy'>",
            "Added width/height/loading to all images missing dimensions.",
        )

    return html, _make_manifest(
        finding, "HTML_ATTRIBUTE_PATCH", selector or "img",
        html, html,
        "All images already have dimensions.",
    )


# ---------------------------------------------------------------------------
# Patch: poor contrast
# ---------------------------------------------------------------------------

# Map of common low-contrast colors to WCAG AA-compliant replacements
_CONTRAST_FIXES: dict[str, str] = {
    "#999": "#1a1a2e",
    "#999999": "#1a1a2e",
    "#aaa": "#1a1a2e",
    "#aaaaaa": "#1a1a2e",
    "#bbb": "#333333",
    "#bbbbbb": "#333333",
    "#ccc": "#1a1a2e",
    "#cccccc": "#1a1a2e",
    "#777": "#1a1a2e",
    "#777777": "#1a1a2e",
    "#888": "#1a1a2e",
    "#888888": "#1a1a2e",
    "grey": "#1a1a2e",
    "gray": "#1a1a2e",
    "lightgrey": "#1a1a2e",
    "lightgray": "#1a1a2e",
}


def patch_poor_contrast(
    css: str,
    finding: dict[str, Any],
) -> tuple[str, PrototypeManifest]:
    """Replace low-contrast color values with WCAG AA-compliant ones."""
    selector = finding.get("selector", "")
    original_css = css
    patched = css

    before_val = ""
    after_val = ""

    for low, good in _CONTRAST_FIXES.items():
        pattern = rf'(color\s*:\s*)({re.escape(low)})(\s*[;}}])'
        match = re.search(pattern, css, re.IGNORECASE)
        if match:
            before_val = match.group(0)
            after_val = f"{match.group(1)}{good}{match.group(3)}"
            patched = css.replace(before_val, after_val, 1)
            break

    if patched != original_css:
        return patched, _make_manifest(
            finding, "CSS_PATCH", selector,
            before_val, after_val,
            "Improved text color contrast to meet WCAG AA (4.5:1 minimum).",
        )

    # Fallback: append a contrast override
    if selector:
        override = f"\n{selector} {{ color: #1a1a2e; }}\n"
        return css + override, _make_manifest(
            finding, "CSS_PATCH", selector,
            "no color declaration found",
            f"{selector} {{ color: #1a1a2e; }}",
            "Appended contrast-fixing color declaration.",
        )

    return css, _make_manifest(
        finding, "CSS_PATCH", selector,
        css, css,
        "No low-contrast color values found to patch.",
    )


# ---------------------------------------------------------------------------
# Patch: broken internal URL
# ---------------------------------------------------------------------------

def patch_broken_internal_url(
    html: str,
    finding: dict[str, Any],
) -> tuple[str, PrototypeManifest]:
    """Fix a broken internal link by replacing the href value."""
    selector = finding.get("selector", "")
    broken_url = finding.get("broken_url", "")
    fixed_url = finding.get("fixed_url", "")

    if not broken_url or not fixed_url:
        return html, _make_manifest(
            finding, "HTML_ATTRIBUTE_PATCH", selector,
            html, html,
            "No broken_url/fixed_url provided in finding.",
        )

    # Escape special regex characters in the URL
    escaped_broken = re.escape(broken_url)
    pattern = rf'(href=["\'])({escaped_broken})(["\'])'
    replacement = rf'\1{fixed_url}\3'

    patched = re.sub(pattern, replacement, html, count=1)

    if patched != html:
        return patched, _make_manifest(
            finding, "HTML_ATTRIBUTE_PATCH", selector,
            f'href="{broken_url}"',
            f'href="{fixed_url}"',
            f"Fixed broken internal URL from {broken_url} to {fixed_url}.",
        )

    return html, _make_manifest(
        finding, "HTML_ATTRIBUTE_PATCH", selector,
        html, html,
        f"URL {broken_url} not found in HTML content.",
    )
