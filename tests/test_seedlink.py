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

    # Cada canal conserva sus chunks; los dos Z son contiguos (1001.0)
    assert len(source._chunks["Z"]) == 2
    assert len(source._chunks["N"]) == 1
    assert len(source._chunks["E"]) == 0
    assert source._ch_start["Z"] == pytest.approx(1000.0)
    assert source._ch_total["Z"] == 150
    assert source._ch_total["N"] == 80
    # latest_ts es el más reciente entre los end_ts (1001 + 50/100 = 1001.5)
    assert source._latest_ts == pytest.approx(1001.5)


# ============================================================
# Empaquetado y emisión alineada por tiempo
# ============================================================
def test_emit_waits_for_all_channels_then_emits_common_window(
    source: SeedLinkSource,
) -> None:
    received: list = []
    source.data_ready.connect(lambda batch: received.append(batch))

    # Z: 150 muestras (100 + 50) → end 1001.5; N: 100 → end 1101.0/100=...
    source._on_trace_received("Z", 1000.0, np.full(100, 1.0, dtype=np.float32), 100)
    source._on_trace_received("Z", 1001.0, np.full(50, 1.0, dtype=np.float32), 100)
    source._on_trace_received("N", 1000.0, np.full(100, 2.0, dtype=np.float32), 100)
    # E no ha enviado nada todavía.

    # Sin gracia (aún no han pasado 3 s) no se emite: hay que esperar a E.
    source._emit_pending()
    assert received == []

    # Forzamos la gracia (estación vertical-only / canal silencioso).
    source._first_data_wall = 0.0
    source._emit_pending()

    assert len(received) == 1
    batch = received[0]
    # Fin común = min(Z end 1001.5, N end 1001.0) → 100 muestras desde 1000.0
    assert batch.z.size == 100
    assert batch.n.size == 100
    assert batch.e.size == 100
    assert np.all(batch.z == 1.0)
    assert np.all(batch.n == 2.0)
    assert np.all(batch.e == 0.0)          # E rellenado con hold
    assert batch.timestamp_unix == pytest.approx(1001.0)
    # Z conserva las 50 muestras posteriores al fin común
    assert source._ch_total["Z"] == 50
    assert source._ch_total["N"] == 0
    # No hay nada más que emitir sin datos nuevos
    source._emit_pending()
    assert len(received) == 1


def test_emit_aligns_asynchronous_channels_by_time(
    source: SeedLinkSource,
) -> None:
    """Z empieza antes que N/E: la emisión arranca en el inicio más tardío
    y cada canal aporta solo su tramo correspondiente (sin duplicar tiempo).
    """

    received: list = []
    source.data_ready.connect(lambda batch: received.append(batch))

    source._on_trace_received(
        "Z", 1000.0, np.arange(100, dtype=np.float32), 100)
    source._on_trace_received(
        "N", 1000.5, np.full(100, 2.0, dtype=np.float32), 100)
    source._on_trace_received(
        "E", 1000.5, np.full(100, 3.0, dtype=np.float32), 100)

    source._emit_pending()

    assert len(received) == 1
    batch = received[0]
    # Ventana común [1000.5, 1001.0) → 50 muestras
    assert batch.z.size == 50
    assert np.all(batch.z == np.arange(50, 100, dtype=np.float32))
    assert np.all(batch.n == 2.0)
    assert np.all(batch.e == 3.0)
    assert batch.timestamp_unix == pytest.approx(1001.0)

    # La continuación: Z a 1001.0, N/E a 1001.5 (conservan 50 pendientes).
    source._on_trace_received(
        "Z", 1001.0, np.full(100, 4.0, dtype=np.float32), 100)
    source._on_trace_received(
        "N", 1001.5, np.full(100, 5.0, dtype=np.float32), 100)
    source._on_trace_received(
        "E", 1001.5, np.full(100, 6.0, dtype=np.float32), 100)
    source._emit_pending()

    assert len(received) == 2
    batch2 = received[1]
    assert batch2.timestamp_unix == pytest.approx(1002.0)
    # Z: 100 muestras nuevas (4.0)
    assert batch2.z.size == 100
    assert np.all(batch2.z == 4.0)
    # N/E: 50 pendientes del primer paquete + 50 del segundo
    assert np.all(batch2.n[:50] == 2.0)
    assert np.all(batch2.n[50:] == 5.0)
    assert np.all(batch2.e[:50] == 3.0)
    assert np.all(batch2.e[50:] == 6.0)


def test_gap_is_filled_with_hold_not_zeros(source: SeedLinkSource) -> None:
    """Un hueco de 0.9 s no debe crear un salto a cero."""

    received: list = []
    source.data_ready.connect(lambda batch: received.append(batch))

    source._on_trace_received(
        "Z", 1000.0, np.full(10, 1.0, dtype=np.float32), 100)
    # Siguiente paquete 0.9 s después (hueco), con valor 2.0
    source._on_trace_received(
        "Z", 1001.0, np.full(10, 2.0, dtype=np.float32), 100)

    assert source._ch_total["Z"] == 110   # 10 + 90 de hold + 10

    # Solo hay Z: forzamos la gracia para que emita sin esperar N/E.
    source._first_data_wall = 0.0
    source._emit_pending()
    assert len(received) == 1
    batch = received[0]
    assert batch.z.size == 110
    assert np.all(batch.z[:10] == 1.0)
    assert np.all(batch.z[10:100] == 1.0)   # hold con el último valor real
    assert np.all(batch.z[100:] == 2.0)
    assert batch.timestamp_unix == pytest.approx(1001.1)


def test_overlapping_packet_is_trimmed(source: SeedLinkSource) -> None:
    """Un paquete que repite 0.5 s ya recibidos no debe duplicarlos."""

    source._on_trace_received(
        "Z", 1000.0, np.ones(100, dtype=np.float32), 100)
    source._on_trace_received(
        "Z", 1000.5, np.full(100, 2.0, dtype=np.float32), 100)

    # 100 muestras iniciales + solo las 50 nuevas (se recortan 50 de solape)
    assert source._ch_total["Z"] == 150
    assert source._latest_ts == pytest.approx(1001.5)


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


# ============================================================
# Workaround del bug de ObsPy 1.5.1 (timeout=None en connect())
# ============================================================
def test_create_seedlink_client_uses_explicit_timeout(monkeypatch) -> None:
    """No usamos create_client(): fijamos timeout y conectamos a mano."""

    import obspy.clients.seedlink.easyseedlink as easyseedlink

    calls: dict = {}

    class _FakeConn:
        timeout = None

    class _FakeClient:
        def __init__(self, endpoint, autoconnect=True):
            calls["endpoint"] = endpoint
            calls["autoconnect"] = autoconnect
            self.conn = _FakeConn()
            self.on_data = None

        def connect(self):
            calls["connected"] = True

    monkeypatch.setattr(easyseedlink, "EasySeedLinkClient", _FakeClient)

    from shakevision.sources.seedlink import (
        SEEDLINK_HANDSHAKE_TIMEOUT_S,
        _create_seedlink_client,
    )

    client = _create_seedlink_client("host:18000", lambda _t: None)

    assert calls["endpoint"] == "host:18000"
    assert calls["autoconnect"] is False
    assert calls["connected"] is True
    assert client.conn.timeout == SEEDLINK_HANDSHAKE_TIMEOUT_S
    assert callable(client.on_data)
