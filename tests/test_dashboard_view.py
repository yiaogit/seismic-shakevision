"""
Pruebas de las funciones de agregación del dashboard y de la presencia
de los recursos web. La parte Qt se omite si PySide6 no está instalado.
"""

from __future__ import annotations

import pytest

# El módulo dashboard_view importa PySide6 en cabecera; saltar si no está
pytest.importorskip("PySide6.QtCore", reason="PySide6 no instalado")

from shakevision.services.data_models import Earthquake  # noqa: E402
from shakevision.ui.dashboard_view import (  # noqa: E402
    WEB_DASHBOARD_DIR,
    aggregate_by_country,
    aggregate_depth_buckets,
    aggregate_magnitude_buckets,
    build_payload,
    build_timeline_24h,
    extract_country,
)


# ============================================================
# Helper para crear sismos rápidamente
# ============================================================
def _q(magnitude: float, depth: float = 10.0, place: str = "X, Country",
       ts: float = 1700000000.0) -> Earthquake:
    return Earthquake(
        id=f"test-{magnitude}-{ts}",
        timestamp_unix=ts,
        longitude=0.0, latitude=0.0,
        depth_km=depth, magnitude=magnitude,
        place=place, url="",
    )


# ============================================================
# extract_country
# ============================================================
def test_extract_country_takes_last_segment() -> None:
    assert extract_country("26 km W of Anchorage, Alaska") == "United States"
    assert extract_country("Sumatra, Indonesia") == "Indonesia"
    assert extract_country("16 km E of Pijijiapan, Mexico") == "Mexico"


def test_extract_country_us_states_canonical() -> None:
    for state in ("Alaska", "California", "Hawaii", "Puerto Rico"):
        assert extract_country(f"loc, {state}") == "United States"


def test_extract_country_open_ocean_normalized() -> None:
    assert extract_country("X, Mid-Atlantic Ridge") == "Open Ocean"


def test_extract_country_empty_or_invalid() -> None:
    assert extract_country("") == "Desconocido"
    assert extract_country(",   ") == "Desconocido"


def test_extract_country_no_comma_returns_whole_string() -> None:
    assert extract_country("Hindu Kush region") == "Hindu Kush region"


# ============================================================
# aggregate_by_country
# ============================================================
def test_aggregate_by_country_returns_top_n_sorted() -> None:
    quakes = [
        _q(4.0, place="x, Indonesia"),
        _q(4.0, place="y, Indonesia"),
        _q(4.0, place="z, Japan"),
        _q(4.0, place="w, Chile"),
        _q(4.0, place="a, Indonesia"),
    ]
    out = aggregate_by_country(quakes, top_n=2)
    # Top_n=2 → devuelve 2 filas. Indonesia gana sin empate; el
    # segundo puesto es ambiguo (Japan vs Chile empatan a 1) y la API
    # solo garantiza el primero.
    assert len(out) == 2
    assert out[0] == {"name": "Indonesia", "count": 3}
    assert out[1]["count"] == 1
    assert out[1]["name"] in ("Japan", "Chile")


def test_aggregate_by_country_empty_returns_empty() -> None:
    assert aggregate_by_country([]) == []


# ============================================================
# aggregate_magnitude_buckets
# ============================================================
def test_magnitude_buckets_cover_known_examples() -> None:
    quakes = [
        _q(2.5),  # <3
        _q(3.0),  # 3-4.5
        _q(4.4),  # 3-4.5
        _q(4.5),  # 4.5-6
        _q(5.9),  # 4.5-6
        _q(6.0),  # 6-7.5
        _q(7.5),  # ≥7.5
        _q(8.2),  # ≥7.5
    ]
    out = aggregate_magnitude_buckets(quakes)
    counts = {b["label"]: b["count"] for b in out}
    assert counts == {
        "<3.0": 1, "3.0–4.5": 2, "4.5–6.0": 2, "6.0–7.5": 1, "≥7.5": 2,
    }
    # Cada bucket trae color
    for b in out:
        assert b["color"].startswith("#")


