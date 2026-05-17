"""
Pruebas de las 3 agregaciones avanzadas del dashboard.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6.QtCore", reason="PySide6 no instalado")

from shakevision.services.data_models import Earthquake, PagerLevel  # noqa: E402
from shakevision.ui.dashboard_view import (  # noqa: E402
    aggregate_pager_distribution,
    build_48h_trend,
    build_depth_magnitude_scatter,
    build_payload,
)


def _q(mag: float, depth: float = 10.0,
       ts: float = 1700000000.0,
       pager: PagerLevel | None = None) -> Earthquake:
    return Earthquake(
        id=f"t-{mag}-{ts}", timestamp_unix=ts,
        longitude=0.0, latitude=0.0,
        depth_km=depth, magnitude=mag,
        place="X", url="", pager=pager,
    )


# ============================================================
# aggregate_pager_distribution
# ============================================================
def test_pager_returns_4_levels_always() -> None:
    out = aggregate_pager_distribution([])
    assert len(out) == 4
    assert all(b["count"] == 0 for b in out)
    assert {b["level"] for b in out} == {"green", "yellow", "orange", "red"}


def test_pager_counts_correctly() -> None:
    quakes = [
        _q(5.0, pager=PagerLevel.GREEN),
        _q(5.0, pager=PagerLevel.GREEN),
        _q(6.0, pager=PagerLevel.YELLOW),
        _q(7.0, pager=PagerLevel.ORANGE),
        _q(4.0),                       # sin PAGER → no cuenta
    ]
    out = aggregate_pager_distribution(quakes)
    counts = {b["level"]: b["count"] for b in out}
    assert counts == {"green": 2, "yellow": 1, "orange": 1, "red": 0}
    # cada nivel debe traer color hex
    for b in out:
        assert b["color"].startswith("#")


# ============================================================
# build_48h_trend
# ============================================================
def test_trend_returns_48_buckets() -> None:
    out = build_48h_trend([], now_unix=1_000_000_000.0)
    assert len(out) == 48
    assert all(b["count"] == 0 for b in out)


def test_trend_assigns_event_to_correct_bucket() -> None:
    now = 1_000_000_000.0
    quakes = [
        _q(5.0, ts=now - 3600),                 # último bucket
        _q(6.0, ts=now - 3600 + 60),            # mismo bucket
        _q(4.0, ts=now - 30 * 3600),            # 30 h atrás
    ]
    out = build_48h_trend(quakes, now_unix=now)
    # El bucket "más reciente" es el último
    assert out[-1]["count"] == 2
    assert out[-1]["max_mag"] == 6.0
    # Ts en milisegundos para ECharts
    assert out[-1]["ts"] > 1_000_000_000_000


def test_trend_ignores_events_outside_window() -> None:
    now = 1_000_000_000.0
    far_future = _q(5.0, ts=now + 1000)
    far_past = _q(5.0, ts=now - 100 * 3600)
    out = build_48h_trend([far_future, far_past], now_unix=now)
    assert sum(b["count"] for b in out) == 0


# ============================================================
# build_depth_magnitude_scatter
# ============================================================
def test_scatter_returns_one_point_per_event() -> None:
    now = 1_000_000_000.0
    quakes = [
        _q(5.0, depth=12, ts=now - 3600),
        _q(6.5, depth=180, ts=now - 7200, pager=PagerLevel.YELLOW),
    ]
    out = build_depth_magnitude_scatter(quakes, now_unix=now)
    assert len(out) == 2
    assert out[0]["depth"] == 12.0
    assert out[1]["pager"] == "yellow"


def test_scatter_filters_by_window() -> None:
    now = 1_000_000_000.0
    out = build_depth_magnitude_scatter(
        [_q(5.0, ts=now - 30 * 3600)], now_unix=now,
    )
    assert out == []


# ============================================================
# build_payload incluye los campos avanzados
# ============================================================
def test_build_payload_includes_advanced_keys() -> None:
    payload = build_payload([_q(5.0)], now_unix=1700000000.0)
    for key in ("pager_distribution", "trend_48h", "depth_mag_scatter"):
        assert key in payload, f"falta {key} en build_payload"
    assert isinstance(payload["pager_distribution"], list)
    assert isinstance(payload["trend_48h"], list)
    assert isinstance(payload["depth_mag_scatter"], list)
