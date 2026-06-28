"""Pruebas de los bloques de análisis profesional del reporte (SVG/HTML puro)."""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("PySide6.QtCore", reason="report importa i18n (QSettings)")

from shakevision.services import report as R              # noqa: E402
from shakevision.services.data_models import Earthquake   # noqa: E402


def _catalog(n: int = 800, b: float = 1.0, seed: int = 1):
    rng = np.random.default_rng(seed)
    mags = 2.0 + rng.exponential(1.0 / (b * np.log(10)), n)
    t0 = 1_700_000_000.0
    return [
        Earthquake(
            id=f"e{i}", timestamp_unix=t0 + i * 3600,
            longitude=139.0 + rng.uniform(-2, 2),
            latitude=35.0 + rng.uniform(-2, 2),
            depth_km=float(abs(rng.normal(40, 30))),
            magnitude=float(round(m, 1)), place="Tokyo, Japan", url="")
        for i, m in enumerate(mags)
    ]


def test_pro_summary_has_kpis() -> None:
    s = R._render_pro_summary(_catalog())
    assert "pro-kpis" in s
    assert s.count("pro-kpi'") >= 5      # N, b, Mc, rango, energía
    assert "b" in s


def test_pro_summary_empty_is_graceful() -> None:
    assert R._render_pro_summary([]).startswith("<p")


def test_gr_svg_wellformed() -> None:
    gr = R._render_gr_svg(_catalog())
    assert gr.startswith("<svg") and gr.endswith("</svg>")
    assert "circle" in gr             # puntos de la FMD
    assert "stroke-dasharray" in gr   # recta de ajuste b


def test_gr_svg_empty_for_small_sample() -> None:
    assert R._render_gr_svg(_catalog(n=5)) == ""


def test_depth_hist_svg_has_bars() -> None:
    dh = R._render_depth_hist_svg(_catalog())
    assert dh.startswith("<svg")
    assert dh.count("<rect") >= 3
