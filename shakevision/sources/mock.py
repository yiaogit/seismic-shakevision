"""
Fuente de datos simulada (``MockSource``).

Genera muestras sintéticas a la misma frecuencia que un Raspberry Shake
real (100 Hz por defecto). Sirve para:

  * desarrollar la UI sin depender de la red ni de un servidor SeedLink;
  * dar al usuario una "demo" inmediata al arrancar la aplicación;
  * tener un escenario reproducible para los tests automáticos.

Composición de la señal
-----------------------
Para que el oscilograma resulte visualmente interesante mezclamos:

  * **Microsismo oceánico**: senoide lenta de 0.2 Hz, amplitud baja.
  * **Ruido cultural**: senoide de 1 Hz, simula tráfico/industria.
  * **Ruido blanco**: gaussiano, simula el suelo de ruido del sensor.
  * **Eventos sintéticos**: cada ``event_period_s`` segundos se inyecta
    un pulso amortiguado tipo "P-wave", suficiente para que el detector
    STA/LTA dispare cuando se conecte en la fase 5.

La generación funciona en un ``QThread`` propio mediante un ``QTimer``
periódico. Esto reproduce fielmente el modelo del cliente SeedLink real
que escribiremos en la fase 4 (mismas señales Qt, misma vida útil).
"""

from __future__ import annotations

import time
from typing import Optional

import numpy as np
from PySide6.QtCore import QObject, QThread, QTimer, Slot

from shakevision.sources.base import DataSource, SampleBatch


