"""
Pruebas del cálculo de espectrograma.

Verifican que la frecuencia dominante de una senoide pura cae en la
columna correcta del espectrograma y que arrays demasiado cortos no
provocan errores.
"""

from __future__ import annotations

import numpy as np

from shakevision.processing.spectrum import (
    DB_FLOOR,
    SpectrumComputer,
    SpectrumResult,
)


SAMPLE_RATE = 100  # Hz


def _sine(freq_hz: float, duration_s: float = 4.0) -> np.ndarray:
    n = int(duration_s * SAMPLE_RATE)
    t = np.arange(n) / SAMPLE_RATE
    return np.sin(2.0 * np.pi * freq_hz * t).astype(np.float32)


def test_compute_returns_spectrum_result() -> None:
    comp = SpectrumComputer(SAMPLE_RATE)
    out = comp.compute(_sine(5.0))
    assert isinstance(out, SpectrumResult)
    assert out.freqs.size > 0
    assert out.times.size > 0
    assert out.power_db.shape == (out.freqs.size, out.times.size)


def test_dominant_frequency_matches_input() -> None:
    """La frecuencia con mayor potencia debe coincidir con la senoide de entrada."""

    target = 7.0  # Hz
    comp = SpectrumComputer(SAMPLE_RATE)
    out = comp.compute(_sine(target, duration_s=4.0))

    # Tomamos la potencia media por frecuencia y buscamos el bin máximo
    mean_power = out.power_db.mean(axis=1)
    idx = int(np.argmax(mean_power))
    detected = float(out.freqs[idx])

    # Tolerancia: la resolución espectral con nperseg=100 es 1 Hz
    assert abs(detected - target) <= 1.0


def test_short_input_returns_empty_result_safely() -> None:
    comp = SpectrumComputer(SAMPLE_RATE)
    out = comp.compute(np.zeros(10, dtype=np.float32))  # menos que nperseg
    assert out.freqs.size == 0
    assert out.times.size == 0
    assert out.power_db.size == 0


def test_silence_uses_db_floor() -> None:
    """Una entrada en silencio absoluto debe tocar fondo en DB_FLOOR."""

    comp = SpectrumComputer(SAMPLE_RATE)
    out = comp.compute(np.zeros(SAMPLE_RATE * 4, dtype=np.float32))
    assert out.power_db.min() >= DB_FLOOR - 1e-3
    # Y el promedio debe estar cerca del piso (no exactamente, por la ventana Hann)
    assert out.power_db.mean() < DB_FLOOR + 5.0


def test_times_axis_ends_at_zero() -> None:
    comp = SpectrumComputer(SAMPLE_RATE)
    out = comp.compute(_sine(2.0, duration_s=4.0))
    assert out.times[-1] == 0.0
    assert out.times[0] < 0.0


def test_update_sample_rate_accepts_positive() -> None:
    comp = SpectrumComputer(SAMPLE_RATE)
    comp.update_sample_rate(200)
    out = comp.compute(_sine(15.0, duration_s=4.0)[:800])
    assert out.freqs.size > 0
