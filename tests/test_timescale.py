"""Pruebas del mapeo valor↔fracción del slider de rango (puro)."""

from __future__ import annotations

import math

from shakevision.utils import timescale as ts


def test_endpoints_map_to_0_and_1() -> None:
    t0, t1 = 1000.0, 5000.0
    assert ts.frac_for_value(t0, t0, t1) == 0.0
    assert ts.frac_for_value(t1, t0, t1) == 1.0


def test_value_frac_roundtrip() -> None:
    t0, t1 = 0.0, 1_000_000.0
    for v in (10_000.0, 250_000.0, 900_000.0):
        f = ts.frac_for_value(v, t0, t1)
        back = ts.value_for_frac(f, t0, t1)
        assert math.isclose(back, v, rel_tol=1e-6, abs_tol=1e-3)


def test_recent_gets_more_resolution() -> None:
    """Con warp<1, la mitad DERECHA del eje (reciente) cubre menos tiempo que la
    izquierda → más resolución para lo reciente."""

    t0, t1 = 0.0, 100.0
    mid_value = ts.value_for_frac(0.5, t0, t1)   # instante en la mitad del eje
    # La mitad del ancho corresponde a un instante MÁS reciente que el punto
    # medio temporal (50): lo reciente está "estirado".
    assert mid_value > 50.0


def test_clamp_orders_and_bounds() -> None:
    lo, hi = ts.clamp_range(8000, 2000, 0, 10000)   # invertido
    assert lo == 2000 and hi == 8000
    lo, hi = ts.clamp_range(-50, 99999, 0, 10000)   # fuera de rango
    assert lo == 0 and hi == 10000


def test_clamp_min_gap() -> None:
    lo, hi = ts.clamp_range(5000, 5000, 0, 10000, min_gap=1000)
    assert hi - lo >= 1000
    # Cerca del borde derecho: el hueco se mantiene empujando lo.
    lo, hi = ts.clamp_range(10000, 10000, 0, 10000, min_gap=1000)
    assert hi - lo >= 1000 and hi <= 10000 and lo >= 0


def test_degenerate_range() -> None:
    assert ts.frac_for_value(5, 5, 5) == 0.0
    assert ts.value_for_frac(0.5, 5, 5) == 5