# ============================================================
# Generador puro (sin Qt) — fácil de probar
# ============================================================
class _MockSignalGenerator:
    """Generador de muestras sintéticas reproducible y sin Qt.

    Mantiene un contador interno de muestras para que la señal sea
    continua entre bloques sucesivos (sin discontinuidades de fase).
    """

    def __init__(
        self,
        sample_rate_hz: int = 100,
        event_period_s: float = 30.0,
        seed: int = 42,
    ) -> None:
        self.sample_rate_hz = int(sample_rate_hz)
        self.event_period_samples = int(event_period_s * sample_rate_hz)
        self._sample_index = 0
        # Generador NumPy moderno (independiente del estado global)
        self._rng = np.random.default_rng(seed)

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def next_block(self, n: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Genera ``n`` muestras nuevas para los tres canales (Z, N, E)."""

        if n <= 0:
            empty = np.zeros(0, dtype=np.float32)
            return empty, empty, empty.copy()

        # Índices de muestra absolutos del bloque
        idx = np.arange(self._sample_index, self._sample_index + n, dtype=np.float64)
        t = idx / self.sample_rate_hz  # Tiempo en segundos

        # --- Componentes deterministas (compartidas por los 3 canales) ---
        microseism = 0.30 * np.sin(2.0 * np.pi * 0.20 * t)
        cultural   = 0.10 * np.sin(2.0 * np.pi * 1.00 * t)

        # --- Eventos periódicos (pulso amortiguado) ---
        events = self._compute_events(idx)

        # --- Ruido propio de cada canal ---
        noise_z = 0.05 * self._rng.standard_normal(n)
        noise_n = 0.05 * self._rng.standard_normal(n)
        noise_e = 0.05 * self._rng.standard_normal(n)

        # Composición final.
        # El canal Z (vertical) lleva la mayor parte del evento, como en
        # un sismo real: la onda P dominante es vertical.
        z = (microseism + cultural + events + noise_z).astype(np.float32)
        n_arr = (
            0.4 * microseism + 0.7 * cultural + 0.5 * events + noise_n
        ).astype(np.float32)
        e_arr = (
            0.4 * microseism + 0.7 * cultural + 0.5 * events + noise_e
        ).astype(np.float32)

        # Avanzar el contador para la siguiente llamada
        self._sample_index += n

        return z, n_arr, e_arr

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------
    def _compute_events(self, idx: np.ndarray) -> np.ndarray:
        """Inserta pulsos amortiguados periódicos.

        Un "evento" arranca cada ``event_period_samples`` y dura unos
        ~6 segundos: senoide de 3 Hz multiplicada por una envolvente
        exponencial decreciente.
        """

        period = self.event_period_samples
        # Tiempo (en segundos) desde el último evento anterior
        local_idx = idx % period
        seconds_since_event = local_idx / self.sample_rate_hz

        envelope = np.exp(-seconds_since_event / 2.0)
        carrier  = np.sin(2.0 * np.pi * 3.0 * seconds_since_event)
        event = 1.4 * envelope * carrier

        # Solo durante los primeros 6 s del ciclo: pasado ese punto la
        # envolvente ya es despreciable, pero anulamos explícitamente.
        event[seconds_since_event > 6.0] = 0.0
        return event


# ============================================================
# Fuente de datos basada en Qt
# ============================================================
class MockSource(DataSource):
    """Fuente de datos simulada compatible con la interfaz ``DataSource``.

    Implementación con ``QThread`` propio + ``QTimer`` periódico. Cada
    ``block_interval_ms`` milisegundos genera un bloque de muestras y
    emite ``data_ready``. La fuente puede arrancarse y detenerse varias
    veces de forma segura.
    """

    def __init__(
        self,
        sample_rate_hz: int = 100,
        block_size: int = 10,
        seed: int = 42,
        station_label: str = "Demo (datos simulados)",
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)

        self._sample_rate = int(sample_rate_hz)
        self._block_size = int(block_size)
        # Periodo del temporizador en milisegundos:
        # con block_size = 10 muestras y 100 Hz, son 100 ms por bloque.
        self._interval_ms = int(1000 * self._block_size / self._sample_rate)
        self._station_label = station_label

        # Generador determinista. Vive en el hilo trabajador.
        self._generator = _MockSignalGenerator(
            sample_rate_hz=self._sample_rate, seed=seed
        )

        # Objetos Qt creados perezosamente al llamar a ``start``
        self._thread: QThread | None = None
        self._timer: QTimer | None = None

    # ------------------------------------------------------------------
    # Metadatos
    # ------------------------------------------------------------------
    @property
    def station_label(self) -> str:
        return self._station_label

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------
    def start(self) -> None:
        """Arranca el hilo trabajador y comienza a emitir muestras."""

        if self._running:
            return

        # Crear hilo dedicado para no bloquear la UI
        self._thread = QThread()
        # Movernos al hilo: los slots se ejecutarán en él
        self.moveToThread(self._thread)

        # Cuando el hilo arranque, crear el temporizador EN ese hilo.
        self._thread.started.connect(self._on_thread_started)
        # Cuando el hilo termine, limpiar el temporizador.
        self._thread.finished.connect(self._on_thread_finished)

        self._running = True
        self.status_changed.emit("Fuente simulada iniciada (100 Hz).")
        self._thread.start()

    def stop(self) -> None:
        """Detiene la emisión y libera el hilo trabajador."""

        if not self._running or self._thread is None:
            return

        self._running = False
        # Pedir al hilo que termine su bucle de eventos. La limpieza se
        # hace en ``_on_thread_finished``.
        self._thread.quit()
        # Bloquear hasta que termine (con un tope de seguridad de 2 s)
        self._thread.wait(2000)
        # ``moveToThread(None)`` devuelve el objeto al hilo principal
        # para que pueda volver a arrancarse más tarde.
        self.moveToThread(QThread.currentThread())
        self._thread = None
        self.status_changed.emit("Fuente simulada detenida.")

    # ------------------------------------------------------------------
    # Slots ejecutados en el hilo trabajador
    # ------------------------------------------------------------------
    @Slot()
    def _on_thread_started(self) -> None:
        """Inicializa el temporizador dentro del hilo trabajador."""

        self._timer = QTimer()
        self._timer.setInterval(self._interval_ms)
        self._timer.timeout.connect(self._emit_block)
        self._timer.start()

    @Slot()
    def _on_thread_finished(self) -> None:
        """Detiene y libera el temporizador al apagar el hilo."""

        if self._timer is not None:
            self._timer.stop()
            self._timer.deleteLater()
            self._timer = None

    @Slot()
    def _emit_block(self) -> None:
        """Genera un nuevo bloque de muestras y lo emite."""

        z, n, e = self._generator.next_block(self._block_size)
        batch = SampleBatch(
            timestamp_unix=time.time(),
            sample_rate_hz=self._sample_rate,
            z=z,
            n=n,
            e=e,
        )
        # ``data_ready`` se emite desde el hilo trabajador; al estar
        # conectada con conexión por cola (la conexión por defecto entre
        # hilos), Qt la entrega de forma segura en el hilo de la UI.
        self.data_ready.emit(batch)
