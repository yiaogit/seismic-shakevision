"""
Fuente de datos de **reproducción histórica** (``ReplaySource``).

A diferencia de ``SeedLinkSource`` (datos en tiempo real) o
``MockSource`` (datos sintéticos), ``ReplaySource`` reproduce
muestras pre-grabadas que se descargaron previamente desde IRIS
dataselect (``services/dataselect.py``).

Diseño
------
* Entrada: un ``obspy.Stream`` con uno o varios Traces (Z, N, E),
  típicamente devuelto por ``DataselectClient.fetch_stream(...)``.
* Salida: misma interfaz que cualquier ``DataSource`` — emite
  ``SampleBatch`` a través de ``data_ready``. Esto permite reusar
  WaveformPanel / SpectrogramWidget / IntensityCard sin cambios.
* **Velocidad ajustable**: ``set_speed(factor)`` controla el ratio
  tiempo-real vs tiempo-reproducción. ``factor=1.0`` reproduce a
  velocidad real; ``factor=10.0`` reproduce 10× más rápido (un sismo
  de 5 minutos se ve en 30 s).
* **Pausa / reanudar / seek**: la reproducción es navegable. El
  cursor se expone como una propiedad para que la UI pinte la
  posición actual en la barra de progreso.
* Sin red, sin Qt en el generador: el motor central
  (``_ReplayClock``) es testeable sin instanciar ningún QObject.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np
from PySide6.QtCore import QObject, QTimer, Signal, Slot

from shakevision.sources.base import DataSource, SampleBatch

logger = logging.getLogger(__name__)


# Velocidades preestablecidas mostradas en el combo del Replay tab.
SPEED_OPTIONS: tuple[float, ...] = (0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0)
DEFAULT_SPEED: float = 1.0

# Intervalo del temporizador interno: cada cuánto emitimos un batch.
# Con factor=1 esto controla la "fineza" del scroll del waveform
# (50 ms ≈ 20 emits/s, suficiente para que se vea fluido).
EMIT_INTERVAL_MS: int = 50


# ============================================================
# Núcleo puro — sin Qt, testeable
# ============================================================
@dataclass
class _ReplayClock:
    """Reloj/cursor que decide qué porción del stream emitir.

    Mantiene:
      * ``cursor_s``      — posición actual relativa al inicio del clip
      * ``speed``         — factor de aceleración (1.0 = tiempo real)
      * ``duration_s``    — duración total del clip
      * ``paused``        — flag
      * ``last_real_t``   — wall-clock de la última llamada a tick()
        (para descontar el tiempo transcurrido en cuanto se reanuda)
    """

    duration_s: float
    speed: float = DEFAULT_SPEED
    cursor_s: float = 0.0
    paused: bool = False
    last_real_t: float = 0.0

    def tick(self, now: float) -> tuple[float, float]:
        """Avanza el cursor según el tiempo wall-clock transcurrido y
        devuelve ``(prev_cursor_s, new_cursor_s)``.

        Si está en pausa, el cursor no avanza pero se actualiza
        ``last_real_t`` para que al reanudar no haya un salto.
        """

        if self.last_real_t <= 0.0:
            self.last_real_t = now
            return self.cursor_s, self.cursor_s

        delta_real = now - self.last_real_t
        self.last_real_t = now
        if self.paused:
            return self.cursor_s, self.cursor_s

        prev = self.cursor_s
        self.cursor_s = min(self.duration_s, prev + delta_real * self.speed)
        return prev, self.cursor_s

    def seek_to(self, position_s: float) -> None:
        self.cursor_s = max(0.0, min(self.duration_s, position_s))

    def reset(self) -> None:
        self.cursor_s = 0.0
        self.last_real_t = 0.0

    @property
    def at_end(self) -> bool:
        return self.cursor_s >= self.duration_s


# ============================================================
# Helpers para trabajar con obspy.Stream sin importarlo a top-level
# ============================================================
def _stream_to_channels(stream) -> tuple[
    Optional[np.ndarray], Optional[np.ndarray], Optional[np.ndarray],
    float, int, float,
]:
    """Extrae arrays Z/N/E + start_ts + sample_rate + duration de un Stream.

    Asume que todos los Traces tienen el MISMO sample_rate y starttime
    (lo razonable para una sola descarga dataselect). Si difieren,
    usa el primer trace como referencia y rellena los otros con 0.
    """

    if stream is None or len(stream) == 0:
        return None, None, None, time.time(), 100, 0.0

    # Reference trace (el primero) define start_ts + sample_rate + length
    ref = stream[0]
    sample_rate = int(round(float(ref.stats.sampling_rate)))
    try:
        start_ts = float(ref.stats.starttime.timestamp)
    except Exception:  # noqa: BLE001
        start_ts = time.time()
    n_samples = int(ref.stats.npts)
    duration_s = n_samples / max(1, sample_rate)

    channels: dict[str, Optional[np.ndarray]] = {"Z": None, "N": None, "E": None}
    for tr in stream:
        ch = str(tr.stats.channel)[-1].upper()
        if ch not in channels:
            continue
        # Recorta / rellena para alinear con la longitud de referencia.
        data = np.asarray(tr.data, dtype=np.float32)
        if data.size < n_samples:
            padded = np.zeros(n_samples, dtype=np.float32)
            padded[: data.size] = data
            data = padded
        elif data.size > n_samples:
            data = data[:n_samples]
        channels[ch] = data

    return (channels["Z"], channels["N"], channels["E"],
            start_ts, sample_rate, duration_s)


# ============================================================
# DataSource
# ============================================================
class ReplaySource(DataSource):
    """Reproduce un Stream histórico como si fuera una conexión live.

    Ejemplo de uso:

        client = DataselectClient()
        stream = client.fetch_stream("IU", "ANMO", "00", "BH?",
                                     starttime=..., endtime=...)
        src = ReplaySource(stream=stream, speed=10.0,
                            station_label="IU.ANMO @ 2024-01-01")
        src.data_ready.connect(panel.update_batch)
        src.start()
    """

    # Señales adicionales específicas de Replay (no rompen la base).
    progress = Signal(float, float)   # (cursor_s, duration_s)
    finished = Signal()               # llegada al final del clip
    speed_changed = Signal(float)     # nuevo factor

    def __init__(
        self,
        stream,                                  # obspy.Stream
        speed: float = DEFAULT_SPEED,
        station_label: str = "Replay",
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._station_label = station_label

        (z, n, e, start_ts, sample_rate, duration_s) = _stream_to_channels(stream)
        self._z = z
        self._n = n
        self._e = e
        self._start_ts = start_ts
        self._sample_rate = sample_rate
        self._duration_s = duration_s

        self._clock = _ReplayClock(
            duration_s=duration_s,
            speed=max(0.01, float(speed)),
        )

        # Temporizador en el hilo de creación (UI). No es CPU-bound
        # (solo recorta np arrays), no necesita su propio QThread.
        self._timer = QTimer(self)
        self._timer.setInterval(EMIT_INTERVAL_MS)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------------
    # Metadatos
    # ------------------------------------------------------------------
    @property
    def station_label(self) -> str:
        return self._station_label

    @property
    def duration_seconds(self) -> float:
        return self._duration_s

    @property
    def cursor_seconds(self) -> float:
        return self._clock.cursor_s

    @property
    def speed(self) -> float:
        return self._clock.speed

    @property
    def is_paused(self) -> bool:
        return self._clock.paused

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------
    def start(self) -> None:
        if self._running:
            return
        if self._duration_s <= 0:
            # Emitimos i18n KEY; ReplayPanel la traduce con t().
            self.status_changed.emit("replay.status.empty_stream")
            return
        self._running = True
        self._clock.last_real_t = 0.0
        self._timer.start()
        self.status_changed.emit("replay.status.playing")

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._timer.stop()
        self._clock.reset()
        self.status_changed.emit("replay.status.stopped")
        self.progress.emit(0.0, self._duration_s)

    def pause(self) -> None:
        if not self._running or self._clock.paused:
            return
        self._clock.paused = True
        self.status_changed.emit("replay.status.paused")

    def resume(self) -> None:
        if not self._running or not self._clock.paused:
            return
        self._clock.paused = False
        self._clock.last_real_t = 0.0
        self.status_changed.emit("replay.status.resumed")

    def set_speed(self, factor: float) -> None:
        factor = max(0.01, float(factor))
        self._clock.speed = factor
        self.speed_changed.emit(factor)
        self.status_changed.emit("replay.status.speed_changed")

    def seek(self, position_s: float) -> None:
        self._clock.seek_to(position_s)
        # Resetear el reloj para no acumular delta entre cambios
        self._clock.last_real_t = 0.0
        self.progress.emit(self._clock.cursor_s, self._duration_s)

    # ------------------------------------------------------------------
    # Bucle de emisión
    # ------------------------------------------------------------------
    @Slot()
    def _tick(self) -> None:
        """Cada EMIT_INTERVAL_MS extrae el slice y emite SampleBatch."""

        now = time.monotonic()
        prev_s, cur_s = self._clock.tick(now)
        if self._clock.paused:
            return

        # Convertir segundos a índices de muestra
        start_idx = int(prev_s * self._sample_rate)
        end_idx = int(cur_s * self._sample_rate)
        if end_idx <= start_idx:
            # Velocidad pequeña + intervalo corto: aún no hay muestra nueva.
            return

        batch = SampleBatch(
            timestamp_unix=self._start_ts + prev_s,
            sample_rate_hz=self._sample_rate,
            z=_slice_or_zeros(self._z, start_idx, end_idx),
            n=_slice_or_zeros(self._n, start_idx, end_idx) if self._n is not None else None,
            e=_slice_or_zeros(self._e, start_idx, end_idx) if self._e is not None else None,
        )
        self.data_ready.emit(batch)
        self.progress.emit(cur_s, self._duration_s)

        # Fin del clip → parar automáticamente y notificar.
        if self._clock.at_end:
            self._timer.stop()
            self._running = False
            self.finished.emit()
            self.status_changed.emit("replay.status.completed")


# ============================================================
# Helpers
# ============================================================
def _slice_or_zeros(arr: Optional[np.ndarray], start: int, end: int) -> np.ndarray:
    """Devuelve ``arr[start:end]`` o zeros del tamaño correcto si arr es None."""

    n = max(0, end - start)
    if arr is None:
        return np.zeros(n, dtype=np.float32)
    # Recortar bounds — el clock puede pedir un end > len(arr) en el último tick.
    end = min(end, arr.size)
    start = min(start, end)
    out = arr[start:end]
    if out.size < n:
        # Rellenar al final si el slice quedó corto (fin del clip)
        padded = np.zeros(n, dtype=np.float32)
        padded[: out.size] = out
        return padded
    return out
