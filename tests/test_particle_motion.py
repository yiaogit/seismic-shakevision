"""
Pruebas de las funciones puras del panel de movimiento de partícula.

El widget Qt en sí requiere PySide6, así que aquí solo verificamos
``color_trail`` y ``auto_range``.
"""

from __future__ import annotations

import numpy as np
import pytest

# El módulo importa pyqtgraph en su cabecera; si no está, omitimos.
pyqtgraph = pytest.importorskip("pyqtgraph", reason="pyqtgraph no instalado")

from shakevision.ui.particle_motion_widget import auto_range, color_trail  # noqa: E402


# ============================================================
# color_trail
# ============================================================
def test_color_trail_returns_rgba_uint8() -> None:
    colors = color_trail(60)
    assert colors.shape == (60, 4)
    assert colors.dtype == np.uint8
    assert (colors >= 0).all() and (colors <= 255).all()


def test_color_trail_zero_returns_empty() -> None:
    assert color_trail(0).shape == (0, 4)


def test_color_trail_is_monotonic_brightness() -> None:
    """El último color debe ser más brillante que el primero."""

    colors = color_trail(20)
    luma_first = float(colors[0, :3].astype(np.float32).mean())
    luma_last = float(colors[-1, :3].astype(np.float32).mean())
    assert luma_last > luma_first


# ============================================================
# auto_range
# ============================================================
def test_auto_range_uses_floor_for_silence() -> None:
    """Una entrada en silencio debe quedar acotada por el piso."""

    out = auto_range(np.zeros(100, dtype=np.float32), floor=0.05)
    assert out == pytest.approx(0.05)


def test_auto_range_scales_with_peak() -> None:
    """El rango debe ser ~1.15× el pico absoluto."""

    x = np.array([-2.0, 1.0, 0.5], dtype=np.float32)
    out = auto_range(x, floor=0.05)
    assert out == pytest.approx(2.0 * 1.15, abs=1e-3)


def test_auto_range_empty_returns_floor() -> None:
    out = auto_range(np.zeros(0, dtype=np.float32), floor=0.123)
    assert out == pytest.approx(0.123)
