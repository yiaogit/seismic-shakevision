"""Tests para shakevision.processing.measurements (v0.7.7). Sin Qt."""

from __future__ import annotations

import numpy as np
import pytest

from shakevision.processing import measurements as m


def test_peak_amplitude_and_p2p():
    x = np.array([0.0, 3.0, -5.0, 2.0], dtype=np.float32)
    assert m.peak_amplitude(x) == 5.0
    assert m.peak_to_peak(x) == 8.0       # 3 − (−5)


def test_rotate_ne_rt_back_azimuth_zero():
    # ba=0: R = -N, T = -E (convención ObsPy).
    n = np.array([1.0, 2.0], dtype=np.float32)
    e = np.array([3.0, 4.0], dtype=np.float32)
    r, t = m.rotate_ne_rt(n, e, 0.0)
    assert np.allclose(r, -n)
    assert np.allclose(t, -e)


def test_rotate_ne_rt_preserves_horizontal_energy():
    # La rotación es ortonormal: R²+T² = N²+E² muestra a muestra.
    rng = np.random.default_rng(0)
    n = rng.standard_normal(64).astype(np.float32)
    e = rng.standard_normal(64).astype(np.float32)
    for ba in (0.0, 37.0, 90.0, 180.0, 268.0):
        r, t = m.rotate_ne_rt(n, e, ba)
        assert np.allclose(r**2 + t**2, n**2 + e**2, atol=1e-4)


def test_great_circle_degrees_known_points():
    assert abs(m.great_circle_degrees(0, 0, 0, 0)) < 1e-9
    assert abs(m.great_circle_degrees(0, 0, 0, 90) - 90.0) < 1e-6
    assert abs(m.great_circle_degrees(0, 0, 0, 180) - 180.0) < 1e-6
    assert abs(m.great_circle_degrees(0, 0, 90, 0) - 90.0) < 1e-6


def test_welch_psd_peaks_at_input_frequency():
    fs = 100.0
    t = np.arange(0, 10, 1 / fs)
    x = np.sin(2 * np.pi * 5.0 * t).astype(np.float32)
    freqs, psd = m.welch_psd(x, fs)
    assert freqs.size > 0 and psd.size == freqs.size
    fpeak = float(freqs[int(np.argmax(psd))])
    assert abs(fpeak - 5.0) < 1.0


def test_welch_psd_empty_on_short_input():
    f, p = m.welch_psd(np.zeros(3), 100.0)
    assert f.size == 0 and p.size == 0


def test_polarization_linear_ns():
    # Movimiento lineal N-S (E=0): azimut ≈ 0°, rectilinearidad ≈ 1.
    t = np.linspace(0, 1, 200)
    n = np.sin(2 * np.pi * 5 * t).astype(np.float32)
    e = np.zeros_like(n)
    az, rect = m.polarization_azimuth(n, e)
    assert abs(az - 0.0) < 1.0 or abs(az - 180.0) < 1.0
    assert rect > 0.99


def test_polarization_linear_45deg():
    # Movimiento lineal a 45° (N=E): azimut ≈ 45°.
    t = np.linspace(0, 1, 200)
    s = np.sin(2 * np.pi * 5 * t).astype(np.float32)
    az, rect = m.polarization_azimuth(s, s)
    assert abs(az - 45.0) < 1.0
    assert rect > 0.99


def test_polarization_circular_low_rect():
    # Movimiento circular: rectilinearidad ≈ 0.
    t = np.linspace(0, 1, 400)
    n = np.cos(2 * np.pi * 5 * t).astype(np.float32)
    e = np.sin(2 * np.pi * 5 * t).astype(np.float32)
    _az, rect = m.polarization_azimuth(n, e)
    assert rect < 0.2


def test_polarization_insufficient_returns_none():
    assert m.polarization_azimuth(np.zeros(1), np.zeros(1)) is None


def test_empty_inputs_are_zero():
    e = np.zeros(0, dtype=np.float32)
    assert m.peak_amplitude(e) == 0.0
    assert m.peak_to_peak(e) == 0.0
    assert m.rms(e) == 0.0
    assert m.dominant_frequency(e, 100) == 0.0


def test_rms_of_constant():
    assert m.rms(np.full(10, 3.0, dtype=np.float32)) == pytest.approx(3.0)


def test_dominant_frequency_recovers_sine():
    fs = 100.0
    t = np.arange(0, 2.0, 1.0 / fs)
    sig = np.sin(2 * np.pi * 7.0 * t).astype(np.float32)  # 7 Hz
    f = m.dominant_frequency(sig, fs)
    assert f == pytest.approx(7.0, abs=0.6)


def test_dominant_frequency_ignores_dc():
    fs = 100.0
    t = np.arange(0, 2.0, 1.0 / fs)
    sig = (50.0 + np.sin(2 * np.pi * 5.0 * t)).astype(np.float32)  # gran DC
    assert m.dominant_frequency(sig, fs) == pytest.approx(5.0, abs=0.6)


def test_sp_to_distance():
    # factor = (6.0·3.46)/(6.0−3.46) ≈ 8.17 km/s → 10 s S-P ≈ 81.7 km
    assert m.sp_to_distance_km(10.0) == pytest.approx(81.7, abs=1.0)
    assert m.sp_to_distance_km(0.0) == 0.0
    assert m.sp_to_distance_km(-1.0) == 0.0


def test_local_magnitude_monotonic_and_guarded():
    assert m.local_magnitude(0.0, 100.0) == 0.0
    assert m.local_magnitude(1e-6, 0.0) == 0.0
    # Más amplitud → mayor magnitud a igual distancia.
    m1 = m.local_magnitude(1e-6, 100.0)
    m2 = m.local_magnitude(1e-5, 100.0)
    assert m2 > m1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
