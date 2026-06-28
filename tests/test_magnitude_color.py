"""Pruebas de ``processing.magnitude_color`` (puro, sin Qt)."""

from __future__ import annotations

from shakevision.processing.magnitude_color import (
    MAGNITUDE_SCALE,
    magnitude_color,
    magnitude_scale_legend,
)


def test_buckets_map_to_expected_colors() -> None:
    assert magnitude_color(1.0) == "#66bb6a"   # micro
    assert magnitude_color(3.5) == "#c0ca33"   # minor
    assert magnitude_color(4.9) == "#fbc02d"   # light
    assert magnitude_color(5.5) == "#fb8c00"   # moderate
    assert magnitude_color(6.4) == "#f4511e"   # strong
    assert magnitude_color(7.8) == "#c62828"   # major


def test_boundaries_are_inclusive_lower() -> None:
    assert magnitude_color(3.0) == "#c0ca33"
    assert magnitude_color(7.0) == "#c62828"
    assert magnitude_color(6.999) == "#f4511e"


def test_negative_uses_first_bucket() -> None:
    assert magnitude_color(-0.5) == "#66bb6a"


def test_nan_and_garbage_grey() -> None:
    assert magnitude_color(float("nan")) == "#9aa0a6"
    assert magnitude_color("oops") == "#9aa0a6"  # type: ignore[arg-type]


def test_legend_matches_scale() -> None:
    legend = magnitude_scale_legend()
    assert len(legend) == len(MAGNITUDE_SCALE)
    assert legend[0] == ("#66bb6a", "mag.scale.micro")
    assert all(c.startswith("#") and k.startswith("mag.scale.")
               for c, k in legend)
