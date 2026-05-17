"""
Pruebas del procesador DSP (``WaveformProcessor``).

Validamos cuatro propiedades críticas:

  1. **Bypass**: cuando el filtro está deshabilitado, la salida es
     idéntica a la entrada (excepto por el dtype).
  2. **Atenuación fuera de banda**: una senoide de 1 Hz pasada por un
     pasa-banda 5–10 Hz debe perder al menos 30 dB de amplitud.
  3. **Transparencia en banda**: una senoide de 5 Hz pasada por un
     pasa-banda 1–10 Hz debe conservar al menos el 90 % de su amplitud.
  4. **Robustez**: arrays más cortos que el mínimo de ``sosfiltfilt``
     no deben provocar excepciones.
"""

from __future__ import annotations

import numpy as np
import pytest

from shakevision.config import FilterConfig
from shakevision.processing.buffer import BufferSnapshot
from shakevision.processing.filters import WaveformProcessor, with_enabled


# ============================================================
# Constantes comunes
# ============================================================
SAMPLE_RATE = 100  # Hz, igual que Raspberry Shake


def _sine(freq_hz: float, duration_s: float = 10.0, amplitude: float = 1.0) -> np.ndarray:
    """Genera una senoide pura para usar como entrada de los tests."""

    n = int(duration_s * SAMPLE_RATE)
    t = np.arange(n) / SAMPLE_RATE
    return (amplitude * np.sin(2.0 * np.pi * freq_hz * t)).astype(np.float32)


def _peak_amplitude(samples: np.ndarray, drop_edge_s: float = 1.0) -> float:
    """Pico de la señal, descartando 1 s de cada borde para evitar el ringing."""

    drop = int(drop_edge_s * SAMPLE_RATE)
    if samples.size <= 2 * drop:
        return float(np.max(np.abs(samples)))
    return float(np.max(np.abs(samples[drop:-drop])))


# ============================================================
# 1. Bypass
# ============================================================
def test_bypass_returns_input_unchanged() -> None:
    """Con ``enabled=False`` el procesador no debe alterar la señal."""

    cfg = FilterConfig(enabled=False, lowcut_hz=1.0, highcut_hz=10.0)
    proc = WaveformProcessor(SAMPLE_RATE, cfg)
    x = _sine(2.0)
    y = proc.apply(x)
    assert y.dtype == np.float32
    assert np.allclose(x, y)


# ============================================================
# 2. Atenuación fuera de banda
# ============================================================
def test_signal_far_below_band_is_attenuated() -> None:
    """1 Hz pasado por 5–10 Hz: pierde al menos 30 dB."""

    cfg = FilterConfig(enabled=True, lowcut_hz=5.0, highcut_hz=10.0, order=4)
    proc = WaveformProcessor(SAMPLE_RATE, cfg)

    x = _sine(freq_hz=1.0, duration_s=10.0, amplitude=1.0)
    y = proc.apply(x)

    in_amp = _peak_amplitude(x)
    out_amp = _peak_amplitude(y)
    attenuation_db = 20.0 * np.log10(in_amp / max(out_amp, 1e-9))

    assert attenuation_db >= 30.0, f"atenuación insuficiente: {attenuation_db:.1f} dB"


def test_signal_far_above_band_is_attenuated() -> None:
    """20 Hz pasado por 1–5 Hz: pierde al menos 30 dB."""

    cfg = FilterConfig(enabled=True, lowcut_hz=1.0, highcut_hz=5.0, order=4)
    proc = WaveformProcessor(SAMPLE_RATE, cfg)

    x = _sine(freq_hz=20.0, duration_s=10.0, amplitude=1.0)
    y = proc.apply(x)

    in_amp = _peak_amplitude(x)
    out_amp = _peak_amplitude(y)
    attenuation_db = 20.0 * np.log10(in_amp / max(out_amp, 1e-9))

    assert attenuation_db >= 30.0


# ============================================================
# 3. Transparencia en banda
# ============================================================
def test_signal_inside_band_passes_through() -> None:
    """5 Hz pasado por 1–10 Hz: conserva ≥ 90 % de la amplitud."""

    cfg = FilterConfig(enabled=True, lowcut_hz=1.0, highcut_hz=10.0, order=4)
    proc = WaveformProcessor(SAMPLE_RATE, cfg)

    x = _sine(freq_hz=5.0, duration_s=10.0, amplitude=1.0)
    y = proc.apply(x)

    ratio = _peak_amplitude(y) / _peak_amplitude(x)
    assert ratio >= 0.9, f"pérdida en banda demasiado alta: ratio={ratio:.3f}"


