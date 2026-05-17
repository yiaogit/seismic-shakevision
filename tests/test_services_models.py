"""
Pruebas de los dataclasses ``Earthquake`` / ``ShakeStation`` y del enum
``PagerLevel``. Sin Qt, sin red.
"""

from __future__ import annotations

import time

from shakevision.services.data_models import (
    PAGER_VISUAL,
    Earthquake,
    PagerLevel,
    ShakeStation,
)


# ============================================================
# PagerLevel
# ============================================================
def test_pager_level_parse_known_values() -> None:
    assert PagerLevel.parse("green") is PagerLevel.GREEN
    assert PagerLevel.parse("YELLOW") is PagerLevel.YELLOW
    assert PagerLevel.parse("Orange") is PagerLevel.ORANGE
    assert PagerLevel.parse("red") is PagerLevel.RED


def test_pager_level_parse_unknown_returns_none() -> None:
    assert PagerLevel.parse(None) is None
    assert PagerLevel.parse("") is None
    assert PagerLevel.parse("blue") is None


def test_pager_visual_table_covers_all_levels() -> None:
    """Cada nivel debe tener un color hex y un radio asociado."""

    for level in PagerLevel:
        assert level in PAGER_VISUAL
        color, radius = PAGER_VISUAL[level]
        assert color.startswith("#") and len(color) == 7
        assert 0.0 < radius < 5.0


# ============================================================
# Earthquake
# ============================================================
def _make_quake(magnitude: float, age_h: float = 0.0) -> Earthquake:
    return Earthquake(
        id=f"test-{magnitude}",
        timestamp_unix=time.time() - age_h * 3600,
        longitude=0.0,
        latitude=0.0,
        depth_km=10.0,
        magnitude=magnitude,
        place="test",
        url="",
    )


def test_earthquake_severity_buckets() -> None:
    cases = [
        (1.0,  "micro"),
        (3.0,  "minor"),
        (4.0,  "light"),
        (5.5,  "moderate"),
        (6.5,  "strong"),
        (7.5,  "major"),
        (8.5,  "great"),
    ]
    for mag, expected in cases:
        assert _make_quake(mag).severity_bucket() == expected


def test_earthquake_is_recent() -> None:
    now = time.time()
    fresh = _make_quake(5.0, age_h=0.5)
    old = _make_quake(5.0, age_h=48.0)
    assert fresh.is_recent(now, hours=24) is True
    assert old.is_recent(now, hours=24) is False


def test_earthquake_is_hashable() -> None:
    """Frozen dataclass debe poder ir en un set (para diffs)."""

    a = _make_quake(5.0)
    b = _make_quake(5.0)
    s = {a, b}
    assert len(s) >= 1  # mismo id por construcción → mismo hash


# ============================================================
# ShakeStation
# ============================================================
def test_shakestation_nslc_prefix() -> None:
    s = ShakeStation(
        network="AM", code="R0E05",
        latitude=40.4, longitude=-3.7, elevation_m=650.0,
        site_name="Madrid",
    )
    assert s.nslc_prefix == "AM.R0E05"


def test_shakestation_is_hashable() -> None:
    s = ShakeStation(network="AM", code="X", latitude=0.0,
                     longitude=0.0, elevation_m=0.0)
    assert isinstance(hash(s), int)
