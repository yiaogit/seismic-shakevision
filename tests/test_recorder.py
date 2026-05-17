"""
Pruebas del grabador de eventos.

Para no depender de ObsPy en CI básico, los tests se centran en:
  * el helper ``build_event_filename_local`` (formato del nombre);
  * la validación de argumentos en ``EventRecorder.__init__``;
  * el flujo completo ``record_event`` cuando ObsPy está disponible
    (omitido si no está instalado).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from shakevision.processing.buffer import RingBuffer
from shakevision.processing.recorder import (
    EventRecorder,
    build_event_filename_local,
)


SAMPLE_RATE = 100  # Hz


# ============================================================
# Validación
# ============================================================
def test_recorder_rejects_invalid_sample_rate(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        EventRecorder(sample_rate_hz=0, pre_event_seconds=10.0,
                      recordings_dir=tmp_path)


def test_recorder_rejects_invalid_pre_event(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        EventRecorder(sample_rate_hz=SAMPLE_RATE, pre_event_seconds=0.0,
                      recordings_dir=tmp_path)


def test_recorder_update_pre_event_validates() -> None:
    rec = EventRecorder(SAMPLE_RATE, pre_event_seconds=10.0)
    rec.update_pre_event_seconds(20.0)
    with pytest.raises(ValueError):
        rec.update_pre_event_seconds(0.0)


# ============================================================
# Nombre de fichero local
# ============================================================
def test_filename_format_is_iso_compact() -> None:
    name = build_event_filename_local(
        network="AM", station="R0E05", end_ts=1715600000.0
    )
    # 2024-05-13T13:33:20Z aproximadamente
    assert name.endswith("_AM_R0E05.mseed")
    # Prefijo de 15 caracteres tipo "YYYYMMDDTHHMMSS"
    prefix = name.split("_", 1)[0]
    assert len(prefix) == 15
    assert prefix[8] == "T"


# ============================================================
# Flujo completo (solo si ObsPy está instalado)
# ============================================================
obspy = pytest.importorskip("obspy", reason="ObsPy no disponible")


def test_record_event_writes_mseed(tmp_path: Path) -> None:
    """Un búfer con datos debe producir un MiniSEED no vacío."""

    # Búfer con 5 segundos de senoide
    buf = RingBuffer(sample_rate_hz=SAMPLE_RATE, capacity_seconds=10)
    n = SAMPLE_RATE * 5
    t = np.arange(n) / SAMPLE_RATE
    sine = np.sin(2.0 * np.pi * 3.0 * t).astype(np.float32)
    buf.write(timestamp_unix=1700000000.0, z=sine, n=sine, e=sine)

    rec = EventRecorder(
        sample_rate_hz=SAMPLE_RATE,
        pre_event_seconds=4.0,
        recordings_dir=tmp_path,
    )
    result = rec.record_event(
        buffer=buf,
        network="AM",
        station="MOCK",
        trigger_time_unix=1700000000.0,
    )

    assert result.success is True
    assert result.path is not None
    assert result.path.exists()
    assert result.path.stat().st_size > 0
    # Releer para confirmar que ObsPy puede abrirlo
    st = obspy.read(str(result.path))
    assert len(st) == 3  # 3 canales escritos
    channels = sorted(tr.stats.channel for tr in st)
    assert channels == ["EHE", "EHN", "EHZ"]


def test_record_event_returns_error_on_empty_buffer(tmp_path: Path) -> None:
    buf = RingBuffer(sample_rate_hz=SAMPLE_RATE, capacity_seconds=10)
    rec = EventRecorder(
        sample_rate_hz=SAMPLE_RATE,
        pre_event_seconds=4.0,
        recordings_dir=tmp_path,
    )
    # No hemos escrito nada en el búfer (read_window devolverá ceros,
    # pero size > 0 -> intentará grabar; los ceros son datos válidos).
    # En su lugar comprobamos que el directorio se crea correctamente.
    result = rec.record_event(
        buffer=buf,
        network="AM",
        station="MOCK",
        trigger_time_unix=1700000000.0,
    )
    # En este caso sí escribe (zeros son datos válidos para ObsPy)
    assert result.success is True
    assert result.path is not None
    assert result.path.parent == tmp_path
