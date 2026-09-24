"""Tests for proof diff generation."""

from types import SimpleNamespace

from auditor_toolkit.proof.render import diff as diff_module
from auditor_toolkit.proof.render.diff import generate_diff


def test_generate_diff_returns_dict():
    result = generate_diff(before_path="", after_path="", output_dir="/tmp")
    assert isinstance(result, dict)


def test_generate_diff_uses_pixel_threshold_and_highlights_without_pillow(
    tmp_path, monkeypatch
):
    drawn_points = []

    class PixelBuffer:
        width = 1
        height = 1

        def load(self):
            return self

        def __getitem__(self, point):
            return 255

    class Canvas:
        size = (1, 1)

        def __init__(self, mode="RGB"):
            self.mode = mode

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def convert(self, mode):
            return PixelBuffer() if mode == "L" else Canvas(mode)

        def resize(self, size):
            self.size = size
            return self

        def copy(self):
            return Canvas(self.mode)

        def save(self, path):
            drawn_points.append(("saved", path))

    class Draw:
        def __init__(self, _canvas):
            pass

        def point(self, point, fill):
            drawn_points.append((point, fill))

    class Difference:
        def convert(self, _mode):
            return PixelBuffer()

    fake_image = SimpleNamespace(
        open=lambda _path: Canvas(),
        new=lambda *_args: Canvas("RGBA"),
        alpha_composite=lambda _before, overlay: overlay,
    )
    monkeypatch.setattr(diff_module, "HAS_PILLOW", True)
    monkeypatch.setattr(diff_module, "Image", fake_image, raising=False)
    monkeypatch.setattr(
        diff_module,
        "ImageChops",
        SimpleNamespace(difference=lambda *_: Difference()),
        raising=False,
    )
    monkeypatch.setattr(diff_module, "ImageDraw", SimpleNamespace(Draw=Draw), raising=False)

    result = generate_diff("before.png", "after.png", output_dir=str(tmp_path))

    assert result["diff_percent"] == 100.0
    assert result["diff_path"].endswith(".png")
    assert ((0, 0), (255, 0, 0, 128)) in drawn_points