def test_magnitude_buckets_empty_returns_zero_counts() -> None:
    out = aggregate_magnitude_buckets([])
    assert sum(b["count"] for b in out) == 0
    assert len(out) == 5


# ============================================================
# aggregate_depth_buckets
# ============================================================
def test_depth_buckets_cover_known_examples() -> None:
    quakes = [
        _q(4.0, depth=5.0),    # 0-10
        _q(4.0, depth=10.0),   # 10-35
        _q(4.0, depth=34.9),   # 10-35
        _q(4.0, depth=70.0),   # 70-150
        _q(4.0, depth=300.0),  # ≥300
        _q(4.0, depth=999.0),  # ≥300
    ]
    out = aggregate_depth_buckets(quakes)
    counts = {b["label"]: b["count"] for b in out}
    assert counts["0–10"] == 1
    assert counts["10–35"] == 2
    assert counts["70–150"] == 1
    assert counts["≥300"] == 2


# ============================================================
# build_timeline_24h
# ============================================================
def test_timeline_filters_by_time_and_magnitude() -> None:
    now = 1_000_000_000.0
    quakes = [
        _q(2.0, ts=now - 3600,        place="hace 1h"),   # mag baja → fuera
        _q(3.0, ts=now - 3600,        place="hace 1h"),   # ok
        _q(3.0, ts=now - 25 * 3600,   place="hace 25h"),  # fuera por tiempo
        _q(5.0, ts=now - 100,         place="ahora"),
    ]
    out = build_timeline_24h(quakes, now_unix=now, min_magnitude=2.5)
    assert len(out) == 2
    # Orden cronológico ascendente
    assert out[0]["ts"] < out[1]["ts"]
    assert all("mag" in r and "place" in r for r in out)


# ============================================================
# build_payload
# ============================================================
def test_build_payload_returns_all_keys() -> None:
    now = 1_000_000_000.0
    quakes = [
        _q(5.4, depth=10, place="loc, Indonesia",  ts=now - 3600),
        _q(3.1, depth=20, place="loc, Mexico",     ts=now - 7200),
        _q(6.2, depth=50, place="loc, Chile",      ts=now - 600),
    ]
    payload = build_payload(quakes, now_unix=now)
    expected = {
        # i18n + zona horaria del usuario (inyectados desde Phase A i18n)
        "lang", "i18n", "timezone",
        "period_seconds",
        "count_24h", "max_magnitude", "latest_iso", "country_count",
        "country_top10", "magnitude_buckets", "depth_buckets",
        "timeline_mode", "timeline_24h", "timeline_density",
        "pager_distribution", "pager_region", "region_options",
        "period_histogram",
        "trend_48h", "depth_mag_scatter",
        "station_summary",
        # v0.8.3: gráficas nuevas del panel (en vivo + análisis)
        "epicenters", "mag_time", "event_rate", "pro",
    }
    assert set(payload.keys()) == expected
    assert payload["count_24h"] == 3
    assert payload["max_magnitude"] == 6.2
    assert payload["country_count"] == 3
    assert isinstance(payload["latest_iso"], str)


def test_build_payload_handles_empty() -> None:
    payload = build_payload([], now_unix=1_000_000_000.0)
    assert payload["count_24h"] == 0
    assert payload["max_magnitude"] is None
    assert payload["latest_iso"] is None
    assert payload["country_count"] == 0
    assert payload["country_top10"] == []
    # Sin estaciones inyectadas el resumen también está vacío
    assert payload["station_summary"]["total"] == 0


