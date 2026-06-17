"""Tests para los helpers puros de shakevision.services.response (v0.7.7).

Solo cubren las funciones sin red ni ObsPy (conversión de unidades).
"""

from __future__ import annotations

import numpy as np
import pytest

from shakevision.services.response import (
    counts_to_velocity,
    scale_velocity_units,
)


def test_counts_to_velocity_divides_by_sensitivity():
    counts = np.array([1000.0, -2000.0], dtype=np.float32)
    out = counts_to_velocity(counts, 1e6)        # 1e6 counts per m/s
    assert out[0] == pytest.approx(1e-3)
    assert out[1] == pytest.approx(-2e-3)
    assert out.dtype == np.float32


def test_counts_to_velocity_fallback_when_invalid_sensitivity():
    counts = np.array([1.0, 2.0], dtype=np.float32)
    # sensibilidad inválida → devuelve la entrada sin tocar
    assert counts_to_velocity(counts, 0.0) is counts
    assert counts_to_velocity(counts, -5.0) is counts


def test_scale_velocity_units_picks_sensible_prefix():
    assert scale_velocity_units(0.0) == (0.0, "m/s")
    v, u = scale_velocity_units(1e-9)        # 1 nm/s
    assert u == "nm/s" and v == pytest.approx(1.0)
    v, u = scale_velocity_units(2e-6)        # 2 µm/s
    assert u == "µm/s" and v == pytest.approx(2.0)
    v, u = scale_velocity_units(5e-3)        # 5 mm/s
    assert u == "mm/s" and v == pytest.approx(5.0)
    v, u = scale_velocity_units(3.0)         # 3 m/s
    assert u == "m/s" and v == pytest.approx(3.0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
