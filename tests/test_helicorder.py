"""
Pruebas de las primitivas puras del panel helicorder.

No instanciamos el QFrame (requiere PySide6 + display); validamos
las dos piezas críticas que sí podemos probar de forma aislada:

  * ``envelope_decimate``: conserva picos en bloques largos.
  * ``_HelicorderBuffer``: escritura, envoltura y linealización en
    el orden temporal correcto.
"""

from __future__ import annotations

import numpy as np
import pytest

# El módulo importa pyqtgraph en su cabecera; si no está, omitimos.
pytest.importorskip("pyqtgraph", reason="pyqtgraph no instalado")

from shakevision.ui.helicorder_widget import (  # noqa: E402
    _HelicorderBuffer,
    envelope_decimate,
)


# ============================================================
# envelope_decimate
# ============================================================
def test_envelope_decimate_returns_target_length() -> None:
    x = np.arange(10000, dtype=np.float32)
    low, high = envelope_decimate(x, 100)
    assert low.shape == (100,)
    assert high.shape == (100,)
    assert low.dtype == np.float32
    assert high.dtype == np.float32


def test_envelope_decimate_preserves_extremes() -> None:
    """Un pico aislado debe sobrevivir a la decimación."""

    x = np.zeros(1000, dtype=np.float32)
    x[500] = 5.0   # pico positivo
    x[600] = -3.0  # pico negativo
    low, high = envelope_decimate(x, 50)
    assert float(high.max()) == 5.0
    assert float(low.min()) == -3.0


def test_envelope_decimate_short_input_returns_passthrough() -> None:
    x = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    low, high = envelope_decimate(x, 100)
    assert np.array_equal(low, x)
    assert np.array_equal(high, x)


def test_envelope_decimate_empty_input() -> None:
    low, high = envelope_decimate(np.zeros(0, dtype=np.float32), 50)
    assert low.size == 50 and high.size == 50
    assert np.all(low == 0) and np.all(high == 0)


# ============================================================
# _HelicorderBuffer
# ============================================================
def test_helicorder_buffer_basic_write_and_linearize() -> None:
    buf = _HelicorderBuffer(capacity_samples=100)
    buf.ingest(np.arange(30, dtype=np.float32))
    out = buf.linearized()
    assert out.shape == (30,)
    assert np.array_equal(out, np.arange(30, dtype=np.float32))
    assert buf.total_written == 30


def test_helicorder_buffer_wrap_around() -> None:
    buf = _HelicorderBuffer(capacity_samples=100)
    buf.ingest(np.arange(80, dtype=np.float32))
    buf.ingest(np.arange(80, 130, dtype=np.float32))  # 50 más → fuerza wrap

    out = buf.linearized()
    assert out.shape == (100,)  # capacidad
    # Esperamos las muestras 30..129 (las 100 más recientes)
    assert np.array_equal(out, np.arange(30, 130, dtype=np.float32))


def test_helicorder_buffer_block_larger_than_capacity() -> None:
    buf = _HelicorderBuffer(capacity_samples=50)
    buf.ingest(np.arange(200, dtype=np.float32))
    out = buf.linearized()
    # Conservamos las últimas 50 (150..199)
    assert out.shape == (50,)
    assert np.array_equal(out, np.arange(150, 200, dtype=np.float32))


def test_helicorder_buffer_empty_ingest_is_noop() -> None:
    buf = _HelicorderBuffer(capacity_samples=50)
    buf.ingest(np.zeros(0, dtype=np.float32))
    assert buf.total_written == 0
    assert buf.linearized().size == 0
