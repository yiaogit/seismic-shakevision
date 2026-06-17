"""Tests para los helpers puros de SeedLinkSource (v0.7.7).

Cubren el remuestreo a la tasa nominal (estaciones broadband IRIS a 20/40
Hz → 100 Hz) y el relleno de alineación con "hold DC" (último valor real)
en vez de ceros, que arreglan el oscilograma a "barras" y el hodograma a
saltos con estaciones de 3 componentes asíncronas.

Solo tocan funciones estáticas (numpy puro); si PySide6.QtCore no se puede
importar, se saltan limpiamente.
"""

from __future__ import annotations

import numpy as np
import pytest

try:
    from shakevision.sources.seedlink import SeedLinkSource
except Exception as _exc:  # noqa: BLE001
    pytest.skip(f"PySide6 no disponible ({_exc})", allow_module_level=True)


def test_resample_upsamples_to_target_rate():
    a = np.sin(np.linspace(0, 2 * np.pi, 20)).astype(np.float32)
    out = SeedLinkSource._resample(a, 20, 100)
    assert out.size == 100        # 20 muestras (1 s @20Hz) → 100 @100Hz
    assert out.dtype == np.float32


def test_resample_downsamples():
    a = np.arange(40, dtype=np.float32)
    out = SeedLinkSource._resample(a, 40, 100)
    assert out.size == 100        # 40 @40Hz (1 s) → 100 @100Hz
    a2 = np.arange(100, dtype=np.float32)
    assert SeedLinkSource._resample(a2, 100, 40).size == 40


def test_resample_noop_when_rates_match_or_empty():
    a = np.ones(10, dtype=np.float32)
    assert SeedLinkSource._resample(a, 100, 100) is a
    assert SeedLinkSource._resample(np.zeros(0, dtype=np.float32), 20, 100).size == 0


def test_resample_preserves_endpoints():
    a = np.array([1.0, 5.0], dtype=np.float32)
    out = SeedLinkSource._resample(a, 2, 10)
    assert out[0] == pytest.approx(1.0)
    assert out[-1] == pytest.approx(5.0)


def test_pad_left_holds_fill_value():
    arr = np.array([5, 6, 7], dtype=np.float32)
    out = SeedLinkSource._pad_left(arr, 6, fill=9.0)
    assert out.tolist() == [9.0, 9.0, 9.0, 5.0, 6.0, 7.0]


def test_pad_left_defaults_to_zero():
    arr = np.array([1, 2], dtype=np.float32)
    assert SeedLinkSource._pad_left(arr, 4).tolist() == [0.0, 0.0, 1.0, 2.0]


def test_pad_left_no_change_or_truncate():
    arr = np.array([1, 2, 3], dtype=np.float32)
    assert SeedLinkSource._pad_left(arr, 3, 9.0).tolist() == [1, 2, 3]
    assert SeedLinkSource._pad_left(arr, 2, 9.0).tolist() == [2, 3]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
