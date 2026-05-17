"""
Búfer circular multicanal para muestras sísmicas en tiempo real.

Diseño
------
La aplicación adquiere muestras a 100 Hz (típico de Raspberry Shake) en
un hilo de adquisición y las consume a 30 FPS desde el hilo de la UI.
Para acoplar ambas velocidades sin descartar muestras y sin reasignar
memoria continuamente, usamos un búfer circular respaldado por un
``numpy.ndarray`` por canal.

Características
---------------
- Capacidad fija = ``sample_rate_hz × buffer_seconds`` (5 min ≈ 30 000
  muestras a 100 Hz, unos 240 KiB por canal — despreciable).
- Escritura ``O(k)`` para un bloque de tamaño ``k`` (típicamente 10).
- Lectura del último tramo con copia contigua en ``O(n)`` para
  alimentar fácilmente a PyQtGraph (que prefiere arrays contiguos).
- Seguridad ante accesos concurrentes mediante ``threading.Lock``.
- Marca de tiempo monotónica del último bloque escrito, útil para
  estimar la latencia de la fuente.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

import numpy as np


# Canales soportados; el orden importa porque corresponde al índice
# interno de la matriz ``_data`` (Z=0, N=1, E=2).
CHANNELS: tuple[str, ...] = ("Z", "N", "E")


@dataclass
class BufferSnapshot:
    """Vista inmutable de una ventana reciente del búfer.

    ``times`` está en segundos relativos al instante actual: 0 es la
    muestra más reciente y los valores son negativos hacia el pasado.
    Esto facilita pintar el eje X del oscilograma sin tener que
    preocuparse por la hora UTC.
    """

    times: np.ndarray            # Eje temporal (segundos, ≤ 0)
    samples: dict[str, np.ndarray]
    latest_timestamp_unix: float  # Timestamp de la muestra más reciente


class RingBuffer:
    """Búfer circular de tres canales con seguridad entre hilos."""

    def __init__(self, sample_rate_hz: int, capacity_seconds: int) -> None:
        if sample_rate_hz <= 0:
            raise ValueError("La frecuencia de muestreo debe ser positiva")
        if capacity_seconds <= 0:
            raise ValueError("La capacidad debe ser positiva")

        self._sample_rate = int(sample_rate_hz)
        self._capacity = int(sample_rate_hz * capacity_seconds)

        # Una fila por canal. Inicializamos a cero para que la lectura
        # antes de tener muestras devuelva una traza plana, no NaN.
        self._data: np.ndarray = np.zeros(
            (len(CHANNELS), self._capacity), dtype=np.float32
        )

        # Número total de muestras escritas (no acotado por la capacidad).
        # Sirve para calcular el desplazamiento real y para tests.
        self._total_written: int = 0

        # Marca de tiempo Unix de la muestra MÁS RECIENTE escrita.
        self._latest_timestamp_unix: float = 0.0

        # Cerrojo para escrituras concurrentes (hilo de adquisición vs UI).
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Propiedades de solo lectura
    # ------------------------------------------------------------------
    @property
    def capacity(self) -> int:
        """Número total de muestras que caben en el búfer (por canal)."""

        return self._capacity

    @property
    def sample_rate_hz(self) -> int:
        """Frecuencia de muestreo configurada."""

        return self._sample_rate

    @property
    def available(self) -> int:
        """Número de muestras válidas escritas hasta ahora (acotado por la capacidad)."""

        with self._lock:
            return min(self._total_written, self._capacity)

    @property
    def latest_timestamp_unix(self) -> float:
        """Timestamp Unix de la muestra más reciente (0 si aún no hay datos)."""

        with self._lock:
            return self._latest_timestamp_unix

    @property
    def total_written(self) -> int:
        """Número total de muestras escritas (no acotado)."""

        with self._lock:
            return self._total_written

    # ------------------------------------------------------------------
    # Escritura
    # ------------------------------------------------------------------
    def write(
        self,
        timestamp_unix: float,
        z: np.ndarray,
        n: np.ndarray | None = None,
        e: np.ndarray | None = None,
    ) -> None:
        """Añade un bloque de muestras al búfer.

        ``timestamp_unix`` debe ser el instante (en segundos Unix) de la
        ÚLTIMA muestra del bloque. Los canales ``n`` y ``e`` son
        opcionales para soportar estaciones de un solo canal (RS1D):
        en ese caso se escriben ceros en los huecos.
        """

        # Convertir a float32 una sola vez y comprobar longitudes
        z_arr = np.asarray(z, dtype=np.float32).reshape(-1)
        block_size = z_arr.size
        if block_size == 0:
            return  # Nada que hacer

        # Si faltan los canales horizontales, rellenamos con ceros.
        n_arr = (
            np.asarray(n, dtype=np.float32).reshape(-1)
            if n is not None
            else np.zeros(block_size, dtype=np.float32)
        )
        e_arr = (
            np.asarray(e, dtype=np.float32).reshape(-1)
            if e is not None
            else np.zeros(block_size, dtype=np.float32)
        )

        if n_arr.size != block_size or e_arr.size != block_size:
            raise ValueError(
                "Los tres canales deben tener el mismo número de muestras"
            )

        # Si el bloque es más grande que el búfer entero, conservamos
        # únicamente la cola (los datos antiguos se perderían igualmente).
        if block_size >= self._capacity:
            z_arr = z_arr[-self._capacity :]
            n_arr = n_arr[-self._capacity :]
            e_arr = e_arr[-self._capacity :]
            block_size = self._capacity

        with self._lock:
            # Posición de escritura módulo la capacidad
            start = self._total_written % self._capacity
            end = start + block_size

            if end <= self._capacity:
                # Cabe de una sola pieza
                self._data[0, start:end] = z_arr
                self._data[1, start:end] = n_arr
                self._data[2, start:end] = e_arr
            else:
                # Se produce envoltura: dividir en dos segmentos
                first = self._capacity - start
                self._data[0, start:] = z_arr[:first]
                self._data[1, start:] = n_arr[:first]
                self._data[2, start:] = e_arr[:first]
                self._data[0, : end - self._capacity] = z_arr[first:]
                self._data[1, : end - self._capacity] = n_arr[first:]
                self._data[2, : end - self._capacity] = e_arr[first:]

            self._total_written += block_size
            self._latest_timestamp_unix = float(timestamp_unix)

    # ------------------------------------------------------------------
    # Lectura
    # ------------------------------------------------------------------
    def read_window(self, seconds: float) -> BufferSnapshot:
        """Devuelve la ventana más reciente de ``seconds`` segundos.

        Si todavía no hay suficientes datos, la ventana se rellena
        con ceros a la izquierda para mantener una longitud constante.
        """

        if seconds <= 0:
            raise ValueError("La ventana debe ser positiva")

        n_samples = int(round(seconds * self._sample_rate))
        if n_samples > self._capacity:
            n_samples = self._capacity

        # Eje temporal: 0 = muestra más reciente, valores negativos hacia el pasado.
        times = np.arange(-n_samples + 1, 1, dtype=np.float32) / self._sample_rate

        with self._lock:
            # Posición justo después de la última muestra escrita
            write_pos = self._total_written % self._capacity
            valid = min(self._total_written, n_samples)

            # Si aún no hay datos, devolver ceros
            if valid == 0:
                samples = {
                    "Z": np.zeros(n_samples, dtype=np.float32),
                    "N": np.zeros(n_samples, dtype=np.float32),
                    "E": np.zeros(n_samples, dtype=np.float32),
                }
                return BufferSnapshot(
                    times=times,
                    samples=samples,
                    latest_timestamp_unix=self._latest_timestamp_unix,
                )

            # Posición de inicio de la lectura (envuelta)
            start = (write_pos - valid) % self._capacity

            # Extraer cada canal contiguo (gestionando envoltura)
            out = np.zeros((len(CHANNELS), n_samples), dtype=np.float32)
            if start + valid <= self._capacity:
                # De una pieza
                out[:, n_samples - valid :] = self._data[:, start : start + valid]
            else:
                # Dos piezas (cola del array + cabeza)
                first = self._capacity - start
                out[:, n_samples - valid : n_samples - valid + first] = self._data[
                    :, start:
                ]
                out[:, n_samples - valid + first :] = self._data[: , : valid - first]

            latest_ts = self._latest_timestamp_unix

        return BufferSnapshot(
            times=times,
            samples={
                "Z": out[0],
                "N": out[1],
                "E": out[2],
            },
            latest_timestamp_unix=latest_ts,
        )

    # ------------------------------------------------------------------
    # Mantenimiento
    # ------------------------------------------------------------------
    def clear(self) -> None:
        """Vacía completamente el búfer (útil al cambiar de estación)."""

        with self._lock:
            self._data.fill(0)
            self._total_written = 0
            self._latest_timestamp_unix = 0.0
