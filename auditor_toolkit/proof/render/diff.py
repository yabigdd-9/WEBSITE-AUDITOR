"""Pixel-level visual diff between before and after screenshots.

Uses Pillow for image comparison and produces a side-by-side diff image
highlighting changed pixels.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone

try:
    from PIL import Image, ImageChops, ImageDraw
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False


def generate_diff(
    before_path: str,
    after_path: str,
    output_dir: str | None = None,
    threshold: int = 30,
    highlight_color: tuple[int, int, int] = (255, 0, 0),
) -> dict[str, str | float]:
    """Generate a visual diff between before and after screenshots.

    Returns a dict with:
    - diff_path: path to the diff image
    - diff_percent: percentage of pixels that differ
    """
    if not HAS_PILLOW:
        return {
            "diff_path": "",
            "diff_percent": 0.0,
            "error": "Pillow not installed (pip install Pillow)",
        }

    output_dir = output_dir or tempfile.mkdtemp(prefix="website-auditor-proof-")
    os.makedirs(output_dir, exist_ok=True)

    with Image.open(before_path) as source_before:
        before_img = source_before.convert("RGB")
    with Image.open(after_path) as source_after:
        after_img = source_after.convert("RGB")

    # Resize after to match before dimensions if needed
    if before_img.size != after_img.size:
        after_img = after_img.resize(before_img.size)

    # Pixel-by-pixel comparison
    diff_img = ImageChops.difference(before_img, after_img)

    # Convert to grayscale for threshold comparison
    gray_diff = diff_img.convert("L")

    total_pixels = gray_diff.width * gray_diff.height
    pixels = gray_diff.load()
    diff_pixels = _count_different_pixels(
        pixels, gray_diff.width, gray_diff.height, threshold
    )
    diff_percent = diff_pixels / total_pixels * 100 if total_pixels else 0.0

    # Create annotated diff image with red highlights
    annotated = before_img.copy()
    _ = ImageDraw.Draw(annotated)  # noqa: F841
    overlay = Image.new("RGBA", before_img.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)

    _draw_highlights(
        overlay_draw,
        pixels,
        gray_diff.width,
        gray_diff.height,
        threshold,
        highlight_color,
    )

    annotated = annotated.convert("RGBA")
    annotated = Image.alpha_composite(annotated, overlay)
    annotated = annotated.convert("RGB")

    # Save
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    diff_path = os.path.join(output_dir, f"diff_{ts}.png")
    annotated.save(diff_path)

    return {
        "diff_path": diff_path,
        "diff_percent": round(diff_percent, 2),
    }


def _count_different_pixels(pixels, width: int, height: int, threshold: int) -> int:
    return sum(
        1
        for y in range(height)
        for x in range(width)
        if pixels[x, y] > threshold
    )


def _draw_highlights(draw, pixels, width, height, threshold, highlight_color) -> None:
    color = (*highlight_color, 128)
    for y in range(height):
        for x in range(width):
            if pixels[x, y] > threshold:
                draw.point((x, y), fill=color)