# ============================================================
# 4. Robustez
# ============================================================
def test_short_array_does_not_crash() -> None:
    """Arrays muy cortos solo aplican detrend y devuelven sin filtrar."""

    cfg = FilterConfig(enabled=True, lowcut_hz=1.0, highcut_hz=10.0, order=4)
    proc = WaveformProcessor(SAMPLE_RATE, cfg)

    short = np.linspace(0.0, 1.0, 8, dtype=np.float32)
    out = proc.apply(short)
    assert out.shape == short.shape
    assert out.dtype == np.float32
    # Detrend resta la media: el resultado debe tener media ≈ 0
    assert abs(float(np.mean(out))) < 1e-5


def test_empty_array_returns_empty_array() -> None:
    """Entrada vacía -> salida vacía sin error."""

    proc = WaveformProcessor(SAMPLE_RATE, FilterConfig())
    out = proc.apply(np.zeros(0, dtype=np.float32))
    assert out.size == 0


def test_invalid_band_disables_filter_only() -> None:
    """Si lowcut >= highcut el filtro se desactiva pero el detrend sigue."""

    cfg = FilterConfig(enabled=True, lowcut_hz=10.0, highcut_hz=1.0, order=4)
    proc = WaveformProcessor(SAMPLE_RATE, cfg)

    x = _sine(freq_hz=2.0) + 5.0  # Senoide con offset DC
    y = proc.apply(x)
    assert y.shape == x.shape
    # El detrend debe haber eliminado el offset DC (5 V)
    assert abs(float(np.mean(y))) < 0.05


# ============================================================
# 5. apply_snapshot conserva eje temporal y procesa los tres canales
# ============================================================
def test_apply_snapshot_preserves_axes_and_processes_all_channels() -> None:
    """Un snapshot procesado debe tener el mismo eje X y atenuación coherente."""

    cfg = FilterConfig(enabled=True, lowcut_hz=5.0, highcut_hz=10.0, order=4)
    proc = WaveformProcessor(SAMPLE_RATE, cfg)

    n = 1000
    times = np.arange(-n + 1, 1, dtype=np.float32) / SAMPLE_RATE
    samples = {ch: _sine(1.0, duration_s=10.0) for ch in ("Z", "N", "E")}
    snap = BufferSnapshot(times=times, samples=samples, latest_timestamp_unix=42.0)

    out = proc.apply_snapshot(snap)
    assert out is not snap                           # devuelve uno nuevo
    assert np.array_equal(out.times, snap.times)     # eje preservado
    assert out.latest_timestamp_unix == 42.0
    for ch in ("Z", "N", "E"):
        # Cada canal pasa de amplitud 1 a una mucho menor (1 Hz fuera de 5–10)
        assert _peak_amplitude(out.samples[ch]) < 0.1


# ============================================================
# 6. update_filter rediseña los coeficientes
# ============================================================
def test_update_filter_changes_band() -> None:
    """Tras cambiar la banda, la atenuación de una frecuencia cambia coherentemente."""

    proc = WaveformProcessor(SAMPLE_RATE, FilterConfig(enabled=True, lowcut_hz=5.0, highcut_hz=10.0))
    x = _sine(2.0)

    # 2 Hz fuera de la banda inicial -> muy atenuada
    y1 = proc.apply(x)
    amp1 = _peak_amplitude(y1)

    # Mover la banda a 1–5 Hz: ahora 2 Hz queda dentro -> casi sin atenuar
    proc.update_filter(FilterConfig(enabled=True, lowcut_hz=1.0, highcut_hz=5.0))
    y2 = proc.apply(x)
    amp2 = _peak_amplitude(y2)

    assert amp2 > 5.0 * amp1


# ============================================================
# 7. Helper with_enabled
# ============================================================
def test_with_enabled_helper() -> None:
    """``with_enabled`` solo cambia el flag y conserva el resto."""

    base = FilterConfig(lowcut_hz=2.0, highcut_hz=8.0, order=3, detrend=False)
    flipped = with_enabled(base, enabled=False)
    assert flipped.enabled is False
    assert flipped.lowcut_hz == 2.0
    assert flipped.highcut_hz == 8.0
    assert flipped.order == 3
    assert flipped.detrend is False


# ============================================================
# 8. update_sample_rate
# ============================================================
def test_update_sample_rate_changes_rate_and_validates() -> None:
    """Cambiar la frecuencia de muestreo rediseña el filtro; valores no positivos fallan."""

    proc = WaveformProcessor(SAMPLE_RATE, FilterConfig())
    proc.update_sample_rate(200)  # No debe lanzar
    with pytest.raises(ValueError):
        proc.update_sample_rate(0)
