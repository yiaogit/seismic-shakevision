"""
Pruebas de las funciones de hash/dedup del worker de datos.

Verifican que dos lotes idénticos producen el mismo hash y que un
cambio mínimo cambia el hash, condición necesaria para el dedup
implementado en ``_RefreshWorker``.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6.QtCore", reason="PySide6 no instalado")

from shakevision.services.data_models import Earthquake, ShakeStation  # noqa: E402
from shakevision.services.worker import (  # noqa: E402
    _hash_earthquakes,
    _hash_stations,
)


def _q(eid: str, ts: float, mag: float = 5.0) -> Earthquake:
    return Earthquake(
        id=eid, timestamp_unix=ts, longitude=0, latitude=0,
        depth_km=10, magnitude=mag, place="X", url="",
    )


def _s(code: str) -> ShakeStation:
    return ShakeStation(network="AM", code=code,
                        latitude=0.0, longitude=0.0, elevation_m=0.0)


# ============================================================
# Earthquake hash
# ============================================================
def test_quake_hash_is_stable_for_equivalent_lists() -> None:
    a = [_q("a", 1.0), _q("b", 2.0)]
    b = [_q("a", 1.0), _q("b", 2.0)]
    assert _hash_earthquakes(a) == _hash_earthquakes(b)


def test_quake_hash_changes_when_ts_changes() -> None:
    a = [_q("a", 1.0)]
    b = [_q("a", 2.0)]
    assert _hash_earthquakes(a) != _hash_earthquakes(b)


def test_quake_hash_changes_when_id_changes() -> None:
    a = [_q("a", 1.0)]
    b = [_q("b", 1.0)]
    assert _hash_earthquakes(a) != _hash_earthquakes(b)


def test_quake_hash_distinguishes_orderings() -> None:
    """El orden importa porque el hash es de tupla."""

    a = [_q("a", 1.0), _q("b", 2.0)]
    b = [_q("b", 2.0), _q("a", 1.0)]
    assert _hash_earthquakes(a) != _hash_earthquakes(b)


def test_quake_hash_empty_is_consistent() -> None:
    assert _hash_earthquakes([]) == _hash_earthquakes([])


# ============================================================
# Station hash
# ============================================================
def test_station_hash_stable() -> None:
    a = [_s("R0E05"), _s("RB5E8")]
    b = [_s("R0E05"), _s("RB5E8")]
    assert _hash_stations(a) == _hash_stations(b)


def test_station_hash_distinguishes_codes() -> None:
    assert _hash_stations([_s("X")]) != _hash_stations([_s("Y")])
