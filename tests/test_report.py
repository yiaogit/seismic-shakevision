"""
Pruebas del generador de reportes HTML.

Verificamos:
  * El HTML producido contiene todas las secciones esperadas.
  * Los renderers individuales son seguros con entradas vacías.
  * El escapado HTML evita inyección desde el campo "place".
  * generate() escribe un archivo no vacío.

Como el módulo importa de ``shakevision.ui.dashboard_view`` (que a su
vez requiere PySide6), saltamos toda la suite cuando PySide6 falta.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtCore", reason="PySide6 no instalado")

from shakevision.services.data_models import Earthquake, PagerLevel  # noqa: E402
from shakevision.services.report import (  # noqa: E402
    ReportGenerator,
    _humanize_window,
    _render_country_bars,
    _render_depth_bars,
    _render_event_table,
    _render_kpi_cards,
    _render_live_notes,
    _render_live_summary,
    _render_magnitude_bars,
    _render_timeline_svg,
)


# ============================================================
# Fixture: forzar locale español para todo el módulo
# ============================================================
# El reporte es i18n: en EN dice "No data", en ES "Sin datos".
# Las aserciones de este módulo están escritas con los strings
# castellanos (que es el idioma "humano" de referencia del producto),
# así que cambiamos el locale al inicio y lo restauramos al final.
@pytest.fixture(autouse=True)
def _spanish_locale():
    from shakevision.i18n import LocaleService

    prev = LocaleService.current_language()
    LocaleService.set_language("es")
    try:
        yield
    finally:
        LocaleService.set_language(prev)


# ============================================================
# Helper
# ============================================================
def _q(mag: float, depth: float = 10.0,
       place: str = "Test, Country",
       ts: float = 1700000000.0,
       pager: PagerLevel | None = None) -> Earthquake:
    return Earthquake(
        id=f"test-{mag}-{ts}", timestamp_unix=ts,
        longitude=0.0, latitude=0.0,
        depth_km=depth, magnitude=mag,
        place=place, url="", pager=pager,
    )


# ============================================================
# Renderers individuales
# ============================================================
def test_country_bars_empty_returns_placeholder() -> None:
    out = _render_country_bars([])
    assert "Sin datos" in out


def test_country_bars_includes_each_country() -> None:
    out = _render_country_bars([
        {"name": "Indonesia", "count": 14},
        {"name": "Japan",     "count": 11},
    ])
    assert "Indonesia" in out
    assert "Japan" in out
    assert "14" in out and "11" in out
    # Anchos relativos: Indonesia debe estar al 100 %, Japan ~78 %
    assert "100.0%" in out


def test_magnitude_bars_with_zero_counts_shows_placeholder() -> None:
    buckets = [{"label": "<3.0", "count": 0, "color": "#000"}]
    assert "Sin sismos" in _render_magnitude_bars(buckets)


def test_depth_bars_with_zero_counts_shows_placeholder() -> None:
    buckets = [{"label": "0-10", "count": 0}]
    assert "Sin sismos" in _render_depth_bars(buckets)


def test_event_table_empty_returns_placeholder() -> None:
    out = _render_event_table([])
    assert "Sin eventos" in out


def test_event_table_renders_pager_class() -> None:
    quake = _q(5.5, place="Anchorage, Alaska", pager=PagerLevel.YELLOW)
    out = _render_event_table([quake], min_mag=3.0)
    assert "pager-yellow" in out
    assert "YELLOW" in out
    assert "M 5.5" in out


def test_event_table_escapes_html_in_place() -> None:
    """El campo 'place' jamás debe inyectar HTML literal."""

    quake = _q(5.5, place="<script>bad</script>")
    out = _render_event_table([quake])
    assert "<script>bad</script>" not in out
    assert "&lt;script&gt;" in out


def test_kpi_cards_includes_four_cards() -> None:
    out = _render_kpi_cards([_q(4.0)], countries=[])
    # Cuatro divs con clase kpi-card
    assert out.count('class="kpi-card"') == 4


def test_timeline_svg_with_events_contains_circles() -> None:
    events = [
        {"ts": 1_000_000_000.0, "mag": 4.0, "place": "x"},
        {"ts": 1_000_001_000.0, "mag": 6.5, "place": "y"},
    ]
    out = _render_timeline_svg(events, now=1_000_002_000.0)
    assert "<svg" in out
    assert out.count("<circle") == 2


def test_timeline_svg_empty_returns_placeholder() -> None:
    out = _render_timeline_svg([], now=0.0)
    assert "Sin eventos" in out


# ============================================================
# Reporte EN VIVO: resumen situacional + notas (rutas puras)
# ============================================================
def test_humanize_window() -> None:
    assert _humanize_window(24 * 3600) == "1 d"
    assert _humanize_window(7 * 86400) == "7 d"
    assert _humanize_window(6 * 3600) == "6 h"


def test_live_summary_empty() -> None:
    out = _render_live_summary([], [], 86400, now=1700000000.0)
    assert "findings" in out
    # "Sin sismos registrados…"
    assert "Sin sismos" in out


def test_live_summary_with_events() -> None:
    now = 1700000000.0
    quakes = [_q(6.4, place="Santiago, Chile", ts=now - 1800),
              _q(3.2, place="Tokyo, Japan", ts=now - 3600)]
    countries = [{"name": "Chile", "count": 5}]
    out = _render_live_summary(quakes, countries, 86400, now=now)
    assert "M6.4" in out            # mayor evento
    assert "Santiago, Chile" in out
    assert "Chile" in out           # región más activa
    assert "significativos" in out  # M≥4.5


def test_live_notes_has_provenance_and_caveats() -> None:
    out = _render_live_notes(1700000000.0, 86400, station_label="AM.MOCK")
    assert "warn-box" in out                  # advertencia de datos preliminares
    assert "preliminares" in out
    assert "params-table" in out              # procedencia
    assert "AM.MOCK" in out
    # El monitoreo en vivo ya no incluye la capa estadística pro.
    assert "methods-list" not in out


# ============================================================
# ReportGenerator.generate (integración)
# ============================================================
def test_generate_writes_html_file_with_required_sections(tmp_path: Path) -> None:
    quakes = [
        _q(5.4, place="Anchorage, Alaska", pager=PagerLevel.YELLOW,
           ts=1700000000 - 3600),
        _q(3.1, place="Sumatra, Indonesia", ts=1700000000 - 7200),
        _q(6.2, place="Santiago, Chile", pager=PagerLevel.ORANGE,
           ts=1700000000 - 600),
    ]
    out_path = tmp_path / "reporte.html"
    gen = ReportGenerator()
    written = gen.generate(
        quakes=quakes,
        station_label="AM.MOCK",
        version="0.1.0",
        output_path=out_path,
        now_unix=1700000000.0,
    )
    assert written == out_path
    assert out_path.exists()
    html = out_path.read_text(encoding="utf-8")

    # Estructura mínima
    assert "<!DOCTYPE html>" in html
    assert "<style>" in html
    assert "SeismicGuard" in html
    assert "AM.MOCK" in html
    assert "v0.1.0" in html

    # Secciones clave
    for section_id in (
        "Top países / regiones",
        "Distribución de magnitud",
        "Distribución de profundidad",
        "Línea temporal últimas 24",
        "Eventos significativos",
    ):
        assert section_id in html, f"falta sección: {section_id}"

    # Que aparezcan los lugares de los sismos significativos
    assert "Anchorage" in html or "United States" in html
    assert "Indonesia" in html
    assert "Santiago" in html or "Chile" in html


def test_generate_creates_parent_directories(tmp_path: Path) -> None:
    """Si la ruta de salida está en un subdirectorio que no existe, se crea."""

    nested = tmp_path / "subdir" / "deeper" / "out.html"
    gen = ReportGenerator()
    gen.generate(quakes=[], station_label="—", version="0",
                 output_path=nested)
    assert nested.exists()
