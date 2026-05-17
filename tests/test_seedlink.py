"""
Pruebas de la lógica de empaquetado de ``SeedLinkSource``.

No conectamos a un servidor real (sería frágil en CI). En su lugar,
validamos directamente:
  * el método estático ``_pad_left`` (relleno con ceros a la izquierda);
  * el slot ``_on_trace_received`` acumula correctamente por canal;
  * el slot ``_emit_pending`` agrupa los traces y respeta la longitud
    máxima entre canales.

Para evitar depender de PySide6 en entornos sin pantalla, los tests
usan ``pytest.importorskip`` y solo se ejecutan cuando el binding está
disponible. En CI sí lo está, así que estos tests corren en los tres
sistemas operativos.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

# Evitar abrir ventana real en entornos sin display
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6.QtWidgets", reason="PySide6 no instalado")
pytest.importorskip("obspy", reason="ObsPy no instalado")  # noqa: F841

from PySide6.QtCore import QCoreApplication  # noqa: E402

from shakevision.sources.seedlink import SeedLinkSource  # noqa: E402


# ============================================================
# Helper: aplicación Qt compartida
# ============================================================
@pytest.fixture(scope="module")
def qt_app():
    app = QCoreApplication.instance() or QCoreApplication([])
    yield app


@pytest.fixture
def source(qt_app):
    """Construye una fuente sin arrancarla (no abre socket)."""

    src = SeedLinkSource(
        host="localhost",
        port=18000,
        network="AM",
        station="MOCK",
        sample_rate_hz=100,
        station_label="MOCK_TEST",
    )
    yield src
    # Aseguramos que el temporizador no quede activo entre tests
    src._emit_timer.stop()


# ============================================================
# _pad_left
# ============================================================
def test_pad_left_extends_short_arrays() -> None:
    arr = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    out = SeedLinkSource._pad_left(arr, 6)
    assert out.shape == (6,)
    # Los ceros van al inicio, los valores quedan al final
    assert np.array_equal(out, np.array([0, 0, 0, 1, 2, 3], dtype=np.float32))


def test_pad_left_truncates_long_arrays() -> None:
    arr = np.arange(10, dtype=np.float32)
    out = SeedLinkSource._pad_left(arr, 4)
    # Conserva los últimos 4 valores
    assert np.array_equal(out, np.array([6, 7, 8, 9], dtype=np.float32))


def test_pad_left_returns_same_when_lengths_match() -> None:
    arr = np.arange(5, dtype=np.float32)
    out = SeedLinkSource._pad_left(arr, 5)
    assert out is arr  # mismo objeto, sin copia


# ============================================================
# Acumulación por canal
# ============================================================
def test_on_trace_received_accumulates_by_channel(source: SeedLinkSource) -> None:
    z1 = np.ones(100, dtype=np.float32)
    z2 = np.full(50, 2.0, dtype=np.float32)
    n1 = np.full(80, 3.0, dtype=np.float32)

    source._on_trace_received("Z", 1000.0, z1, 100)
    source._on_trace_received("Z", 1001.0, z2, 100)
    source._on_trace_received("N", 1000.0, n1, 100)

    # Los acumuladores conservan los chunks separados (no concatenados)
    assert len(source._chunks["Z"]) == 2
    assert len(source._chunks["N"]) == 1
    assert len(source._chunks["E"]) == 0
    # latest_ts es el más reciente entre los end_ts (1001 + 50/100 = 1001.5)
    assert source._latest_ts == pytest.approx(1001.5)


# ============================================================
# Empaquetado y emisión
# ============================================================
def test_emit_pending_combines_chunks_and_pads(source: SeedLinkSource) -> None:
    received: list = []
    source.data_ready.connect(lambda batch: received.append(batch))

    # Z: 150 muestras (100 + 50)
    source._on_trace_received("Z", 1000.0, np.full(100, 1.0, dtype=np.float32), 100)
    source._on_trace_received("Z", 1001.0, np.full(50, 1.0, dtype=np.float32), 100)
    # N: 100 muestras
    source._on_trace_received("N", 1000.0, np.full(100, 2.0, dtype=np.float32), 100)
    # E: nada (canal silencioso, p. ej. estación de un solo eje)

    source._emit_pending()

    assert len(received) == 1
    batch = received[0]
    # Longitud máxima = 150 -> los tres canales acaban con 150 muestras
    assert batch.z.size == 150
    assert batch.n.size == 150
    assert batch.e.size == 150
    # Z lleno de unos en sus 150 elementos
    assert np.all(batch.z == 1.0)
    # N rellenado con ceros al inicio (longitud 150 pero solo 100 datos reales)
    assert np.all(batch.n[:50] == 0.0)
    assert np.all(batch.n[50:] == 2.0)
    # E completamente cero
    assert np.all(batch.e == 0.0)
    # timestamp_unix coincide con el último end_ts registrado
    assert batch.timestamp_unix == pytest.approx(1001.5)
    # Los acumuladores se vacían tras emitir
    assert source._chunks["Z"] == []
    assert source._chunks["N"] == []


def test_emit_pending_does_nothing_when_empty(source: SeedLinkSource) -> None:
    received: list = []
    source.data_ready.connect(lambda batch: received.append(batch))
    source._emit_pending()
    assert received == []


# ============================================================
# Filtrado de canales no soportados
# ============================================================
def test_unknown_channel_letters_are_ignored(source: SeedLinkSource) -> None:
    """Letras como 'X' (inexistentes en nuestro modelo) no deben acumular."""

    # Llamamos al callback interno simulando un trace exótico
    fake_samples = np.zeros(10, dtype=np.float32)

    class _FakeStats:
        channel = "EHX"
        sampling_rate = 100.0

        class starttime:  # imita UTCDateTime
            timestamp = 0.0

    class _FakeTrace:
        stats = _FakeStats()
        data = fake_samples

    # Llamada como lo haría ObsPy
    source._worker._on_trace(_FakeTrace())
    # Como _on_trace emite la señal en el hilo del worker pero estamos
    # en el principal, y el worker no se ha movido aún a otro hilo en
    # este test, el slot _on_trace_received NO se invoca (la conexión
    # es DirectConnection por defecto si están en el mismo hilo).
    # El canal 'X' es rechazado dentro de _on_trace antes de emitir.
    assert all(len(v) == 0 for v in source._chunks.values())
