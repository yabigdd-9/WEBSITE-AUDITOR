"""Pixel-level visual diff between before and after screenshots.

Uses Pillow for image comparison and produces a side-by-side diff image
highlighting changed pixels.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

try:
    from PIL import Image, ImageChops, ImageDraw
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False


def generate_diff(
    before_path: str,
    after_path: str,
    output_dir: str = "/tmp/proof_capture",
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

    os.makedirs(output_dir, exist_ok=True)

    before_img = Image.open(before_path).convert("RGB")
    after_img = Image.open(after_path).convert("RGB")

    # Resize after to match before dimensions if needed
    if before_img.size != after_img.size:
        after_img = after_img.resize(before_img.size)

    # Pixel-by-pixel comparison
    diff_img = ImageChops.difference(before_img, after_img)

    # Convert to grayscale for threshold comparison
    gray_diff = diff_img.convert("L")

    # Count differing pixels
    total_pixels = gray_diff.width * gray_diff.height
    diff_pixels = 0

    pixels = gray_diff.load()
    for y in range(gray_diff.height):
        for x in range(gray_diff.width):
            if pixels[x, y] > threshold:
                diff_pixels += 1

    diff_percent = (diff_pixels / total_pixels * 100) if total_pixels > 0 else 0.0

    # Create annotated diff image with red highlights
    annotated = before_img.copy()
    _ = ImageDraw.Draw(annotated)  # noqa: F841
    overlay = Image.new("RGBA", before_img.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)

    for y in range(gray_diff.height):
        for x in range(gray_diff.width):
            if pixels[x, y] > threshold:
                overlay_draw.point((x, y), fill=(*highlight_color, 128))

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