# ============================================================
# Periodo aplicado a TODAS las agregaciones
# ============================================================
def test_build_payload_respects_period_window() -> None:
    """Con period_seconds=3600 solo entran sismos de la última hora."""

    from shakevision.ui.dashboard_view import build_payload as _bp

    now = 1_000_000_000.0
    quakes = [
        _q(5.0, ts=now - 600,       place="x, A"),    # dentro
        _q(4.0, ts=now - 5_000,     place="x, B"),    # fuera (~83 min)
        _q(6.0, ts=now - 60,        place="x, A"),    # dentro
    ]
    payload = _bp(quakes, now_unix=now, period_seconds=3600)
    assert payload["count_24h"] == 2          # campo histórico, mide ventana
    assert payload["max_magnitude"] == 6.0
    # Los buckets también deben respetar el periodo
    mag_total = sum(b["count"] for b in payload["magnitude_buckets"])
    assert mag_total == 2


def test_build_payload_timeline_capped_at_24h() -> None:
    """Para periodos > 24 h se usa la vista de densidad (burbujas)
    y ``timeline_24h`` queda vacío. La cota efectiva la asegura el
    cambio de modo (``timeline_mode == "density"``)."""

    from shakevision.ui.dashboard_view import build_payload as _bp

    now = 1_000_000_000.0
    quakes = [
        _q(5.0, ts=now - 3 * 86400, place="x, A"),
        _q(5.0, ts=now - 100,       place="x, A"),
    ]
    payload = _bp(quakes, now_unix=now, period_seconds=7 * 86400)
    # Con period > 24 h el scatter queda vacío y la página dibuja
    # ``timeline_density`` en su lugar.
    assert payload["timeline_mode"] == "density"
    assert payload["timeline_24h"] == []
    # La vista de densidad sí debe traer las 2 burbujas (día 0 y día 3).
    assert len(payload["timeline_density"]) == 2


# ============================================================
# Resumen de estaciones para el KPI / filtro de fuente
# ============================================================
def test_station_summary_counts_by_provider() -> None:
    from shakevision.services.data_models import ShakeStation
    from shakevision.ui.dashboard_view import build_station_summary

    stations = [
        ShakeStation(network="AM", code="R001", latitude=0, longitude=0,
                     elevation_m=0, site_name="x", provider="shakenet"),
        ShakeStation(network="AM", code="R002", latitude=0, longitude=0,
                     elevation_m=0, site_name="x", provider="shakenet"),
        ShakeStation(network="IU", code="ANMO", latitude=0, longitude=0,
                     elevation_m=0, site_name="x", provider="usgs"),
    ]
    summary = build_station_summary(stations)
    assert summary == {"total": 3, "shakenet": 2, "usgs": 1}


def test_station_summary_handles_none() -> None:
    from shakevision.ui.dashboard_view import build_station_summary
    assert build_station_summary(None) == {"total": 0, "shakenet": 0, "usgs": 0}
    assert build_station_summary([]) == {"total": 0, "shakenet": 0, "usgs": 0}


def test_build_payload_includes_station_summary() -> None:
    from shakevision.services.data_models import ShakeStation
    from shakevision.ui.dashboard_view import build_payload as _bp

    stations = [
        ShakeStation(network="AM", code="R001", latitude=0, longitude=0,
                     elevation_m=0, site_name="x", provider="shakenet"),
        ShakeStation(network="IU", code="ANMO", latitude=0, longitude=0,
                     elevation_m=0, site_name="x", provider="usgs"),
    ]
    payload = _bp([], now_unix=1_000_000_000.0, stations=stations)
    assert payload["station_summary"]["total"] == 2
    assert payload["station_summary"]["shakenet"] == 1
    assert payload["station_summary"]["usgs"] == 1


# ============================================================
# Top 10 países con filtro mínimo de magnitud
# ============================================================
def test_aggregate_by_country_respects_min_magnitude() -> None:
    """M < 3 no debe contar para el Top 10 (regla de UI)."""

    quakes = [
        _q(2.0, place="x, Indonesia"),  # filtrado
        _q(2.5, place="x, Indonesia"),  # filtrado
        _q(3.1, place="x, Indonesia"),  # cuenta
        _q(4.0, place="x, Japan"),      # cuenta
    ]
    out = aggregate_by_country(quakes, top_n=10, min_magnitude=3.0)
    counts = {row["name"]: row["count"] for row in out}
    assert counts.get("Indonesia") == 1
    assert counts.get("Japan") == 1


