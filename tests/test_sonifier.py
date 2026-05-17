"""
Pruebas del sonificador (``processing.sonifier``).

Cubrimos:
  * validación de argumentos;
  * camino vacío (entrada de tamaño 0);
  * dtype y rango int16 de la salida;
  * normalización: pico ≈ ``target_amplitude × 32767``;
  * helper ``estimate_audio_duration_s``.
"""

from __future__ import annotations

import numpy as np
import pytest

# scipy es la única dependencia pesada del módulo
pytest.importorskip("scipy", reason="SciPy no instalado")

from shakevision.processing.sonifier import (  # noqa: E402
    AUDIO_RATE_HZ,
    SonifyResult,
    estimate_audio_duration_s,
    sonify,
)


# ============================================================
# Validación
# ============================================================
def test_sonify_rejects_invalid_input_rate() -> None:
    with pytest.raises(ValueError):
        sonify(np.ones(100, dtype=np.float32), input_rate_hz=0, speed_factor=60)


def test_sonify_rejects_invalid_speed() -> None:
    with pytest.raises(ValueError):
        sonify(np.ones(100, dtype=np.float32), input_rate_hz=100, speed_factor=0)


def test_sonify_rejects_invalid_amplitude() -> None:
    with pytest.raises(ValueError):
        sonify(np.ones(100, dtype=np.float32), input_rate_hz=100, speed_factor=60,
               target_amplitude=1.5)
    with pytest.raises(ValueError):
        sonify(np.ones(100, dtype=np.float32), input_rate_hz=100, speed_factor=60,
               target_amplitude=0.0)


# ============================================================
# Camino vacío
# ============================================================
def test_sonify_empty_input_returns_empty_int16() -> None:
    out = sonify(np.zeros(0, dtype=np.float32), input_rate_hz=100, speed_factor=60)
    assert isinstance(out, SonifyResult)
    assert out.audio.size == 0
    assert out.audio.dtype == np.int16
    assert out.audio_duration_s == 0.0
    assert out.input_samples == 0


# ============================================================
# Dtype y rango
# ============================================================
def test_sonify_returns_int16_within_range() -> None:
    rng = np.random.default_rng(0)
    samples = rng.standard_normal(6000).astype(np.float32)  # 60 s @ 100 Hz
    out = sonify(samples, input_rate_hz=100, speed_factor=60)

    assert out.audio.dtype == np.int16
    assert out.audio.size > 0
    assert out.audio.min() >= -32768
    assert out.audio.max() <= 32767


def test_sonify_audio_rate_is_44100() -> None:
    samples = np.linspace(-1.0, 1.0, 6000, dtype=np.float32)
    out = sonify(samples, input_rate_hz=100, speed_factor=60)
    assert out.audio_rate_hz == AUDIO_RATE_HZ


def test_sonify_duration_is_consistent() -> None:
    """60 s × 60 ⇒ 1 s de audio (± resampling ~5%)."""

    samples = np.linspace(-1.0, 1.0, 6000, dtype=np.float32)
    out = sonify(samples, input_rate_hz=100, speed_factor=60)
    assert 0.85 < out.audio_duration_s < 1.15


# ============================================================
# Normalización
# ============================================================
def test_sonify_normalizes_peak_to_target() -> None:
    """El pico debe quedar cerca de ``target_amplitude * 32767``."""

    samples = np.linspace(-1.0, 1.0, 6000, dtype=np.float32)
    target = 0.7
    out = sonify(samples, input_rate_hz=100, speed_factor=60,
                 target_amplitude=target)
    expected_peak = int(32767 * target)
    # Tras el remuestreo el pico puede oscilar ~ ±2 %
    assert abs(out.peak_amplitude_int16 - expected_peak) <= int(expected_peak * 0.05)


def test_sonify_silent_input_returns_silent_output() -> None:
    """Una entrada constante produce audio silente (no NaN, no clipping)."""

    samples = np.full(6000, 5.0, dtype=np.float32)
    out = sonify(samples, input_rate_hz=100, speed_factor=60)
    assert out.audio.size > 0
    # Tras detrend la señal queda en ceros y no hay nada que escalar
    assert out.peak_amplitude_int16 == 0
    assert int(out.audio.max()) == 0
    assert int(out.audio.min()) == 0


# ============================================================
# Helper de duración
# ============================================================
def test_estimate_audio_duration_s_basic() -> None:
    # 60 s × 60 = 1 s
    assert estimate_audio_duration_s(6000, 100, 60.0) == pytest.approx(1.0)
    # 30 s × 30 = 1 s
    assert estimate_audio_duration_s(3000, 100, 30.0) == pytest.approx(1.0)
    # 60 s × 120 = 0.5 s
    assert estimate_audio_duration_s(6000, 100, 120.0) == pytest.approx(0.5)


def test_estimate_audio_duration_s_invalid() -> None:
    assert estimate_audio_duration_s(6000, 0, 60.0) == 0.0
    assert estimate_audio_duration_s(6000, 100, 0.0) == 0.0
