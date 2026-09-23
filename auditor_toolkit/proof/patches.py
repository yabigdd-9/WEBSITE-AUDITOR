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

    # Try to extract the input tag to determine label text
    id_match = re.search(rf'id=["\']({re.escape(input_id)})["\']', html) if input_id else None
    placeholder_match = re.search(r'placeholder=["\']([^"\']+)["\']', html)
    _ = re.search(r'name=["\']([^"\']+)["\']', html)  # noqa: F841

    if id_match:
        label_text = placeholder_match.group(1) if placeholder_match else input_id.replace("-", " ").title()
        label_html = f'<label for="{input_id}">{label_text}</label>\n'
        # Insert label before the input
        pattern = rf'(<input[^>]*id=["\']{re.escape(input_id)}["\'][^>]*>)'
        replacement = label_html + r"\1"
        patched = re.sub(pattern, replacement, html, count=1)
        if patched != html:
            return patched, _make_manifest(
                finding, "FORM_LABEL_PATCH", selector,
                html[html.find(f'id="{input_id}"'):html.find(f'id="{input_id}"') + 50] if f'id="{input_id}"' in html else html,
                label_html + html,
                f"Added <label for='{input_id}'> for form accessibility.",
            )

    # Fallback: find any <input> without a preceding <label>
    input_match = re.search(r'<input([^>]*)>', html)
    if input_match:
        attrs = input_match.group(1)
        pid = re.search(r'id=["\']([^"\']+)["\']', attrs)
        ph = re.search(r'placeholder=["\']([^"\']+)["\']', attrs)
        pn = re.search(r'name=["\']([^"\']+)["\']', attrs)
        inp_id = pid.group(1) if pid else (pn.group(1) if pn else "field")
        label_text = ph.group(1) if ph else inp_id.replace("-", " ").title()
        label_html = f'<label for="{inp_id}">{label_text}</label>\n'
        patched = html[:input_match.start()] + label_html + html[input_match.start():]
        return patched, _make_manifest(
            finding, "FORM_LABEL_PATCH", selector or f"#{inp_id}",
            input_match.group(0),
            label_html + input_match.group(0),
            f"Added <label for='{inp_id}'> for form accessibility.",
        )

    return html, _make_manifest(
        finding, "FORM_LABEL_PATCH", selector,
        html, html,
        "No injectable <input> found; label patch not applicable.",
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
    before_inline = "overflow: hidden"
    after_inline = "overflow: visible"
    patched = html.replace("overflow: hidden", "overflow: visible", 1)

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
            "overflow: hidden", "overflow: visible",
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
