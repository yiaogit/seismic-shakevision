"""
Pruebas del detector STA/LTA.

Cubrimos:
  * función característica clásica (forma, magnitud razonable);
  * histéresis del detector con un escalón sintético;
  * desactivación por configuración;
  * cambio de configuración en caliente.
"""

from __future__ import annotations

import numpy as np
import pytest

from shakevision.config import TriggerConfig
from shakevision.processing.buffer import BufferSnapshot
from shakevision.processing.detector import (
    EventSignal,
    StaLtaDetector,
    classic_sta_lta,
)


SAMPLE_RATE = 100  # Hz


# ============================================================
# Helpers
# ============================================================
def _make_snapshot(samples: np.ndarray, ts: float = 0.0) -> BufferSnapshot:
    n = samples.size
    times = np.arange(-n + 1, 1, dtype=np.float32) / SAMPLE_RATE
    return BufferSnapshot(
        times=times,
        samples={
            "Z": samples.astype(np.float32),
            "N": np.zeros_like(samples, dtype=np.float32),
            "E": np.zeros_like(samples, dtype=np.float32),
        },
        latest_timestamp_unix=ts,
    )


# ============================================================
# classic_sta_lta
# ============================================================
def test_classic_sta_lta_validates_window_sizes() -> None:
    with pytest.raises(ValueError):
        classic_sta_lta(np.ones(100), sta_n=0, lta_n=10)
    with pytest.raises(ValueError):
        classic_sta_lta(np.ones(100), sta_n=20, lta_n=10)  # sta >= lta


def test_classic_sta_lta_returns_correct_shape() -> None:
    out = classic_sta_lta(np.ones(500), sta_n=50, lta_n=200)
    assert out.shape == (500,)
    assert out.dtype == np.float32


def test_classic_sta_lta_constant_signal_yields_one() -> None:
    """Una señal constante debe dar ratio ~1 (energía igual en sta y lta)."""

    out = classic_sta_lta(np.ones(1000) * 2.0, sta_n=50, lta_n=200)
    # Tras estabilizarse, el ratio debe ser ≈ 1
    assert abs(out[800] - 1.0) < 0.01


def test_classic_sta_lta_step_signal_jumps_above_one() -> None:
    """Un escalón debe producir un pico claro de la función característica."""

    n = 2000
    x = np.zeros(n, dtype=np.float64)
    x[:1000] = 0.01 * np.random.default_rng(0).standard_normal(1000)  # ruido bajo
    x[1000:] = 1.0 * np.random.default_rng(1).standard_normal(1000)  # ruido alto

    cft = classic_sta_lta(x, sta_n=50, lta_n=500)
    # Justo después del escalón, la STA explota frente a la LTA.
    # En el peor caso teórico el ratio cae cerca de 5; usamos 4 como
    # cota inferior conservadora para que la prueba no falle por ruido.
    assert cft[1100] > 4.0


# ============================================================
# StaLtaDetector — histéresis
# ============================================================
def test_detector_is_initially_armed() -> None:
    cfg = TriggerConfig(enabled=True)
    det = StaLtaDetector(SAMPLE_RATE, cfg)
    assert det.is_triggered is False


def test_detector_disabled_returns_no_signal() -> None:
    cfg = TriggerConfig(enabled=False)
    det = StaLtaDetector(SAMPLE_RATE, cfg)
    snap = _make_snapshot(np.ones(2000) * 5.0)
    state = det.process(snap)
    assert state.signal == EventSignal.NONE
    assert state.is_triggered is False


def test_detector_triggers_on_step_signal() -> None:
    """Una explosión clara dispara el detector y luego se libera."""

    cfg = TriggerConfig(
        enabled=True,
        sta_seconds=0.5,
        lta_seconds=5.0,
        threshold_on=3.5,
        threshold_off=1.5,
    )
    det = StaLtaDetector(SAMPLE_RATE, cfg)

    rng = np.random.default_rng(0)

    # 1) Snapshot tranquilo: solo ruido bajo
    quiet = 0.01 * rng.standard_normal(2000).astype(np.float32)
    state = det.process(_make_snapshot(quiet))
    assert state.signal == EventSignal.NONE
    assert state.is_triggered is False

    # 2) Snapshot con un final muy enérgico → debe disparar
    tail = quiet.copy()
    # Pico de 80 muestras: ratio ≈ lta_n/80 = 500/80 = 6.25, supera 3.5
    tail[-80:] = 8.0 * rng.standard_normal(80).astype(np.float32)
    state = det.process(_make_snapshot(tail))
    assert state.signal == EventSignal.TRIGGERED
    assert state.is_triggered is True

    # 3) Snapshot que vuelve a estar tranquilo → debe liberar
    quiet2 = 0.01 * rng.standard_normal(2000).astype(np.float32)
    state = det.process(_make_snapshot(quiet2))
    assert state.signal == EventSignal.RELEASED
    assert state.is_triggered is False


def test_detector_does_not_retrigger_while_active() -> None:
    """Mientras la energía sigue alta, no debe re-emitir TRIGGERED."""

    cfg = TriggerConfig(enabled=True, sta_seconds=0.5, lta_seconds=5.0,
                        threshold_on=3.5, threshold_off=1.5)
    det = StaLtaDetector(SAMPLE_RATE, cfg)
    rng = np.random.default_rng(1)

    quiet = 0.01 * rng.standard_normal(2000).astype(np.float32)
    det.process(_make_snapshot(quiet))                 # NONE
    loud = quiet.copy()
    loud[-80:] = 8.0 * rng.standard_normal(80).astype(np.float32)
    state = det.process(_make_snapshot(loud))          # TRIGGERED
    assert state.signal == EventSignal.TRIGGERED

    # Otro bloque ruidoso: debe seguir disparado pero NO re-disparar
    state = det.process(_make_snapshot(loud))
    assert state.signal == EventSignal.NONE
    assert state.is_triggered is True


def test_detector_update_config_keeps_state() -> None:
    cfg = TriggerConfig(enabled=True)
    det = StaLtaDetector(SAMPLE_RATE, cfg)
    new_cfg = TriggerConfig(enabled=True, threshold_on=10.0)
    det.update_config(new_cfg)
    assert det.config.threshold_on == 10.0


def test_detector_reset_clears_state() -> None:
    cfg = TriggerConfig(enabled=True, sta_seconds=0.5, lta_seconds=5.0,
                        threshold_on=3.5, threshold_off=1.5)
    det = StaLtaDetector(SAMPLE_RATE, cfg)
    rng = np.random.default_rng(2)
    quiet = 0.01 * rng.standard_normal(2000).astype(np.float32)
    loud = quiet.copy()
    loud[-80:] = 8.0 * rng.standard_normal(80).astype(np.float32)
    det.process(_make_snapshot(quiet))
    det.process(_make_snapshot(loud))
    assert det.is_triggered is True

    det.reset()
    assert det.is_triggered is False
    assert det.last_trigger_timestamp is None


def test_detector_returns_no_signal_when_buffer_too_short() -> None:
    cfg = TriggerConfig(enabled=True, sta_seconds=0.5, lta_seconds=5.0)
    det = StaLtaDetector(SAMPLE_RATE, cfg)
    short = np.ones(50, dtype=np.float32)  # menos que lta_n = 500
    state = det.process(_make_snapshot(short))
    assert state.signal == EventSignal.NONE
