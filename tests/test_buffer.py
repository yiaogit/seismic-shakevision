"""
Pruebas del búfer circular ``RingBuffer``.

Cubren los casos básicos (escritura, lectura, envoltura) y un caso de
acceso concurrente para detectar regresiones en la sincronización.
"""

from __future__ import annotations

import threading

import numpy as np
import pytest

from shakevision.processing.buffer import BufferSnapshot, RingBuffer


# ============================================================
# Construcción
# ============================================================
def test_constructor_validates_arguments() -> None:
    """Tasas o capacidades no positivas deben rechazarse."""

    with pytest.raises(ValueError):
        RingBuffer(sample_rate_hz=0, capacity_seconds=10)
    with pytest.raises(ValueError):
        RingBuffer(sample_rate_hz=100, capacity_seconds=0)


def test_capacity_matches_rate_times_seconds() -> None:
    """La capacidad debe ser exactamente ``rate * seconds``."""

    buf = RingBuffer(sample_rate_hz=100, capacity_seconds=5)
    assert buf.capacity == 500
    assert buf.sample_rate_hz == 100
    assert buf.available == 0
    assert buf.total_written == 0


# ============================================================
# Escritura básica
# ============================================================
def test_write_increments_counters() -> None:
    """Tras escribir 30 muestras, ``available`` debe ser 30."""

    buf = RingBuffer(sample_rate_hz=100, capacity_seconds=10)
    z = np.arange(30, dtype=np.float32)
    buf.write(timestamp_unix=1000.0, z=z, n=z, e=z)

    assert buf.total_written == 30
    assert buf.available == 30
    assert buf.latest_timestamp_unix == pytest.approx(1000.0)


def test_write_with_optional_channels_fills_with_zeros() -> None:
    """Cuando falta N o E debe rellenarse con ceros, no propagar None."""

    buf = RingBuffer(sample_rate_hz=100, capacity_seconds=10)
    z = np.ones(10, dtype=np.float32)
    buf.write(timestamp_unix=1.0, z=z)  # n y e omitidos

    snap = buf.read_window(seconds=0.1)  # 10 muestras
    assert np.allclose(snap.samples["Z"], 1.0)
    assert np.allclose(snap.samples["N"], 0.0)
    assert np.allclose(snap.samples["E"], 0.0)


def test_write_rejects_mismatched_channel_lengths() -> None:
    """Si los tres canales no tienen la misma longitud debe lanzar."""

    buf = RingBuffer(sample_rate_hz=100, capacity_seconds=10)
    z = np.zeros(10, dtype=np.float32)
    n = np.zeros(9, dtype=np.float32)  # desajuste deliberado
    e = np.zeros(10, dtype=np.float32)

    with pytest.raises(ValueError):
        buf.write(timestamp_unix=0.0, z=z, n=n, e=e)


# ============================================================
# Envoltura (wrap-around)
# ============================================================
def test_wraparound_preserves_recent_samples() -> None:
    """Tras llenar el búfer y volver a escribir, debemos ver las nuevas."""

    buf = RingBuffer(sample_rate_hz=100, capacity_seconds=1)  # cap = 100
    # Llenar con valores 0..99
    first = np.arange(100, dtype=np.float32)
    buf.write(timestamp_unix=0.0, z=first, n=first, e=first)

    # Escribir 30 valores nuevos (100..129) — fuerza envoltura
    second = np.arange(100, 130, dtype=np.float32)
    buf.write(timestamp_unix=1.0, z=second, n=second, e=second)

    assert buf.total_written == 130
    assert buf.available == 100  # acotado por la capacidad

    # La ventana de las últimas 30 muestras debe contener 100..129
    snap = buf.read_window(seconds=0.30)  # 30 muestras
    assert snap.samples["Z"].size == 30
    assert np.array_equal(snap.samples["Z"], second)


def test_block_larger_than_capacity_keeps_tail() -> None:
    """Si el bloque excede la capacidad, conservamos las últimas muestras."""

    buf = RingBuffer(sample_rate_hz=100, capacity_seconds=1)  # cap = 100
    big = np.arange(250, dtype=np.float32)
    buf.write(timestamp_unix=0.0, z=big, n=big, e=big)

    snap = buf.read_window(seconds=1.0)  # 100 muestras
    # Las últimas 100 de 0..249 son 150..249
    expected_tail = np.arange(150, 250, dtype=np.float32)
    assert np.array_equal(snap.samples["Z"], expected_tail)


# ============================================================
# Lectura
# ============================================================
def test_read_window_pads_with_zeros_when_not_enough_data() -> None:
    """Si pedimos más de lo escrito, los huecos quedan a cero a la izquierda."""

    buf = RingBuffer(sample_rate_hz=100, capacity_seconds=10)
    z = np.full(20, 7.0, dtype=np.float32)
    buf.write(timestamp_unix=0.0, z=z, n=z, e=z)

    snap = buf.read_window(seconds=1.0)  # pedimos 100, hay 20
    assert isinstance(snap, BufferSnapshot)
    assert snap.samples["Z"].size == 100
    assert np.all(snap.samples["Z"][:80] == 0.0)
    assert np.all(snap.samples["Z"][80:] == 7.0)


def test_read_window_axis_is_relative_seconds() -> None:
    """El eje de tiempos termina en 0 y va hacia atrás."""

    buf = RingBuffer(sample_rate_hz=100, capacity_seconds=10)
    snap = buf.read_window(seconds=1.0)
    assert snap.times[-1] == pytest.approx(0.0)
    assert snap.times[0] == pytest.approx(-0.99, abs=1e-3)


def test_clear_resets_state() -> None:
    """``clear`` debe poner los contadores a cero y los datos a cero."""

    buf = RingBuffer(sample_rate_hz=100, capacity_seconds=10)
    z = np.full(50, 5.0, dtype=np.float32)
    buf.write(timestamp_unix=10.0, z=z, n=z, e=z)
    buf.clear()
    assert buf.total_written == 0
    assert buf.available == 0
    assert buf.latest_timestamp_unix == 0.0
    snap = buf.read_window(seconds=0.5)
    assert np.all(snap.samples["Z"] == 0.0)


# ============================================================
# Concurrencia
# ============================================================
def test_concurrent_writes_do_not_corrupt_counter() -> None:
    """Múltiples hilos escribiendo no deben perder muestras."""

    buf = RingBuffer(sample_rate_hz=1000, capacity_seconds=10)  # cap grande
    block = np.ones(50, dtype=np.float32)

    def worker(n_iter: int) -> None:
        for _ in range(n_iter):
            buf.write(timestamp_unix=0.0, z=block, n=block, e=block)

    threads = [threading.Thread(target=worker, args=(20,)) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 8 hilos × 20 iteraciones × 50 muestras = 8000
    assert buf.total_written == 8 * 20 * 50