def test_build_payload_top10_filters_micro_sismos() -> None:
    """build_payload aplica M≥3.0 al Top 10 por defecto."""

    from shakevision.ui.dashboard_view import build_payload as _bp
    now = 1_000_000_000.0
    quakes = [
        _q(2.0, ts=now - 100, place="x, Alaska"),
        _q(2.5, ts=now - 200, place="x, Alaska"),
        _q(2.0, ts=now - 300, place="x, Alaska"),
        _q(3.5, ts=now - 400, place="x, Japan"),
    ]
    p = _bp(quakes, now_unix=now, period_seconds=3600)
    countries = {row["name"]: row["count"] for row in p["country_top10"]}
    # Alaska/US no debería aparecer (todos sus sismos < 3.0)
    assert "United States" not in countries
    assert countries.get("Japan") == 1


# ============================================================
# Timeline density (vista de burbujas para 7d/30d)
# ============================================================
def test_build_payload_uses_density_timeline_above_24h() -> None:
    from shakevision.ui.dashboard_view import build_payload as _bp
    now = 1_000_000_000.0
    quakes = [_q(5.0, ts=now - 6*3600, place="x, Japan")]
    p = _bp(quakes, now_unix=now, period_seconds=7 * 86400)
    assert p["timeline_mode"] == "density"
    assert p["timeline_24h"] == []        # se llena el otro lado
    assert isinstance(p["timeline_density"], list)


def test_build_payload_uses_scatter_timeline_at_24h_or_less() -> None:
    from shakevision.ui.dashboard_view import build_payload as _bp
    now = 1_000_000_000.0
    quakes = [_q(4.0, ts=now - 60, place="x, Japan")]
    p = _bp(quakes, now_unix=now, period_seconds=3600)
    assert p["timeline_mode"] == "scatter"
    assert p["timeline_density"] == []


def test_build_timeline_density_aggregates_by_day() -> None:
    from shakevision.ui.dashboard_view import build_timeline_density
    now = 1_000_000_000.0
    quakes = [
        _q(5.0, ts=now - 1 * 3600),         # día 0
        _q(6.0, ts=now - 2 * 3600),         # día 0
        _q(4.0, ts=now - 25 * 3600),        # día 1
        _q(3.0, ts=now - 100 * 3600),       # fuera (4d, >3d window)
    ]
    out = build_timeline_density(
        quakes, now_unix=now, period_seconds=3 * 86400,
        min_magnitude=2.5,
    )
    # Esperamos burbujas para día 0 y día 1, no día 2 (no eventos), no día 4
    assert len(out) == 2
    # Día 0 (más reciente) debe tener count=2 y max_mag=6.0
    day0 = max(out, key=lambda d: d["ts"])
    assert day0["count"] == 2
    assert day0["max_mag"] == 6.0


# ============================================================
# Histograma adaptativo por periodo
# ============================================================
def test_period_histogram_chooses_bucket_by_period() -> None:
    from shakevision.ui.dashboard_view import build_period_buckets

    now = 1_000_000_000.0
    cases = [
        (3600,        "5 min",  12),
        (6 * 3600,    "30 min", 12),
        (24 * 3600,   "1 h",    24),
        (7 * 86400,   "1 día",   7),
        (30 * 86400,  "1 día",  30),
    ]
    for period, label, n_expected in cases:
        h = build_period_buckets([], now_unix=now, period_seconds=period)
        assert h["bucket_label"] == label, (period, label, h["bucket_label"])
        assert len(h["buckets"]) == n_expected, (period, len(h["buckets"]))


