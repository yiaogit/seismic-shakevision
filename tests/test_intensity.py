"""
Pruebas de la traducción PGV → MMI y del suavizador VU-meter.

No tocamos PySide6: solo validamos las funciones puras de
``shakevision.processing.intensity``. Cubrimos:

  * monotonía de ``pgv_to_mmi``;
  * límites del rango [1, 12];
  * tabla ``INTENSITY_LEVELS`` completa y consistente;
  * estimación de PGV con / sin offset DC;
  * decaimiento exponencial y "max-hold" del ``IntensitySmoother``.
"""

from __future__ import annotations

import numpy as np
import pytest

from shakevision.processing.intensity import (
    INTENSITY_LEVELS,
    IntensityLevel,
    IntensitySmoother,
    IntensitySnapshot,
    classify,
    default_gain_for,
    estimate_intensity,
    estimate_pgv,
    pgv_to_mmi,
)


# ============================================================
# pgv_to_mmi
# ============================================================
def test_pgv_to_mmi_returns_one_for_silence() -> None:
    assert pgv_to_mmi(0.0) == pytest.approx(1.0)
    assert pgv_to_mmi(0.0005) == pytest.approx(1.0)


def test_pgv_to_mmi_is_monotonic_increasing() -> None:
    """Mayor PGV ⇒ mayor MMI."""

    pgvs = [0.05, 0.5, 5.0, 50.0]
    mmis = [pgv_to_mmi(p) for p in pgvs]
    assert mmis == sorted(mmis)


def test_pgv_to_mmi_clipped_to_12() -> None:
    """Velocidades absurdamente altas no superan 12."""

    assert pgv_to_mmi(1e9) == pytest.approx(12.0)


def test_pgv_to_mmi_known_value() -> None:
    """1 cm/s → MMI ≈ 3.78 (definición de Worden 2012)."""

    assert pgv_to_mmi(1.0) == pytest.approx(3.78, abs=0.01)


# ============================================================
# classify
# ============================================================
def test_classify_returns_intensity_level() -> None:
    level = classify(0.0)
    assert isinstance(level, IntensityLevel)
    assert level.mmi == 1


def test_classify_round_trip_for_each_level() -> None:
    """La clasificación debe cubrir los 12 niveles para PGV creciente.

    El nivel 12 corresponde a PGV ≈ 4×10⁵ cm/s (≥ 4 km/s — destrucción
    total), por eso barremos hasta 10⁶.
    """

    seen: set[int] = set()
    for pgv in np.geomspace(0.001, 1e6, 80):
        seen.add(classify(float(pgv)).mmi)
    for required in (1, 2, 5, 8, 12):
        assert required in seen, f"nivel {required} no alcanzado"


def test_intensity_levels_table_is_complete() -> None:
    """La tabla debe cubrir 1..12 sin huecos."""

    assert set(INTENSITY_LEVELS.keys()) == set(range(1, 13))
    for mmi, level in INTENSITY_LEVELS.items():
        assert level.mmi == mmi
        assert isinstance(level.label, str) and level.label
        assert isinstance(level.description, str) and level.description
        assert level.color.startswith("#") and len(level.color) == 7


# ============================================================
# estimate_pgv
# ============================================================
def test_estimate_pgv_zero_for_empty() -> None:
    assert estimate_pgv(np.zeros(0, dtype=np.float32), 1.0) == 0.0


def test_estimate_pgv_uses_peak_absolute() -> None:
    samples = np.array([0.0, 1.0, -3.0, 2.0], dtype=np.float32)
    # Sin detrend: pico absoluto = 3
    assert estimate_pgv(samples, gain_cm_s_per_count=1.0, detrend=False) == 3.0


def test_estimate_pgv_detrend_removes_dc_offset() -> None:
    """Una offset DC grande NO debe inflar el PGV cuando se aplica detrend."""

    samples = np.full(1000, 1000.0, dtype=np.float32)  # señal totalmente plana
    samples[500] = 1001.0                              # un solo "pico" de +1
    pgv_with = estimate_pgv(samples, 1.0, detrend=True)
    pgv_without = estimate_pgv(samples, 1.0, detrend=False)
    assert pgv_with < 1.5
    assert pgv_without >= 1000.0


def test_estimate_pgv_applies_gain() -> None:
    samples = np.array([0.0, 5.0, -2.0], dtype=np.float32)
    assert estimate_pgv(samples, 0.5, detrend=False) == pytest.approx(2.5)


# ============================================================
# estimate_intensity
# ============================================================
def test_estimate_intensity_returns_pair() -> None:
    samples = np.array([0.0, 0.0, 0.0], dtype=np.float32)
    pgv, level = estimate_intensity(samples, 1.0)
    assert pgv == 0.0
    assert level.mmi == 1


# ============================================================
# default_gain_for
# ============================================================
def test_default_gain_for_mock_is_higher_than_real() -> None:
    """La ganancia del Mock debe ser >> que la de Raspberry Shake."""

    assert default_gain_for("XX", "MOCK") > default_gain_for("AM", "R0E05") * 1000


def test_default_gain_for_is_case_insensitive() -> None:
    assert default_gain_for("xx", "MOCK") == default_gain_for("XX", "MOCK")


# ============================================================
# IntensitySmoother
# ============================================================
def test_smoother_max_holds_then_decays() -> None:
    sm = IntensitySmoother(decay_per_second=0.1, refresh_hz=10.0)
    sm.update(5.0)
    assert sm.value == pytest.approx(5.0)
    # Tras 10 ticks (1 s) con entradas pequeñas, debe haber caído al ~10 %
    for _ in range(10):
        sm.update(0.0)
    assert 0.4 < sm.value < 0.6


def test_smoother_takes_higher_input() -> None:
    sm = IntensitySmoother(decay_per_second=0.5, refresh_hz=10.0)
    sm.update(2.0)
    sm.update(7.0)
    assert sm.value == pytest.approx(7.0)


def test_smoother_reset() -> None:
    sm = IntensitySmoother()
    sm.update(10.0)
    sm.reset()
    assert sm.value == 0.0


# ============================================================
# IntensitySnapshot.from_samples
# ============================================================
def test_snapshot_from_samples_uses_smoother_when_provided() -> None:
    sm = IntensitySmoother(decay_per_second=0.5, refresh_hz=10.0)
    # Señal con media cero para que el detrend no altere el pico
    snap = IntensitySnapshot.from_samples(
        np.array([-5.0, 5.0, -5.0, 5.0], dtype=np.float32),
        gain_cm_s_per_count=1.0,
        smoother=sm,
    )
    assert snap.pgv_cm_s == pytest.approx(5.0)
    assert isinstance(snap.level, IntensityLevel)
    assert snap.gain_cm_s_per_count == 1.0
    assert snap.mmi >= 1.0


def test_snapshot_without_smoother_returns_instantaneous_pgv() -> None:
    # Señal de media cero: detrend no la altera, pico absoluto = 1
    snap = IntensitySnapshot.from_samples(
        np.array([1.0, -1.0], dtype=np.float32),
        gain_cm_s_per_count=2.0,
    )
    assert snap.pgv_cm_s == pytest.approx(2.0)
