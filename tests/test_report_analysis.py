"""Pruebas del reporte de ANÁLISIS (estadístico).

A diferencia del reporte en vivo, esta ruta es **pura**: no importa
``shakevision.ui.dashboard_view`` (Qt), así que corre en el sandbox sin
libEGL. Verificamos:
  * Los renderers SVG estadísticos son seguros con poca data ("" ) y producen
    gráficas con data suficiente.
  * ``render(context={"mode": "analysis"})`` produce el layout de análisis
    (título, KPIs, SVGs, bloque de contexto, tabla) y NO el de monitoreo.
  * ``generate()`` escribe el fichero en modo análisis.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from shakevision.services.data_models import Earthquake
from shakevision.services.report import (
    ReportGenerator,
    _render_cross_section_svg,
    _render_energy_svg,
    _render_inter_event_svg,
    _render_mcb_svg,
    _render_spatial_svg,
    _render_stats_kpis,
)

_NOW = 1_700_000_000.0


@pytest.fixture(autouse=True)
def _english_locale():
    from shakevision.i18n import LocaleService

    prev = LocaleService.current_language()
    LocaleService.set_language("en")
    try:
        yield
    finally:
        LocaleService.set_language(prev)


def _catalog(n: int = 400) -> list[Earthquake]:
    """Catálogo sintético: 1 año, magnitudes ~GR, dos cúmulos espaciales."""

    rng = np.random.default_rng(11)
    times = _NOW - rng.uniform(0, 365 * 86400, n)
    mags = np.clip(2.5 + rng.exponential(0.5, n), 2.5, 8.0)
    half = n // 2
    lon = np.concatenate([rng.normal(-120, 1.0, half),
                          rng.normal(140, 1.0, n - half)])
    lat = np.concatenate([rng.normal(36, 1.0, half),
                          rng.normal(-5, 1.0, n - half)])
    depth = rng.uniform(0, 200, n)
    out = []
    for i in range(n):
        out.append(Earthquake(
            id=f"e{i}", timestamp_unix=float(times[i]),
            longitude=float(lon[i]), latitude=float(lat[i]),
            depth_km=float(depth[i]), magnitude=float(mags[i]),
            place="Region, Country", url="", pager=None))
    return out


def _ctx() -> dict:
    return {"mode": "analysis", "region": "US · United States",
            "from": _NOW - 365 * 86400, "to": _NOW, "min_mag": 3.0}


# ── Renderers individuales: seguros con poca data ──────────────────
def test_svgs_empty_on_tiny_input() -> None:
    tiny = _catalog(3)
    assert _render_energy_svg(tiny) == ""
    assert _render_mcb_svg(tiny) == ""
    assert _render_spatial_svg(tiny) == ""
    assert _render_inter_event_svg(tiny) == ""


def test_svgs_render_with_enough_data() -> None:
    cat = _catalog(400)
    assert "<polyline" in _render_energy_svg(cat)
    assert "<polyline" in _render_mcb_svg(cat)
    assert "<rect" in _render_spatial_svg(cat)
    assert "<circle" in _render_cross_section_svg(cat)
    assert "<rect" in _render_inter_event_svg(cat)


def test_stats_kpis_has_cards() -> None:
    out = _render_stats_kpis(_catalog(200), _ctx())
    assert out.count("class='pro-kpi'") >= 4
    assert "± " in out  # b ± err


def test_stats_kpis_empty_placeholder() -> None:
    assert "color:#71717a" in _render_stats_kpis([], _ctx())


# ── render() en modo análisis ──────────────────────────────────────
def test_render_analysis_layout() -> None:
    html = ReportGenerator().render(
        _catalog(400), station_label="—", version="0.8.0",
        now_unix=_NOW, context=_ctx())
    assert "<!DOCTYPE html>" in html
    # Título y secciones del layout de análisis (no el de monitoreo 24 h).
    assert "Seismic analysis" in html
    assert "Statistical analysis" in html
    assert "24 h" not in html  # no debe colarse el layout en vivo
    # Bloque de contexto + chips.
    assert "ctx-analysis" in html
    assert "United States" in html
    # Las gráficas estadísticas están presentes.
    for token in ("<svg", "<polyline", "<rect", "<circle", "pro-kpi",
                  "table class='events'"):
        assert token in html, f"falta: {token}"


def test_render_analysis_professional_sections() -> None:
    html = ReportGenerator().render(
        _catalog(400), station_label="—", version="0.8.0",
        now_unix=_NOW, context=_ctx())
    # Hallazgos (párrafo interpretativo auto-generado).
    assert "Findings" in html and "Gutenberg–Richter b =" in html
    # Procedencia + métodos + advertencias.
    assert "Methods &amp; data provenance" in html or "Methods" in html
    assert "Query parameters" in html
    assert "USGS ANSS ComCat" in html
    assert "maximum curvature" in html        # método Mc
    assert "warn-box" in html                 # caja de advertencias
    assert "Magnitude types are not verified" in html
    # Pies de figura.
    assert "fig-cap" in html
    # Tabla con coordenadas + ID de evento.
    assert "class='coord'" in html
    assert "class=\"evid\"" in html


def test_generate_analysis_writes_file(tmp_path: Path) -> None:
    out_path = tmp_path / "analisis.html"
    written = ReportGenerator().generate(
        quakes=_catalog(300), station_label="—", version="0.8.0",
        output_path=out_path, now_unix=_NOW, context=_ctx())
    assert written == out_path and out_path.exists()
    assert out_path.stat().st_size > 2000