def test_period_histogram_assigns_event_to_correct_bucket() -> None:
    from shakevision.ui.dashboard_view import build_period_buckets

    now = 1_000_000_000.0
    quakes = [
        _q(5.0, ts=now - 100),           # último bucket (24h, bucket=1h)
        _q(6.0, ts=now - 200),           # último bucket
        _q(4.0, ts=now - 3 * 3600 - 60), # 3h-4h atrás (bucket #20 si n=24)
    ]
    h = build_period_buckets(quakes, now_unix=now, period_seconds=24 * 3600)
    total = sum(b["count"] for b in h["buckets"])
    assert total == 3
    # El último bucket (más reciente) tiene 2 eventos con max_mag=6.0
    assert h["buckets"][-1]["count"] == 2
    assert h["buckets"][-1]["max_mag"] == 6.0


# ============================================================
# PAGER con filtro de región + lista de regiones disponibles
# ============================================================
def test_pager_distribution_filters_by_region() -> None:
    from shakevision.services.data_models import PagerLevel
    from shakevision.ui.dashboard_view import aggregate_pager_distribution

    quakes = [
        Earthquake(id="1", timestamp_unix=0, longitude=0, latitude=0,
                   depth_km=0, magnitude=5, place="x, Japan",
                   url="", pager=PagerLevel.GREEN),
        Earthquake(id="2", timestamp_unix=0, longitude=0, latitude=0,
                   depth_km=0, magnitude=5, place="x, Japan",
                   url="", pager=PagerLevel.YELLOW),
        Earthquake(id="3", timestamp_unix=0, longitude=0, latitude=0,
                   depth_km=0, magnitude=5, place="x, Chile",
                   url="", pager=PagerLevel.GREEN),
    ]
    out = aggregate_pager_distribution(quakes, region="Japan")
    counts = {b["level"]: b["count"] for b in out}
    assert counts["green"] == 1
    assert counts["yellow"] == 1
    assert counts["orange"] == 0

    # Sin filtro → todos
    out_all = aggregate_pager_distribution(quakes, region="all")
    counts_all = {b["level"]: b["count"] for b in out_all}
    assert counts_all["green"] == 2


def test_list_regions_sorted_excludes_unknown() -> None:
    from shakevision.ui.dashboard_view import list_regions

    quakes = [
        _q(4.0, place="x, Japan"),
        _q(4.0, place="x, Indonesia"),
        _q(4.0, place="x, Japan"),
        _q(4.0, place=""),  # → Desconocido, debe excluirse
        _q(2.0, place="x, Tonga"),  # filtrado por magnitud
    ]
    out = list_regions(quakes, min_magnitude=3.0)
    assert out == ["Indonesia", "Japan"]


def test_build_payload_exposes_region_options_and_default() -> None:
    from shakevision.ui.dashboard_view import build_payload as _bp
    now = 1_000_000_000.0
    quakes = [
        _q(4.0, ts=now - 60, place="x, Japan"),
        _q(4.0, ts=now - 60, place="x, Chile"),
    ]
    p = _bp(quakes, now_unix=now, period_seconds=3600)
    assert p["pager_region"] == "all"
    assert "Japan" in p["region_options"]
    assert "Chile" in p["region_options"]


# ============================================================
# Recursos web presentes
# ============================================================
def test_web_dashboard_files_exist() -> None:
    assert WEB_DASHBOARD_DIR.is_dir()
    for name in ("index.html", "dashboard.js", "styles.css"):
        path = WEB_DASHBOARD_DIR / name
        assert path.is_file(), f"falta {name}"
        assert path.stat().st_size > 0


def test_index_html_has_chart_containers() -> None:
    html = (WEB_DASHBOARD_DIR / "index.html").read_text(encoding="utf-8")
    for chart_id in ("chart-countries", "chart-magnitude",
                     "chart-depth", "chart-timeline"):
        assert f'id="{chart_id}"' in html, f"falta contenedor {chart_id}"
    assert "echarts" in html.lower()
    assert "qwebchannel" in html.lower()


def test_dashboard_js_exposes_set_aggregations() -> None:
    js = (WEB_DASHBOARD_DIR / "dashboard.js").read_text(encoding="utf-8")
    assert "shakevisionDashboard" in js
    assert "setAggregations" in js
