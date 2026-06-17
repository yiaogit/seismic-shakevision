"""Tests para ``shakevision.utils.periods`` (v0.7.7, O2). Sin Qt."""

from __future__ import annotations

from dataclasses import dataclass

from shakevision.utils.periods import (
    PERIOD_SECONDS,
    filter_for_period,
    period_seconds,
)


@dataclass
class _Quake:
    timestamp_unix: float


def test_period_seconds_known():
    assert period_seconds("all_hour") == 3600
    assert period_seconds("all_day") == 86_400
    assert period_seconds("all_week") == 7 * 86_400


def test_period_seconds_unknown_defaults_to_one_day():
    assert period_seconds("nonsense") == 86_400
    assert period_seconds("") == 86_400


def test_all_period_names_have_positive_seconds():
    assert PERIOD_SECONDS  # no vacío
    assert all(v > 0 for v in PERIOD_SECONDS.values())


def test_filter_for_period_keeps_recent_drops_old():
    now = 1_000_000.0
    quakes = [
        _Quake(now - 100),          # hace 100 s  → dentro de 1 h
        _Quake(now - 7200),         # hace 2 h     → fuera de 1 h
        _Quake(now),                # justo ahora  → dentro
    ]
    kept = filter_for_period(quakes, "all_hour", now=now)
    assert _Quake(now - 100) in kept
    assert _Quake(now) in kept
    assert _Quake(now - 7200) not in kept
    assert len(kept) == 2


def test_filter_for_period_boundary_inclusive():
    now = 500.0
    # exactamente en el corte (now - 3600) debe incluirse (>=)
    edge = _Quake(now - 3600)
    assert edge in filter_for_period([edge], "all_hour", now=now)


def test_filter_for_period_empty():
    assert filter_for_period([], "all_day", now=123.0) == []
