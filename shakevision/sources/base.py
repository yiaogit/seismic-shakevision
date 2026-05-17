"""
Interfaz abstracta para las fuentes de datos sísmicos.

Tanto la fuente simulada (fase 2) como el cliente SeedLink real (fase 4)
implementan esta interfaz. La interfaz se diseña como un ``QObject`` para
poder emitir señales Qt y vivir dentro de un ``QThread`` sin esfuerzo.

Contrato mínimo:
  - ``start()``  : inicia la adquisición.
  - ``stop()``   : detiene la adquisición de forma segura.
  - señal ``data_ready(SampleBatch)`` : emitida cada vez que llega un
    nuevo bloque de muestras (canales Z/N/E).
  - señal ``status_changed(str)``     : mensajes de estado para mostrar
    en la barra inferior (conectando, error, latencia, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
from PySide6.QtCore import QObject, Signal


@dataclass(frozen=True)
class SampleBatch:
    """Bloque de muestras entregado por una fuente.

    Attributes
    ----------
    timestamp_unix:
        Marca de tiempo (segundos UNIX) de la primera muestra del bloque.
    sample_rate_hz:
        Frecuencia de muestreo en Hz (típicamente 100 para Raspberry Shake).
    z, n, e:
        Vectores de muestras de los canales vertical, norte y este. Los
        tres deben tener la misma longitud. Si la estación es de un solo
        canal (RS1D), ``n`` y ``e`` pueden ser ``None``.
    """

    timestamp_unix: float
    sample_rate_hz: int
    z: np.ndarray
    n: Optional[np.ndarray] = None
    e: Optional[np.ndarray] = None


class DataSource(QObject):
    """Clase base abstracta para todas las fuentes de datos sísmicos."""

    # Señal emitida cada vez que llega un nuevo bloque de muestras
    data_ready = Signal(object)  # SampleBatch

    # Señal emitida con mensajes de estado legibles para el usuario
    status_changed = Signal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._running: bool = False

    # ------------------------------------------------------------------
    # Ciclo de vida (a implementar por las subclases)
    # ------------------------------------------------------------------
    def start(self) -> None:
        """Inicia la adquisición de muestras."""

        raise NotImplementedError

    def stop(self) -> None:
        """Detiene la adquisición de manera limpia."""

        raise NotImplementedError

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------
    @property
    def is_running(self) -> bool:
        """Devuelve ``True`` si la fuente está produciendo muestras."""

        return self._running

    # ------------------------------------------------------------------
    # Metadatos opcionales (las subclases pueden sobrescribirlos)
    # ------------------------------------------------------------------
    @property
    def station_label(self) -> str:
        """Etiqueta legible de la estación; se mostrará en la cabecera."""

        return "—"
