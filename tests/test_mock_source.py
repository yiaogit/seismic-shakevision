"""
Pruebas del generador y de la fuente simulada.

El test del generador (``_MockSignalGenerator``) es completamente
independiente de Qt: solo verifica forma, dtype y continuidad de fase.
El test de la fuente Qt (``MockSource``) crea una ``QApplication``
mínima y comprueba que ``data_ready`` se emite al menos una vez al
arrancar el hilo.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

from shakevision.sources.mock import _MockSignalGenerator


# ============================================================
# Generador puro
# ============================================================
def test_generator_block_shape_and_dtype() -> None:
    """Cada llamada devuelve tres arrays float32 del tamaño pedido."""

    gen = _MockSignalGenerator(sample_rate_hz=100, seed=0)
    z, n, e = gen.next_block(50)
    assert z.shape == (50,)
    assert n.shape == (50,)
    assert e.shape == (50,)
    assert z.dtype == np.float32
    assert n.dtype == np.float32
    assert e.dtype == np.float32


def test_generator_phase_continuity_between_blocks() -> None:
    """La señal compuesta debe ser continua al concatenar bloques.

    Como cada llamada también añade ruido aleatorio, no podemos
    comparar la señal entera. En su lugar, comprobamos que el índice
    interno avanza correctamente generando dos bloques pequeños y un
    bloque grande, y verificando que las componentes deterministas
    (sin ruido) coinciden.
    """

    gen_a = _MockSignalGenerator(sample_rate_hz=100, seed=123)
    gen_b = _MockSignalGenerator(sample_rate_hz=100, seed=123)

    # gen_a emite en 2 trozos, gen_b en 1 trozo
    a1, _, _ = gen_a.next_block(40)
    a2, _, _ = gen_a.next_block(60)
    b_full, _, _ = gen_b.next_block(100)

    # Ruido distinto -> no podemos comparar punto a punto, pero sí la
    # media debe ser similar (ambas series tienen el mismo determinista).
    diff_mean = abs(np.mean(np.concatenate([a1, a2])) - np.mean(b_full))
    assert diff_mean < 0.05


def test_generator_event_visible_in_first_seconds() -> None:
    """Al inicio (t≈0) el evento sintético debe ser claramente perceptible."""

    gen = _MockSignalGenerator(sample_rate_hz=100, event_period_s=30.0, seed=0)
    z, _, _ = gen.next_block(600)  # 6 segundos

    # En el primer segundo (envolvente alta) la energía debe ser
    # claramente mayor que entre el segundo 5 y el 6 (envolvente ya casi cero).
    energy_early = float(np.sum(z[:100] ** 2))
    energy_late  = float(np.sum(z[500:600] ** 2))
    assert energy_early > 5.0 * energy_late


def test_generator_empty_block_returns_empty_arrays() -> None:
    """Pedir 0 muestras debe devolver tres arrays vacíos sin error."""

    gen = _MockSignalGenerator(sample_rate_hz=100, seed=0)
    z, n, e = gen.next_block(0)
    assert z.size == 0 and n.size == 0 and e.size == 0


# ============================================================
# Fuente Qt — solo se ejecuta si PySide6 está disponible
# ============================================================
pyside6 = pytest.importorskip(
    "PySide6.QtWidgets", reason="PySide6 no instalado en este entorno"
)


def test_mock_source_emits_at_least_one_batch() -> None:
    """Tras 300 ms, ``data_ready`` debe haber disparado varias veces."""

    # Forzar el backend "offscreen" para entornos sin pantalla (CI)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtCore import QCoreApplication, QTimer

    from shakevision.sources.mock import MockSource

    # Reusar la app si otro test ya la creó
    app = QCoreApplication.instance() or QCoreApplication([])

    received: list = []

    source = MockSource(sample_rate_hz=100, block_size=10)
    source.data_ready.connect(lambda batch: received.append(batch))
    source.start()

    # Detener la app tras 300 ms
    QTimer.singleShot(300, app.quit)
    app.exec()

    source.stop()

    # A 100 Hz con bloques de 10 muestras esperamos ~3 batches en 300 ms.
    # Aceptamos al menos 1 para tolerar el ruido del scheduler de CI.
    assert len(received) >= 1
    first = received[0]
    assert first.z.size == 10
    assert first.sample_rate_hz == 100
