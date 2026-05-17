"""
Detector clásico STA/LTA con histéresis.

Algoritmo
---------
Para cada muestra ``i`` calculamos:

    sta[i] = media móvil de x[i]² sobre los ``sta_n`` valores previos.
    lta[i] = media móvil de x[i]² sobre los ``lta_n`` valores previos.
    cft[i] = sta[i] / lta[i]      (Characteristic Function clásica)

La función característica se calcula con sumas acumuladas (cumsum), lo
que da una complejidad O(n) sin importar el tamaño de las ventanas.

Histéresis
----------
* Si ``cft`` supera ``threshold_on`` y el detector estaba "armado",
  pasa a estado "disparado" y emitimos ``EventSignal.TRIGGERED``.
* Si ``cft`` baja por debajo de ``threshold_off`` y estaba "disparado",
  vuelve a "armado" y emitimos ``EventSignal.RELEASED``.

Los dos umbrales evitan que pequeñas oscilaciones cerca del umbral
provoquen ráfagas de eventos.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import numpy as np

from shakevision.config import TriggerConfig
from shakevision.processing.buffer import BufferSnapshot


class EventSignal(Enum):
    """Resultado de procesar un nuevo bloque/snapshot."""

    NONE = "none"            # Sin cambio de estado
    TRIGGERED = "triggered"  # Acabamos de entrar en evento
    RELEASED = "released"    # Acabamos de salir del evento


@dataclass
class DetectorState:
    """Estado completo del detector tras un ``process``."""

    signal: EventSignal
    is_triggered: bool
    cft_max: float           # Pico del ratio en la última ventana
    last_timestamp_unix: float


# ============================================================
# Función característica STA/LTA (sin estado)
# ============================================================
def classic_sta_lta(x: np.ndarray, sta_n: int, lta_n: int) -> np.ndarray:
    """Calcula la función característica clásica STA/LTA en O(n).

    El array de entrada se eleva al cuadrado (energía) y se calculan las
    medias móviles con ``cumsum``. Las primeras ``lta_n`` muestras
    devuelven 1.0 porque la LTA todavía no es estable.
    """

    if sta_n <= 0 or lta_n <= 0:
        raise ValueError("sta_n y lta_n deben ser positivos")
    if sta_n >= lta_n:
        raise ValueError("sta_n debe ser estrictamente menor que lta_n")

    n = x.size
    if n == 0:
        return np.zeros(0, dtype=np.float32)

    # Energía instantánea (cuadrado de la señal)
    energy = np.asarray(x, dtype=np.float64) ** 2

    # Media móvil O(n) usando suma acumulada con prefijo cero
    cs = np.concatenate(([0.0], np.cumsum(energy)))

    sta = np.zeros(n, dtype=np.float64)
    lta = np.zeros(n, dtype=np.float64)

    # Para i >= sta_n, sta[i] = (cs[i+1] - cs[i+1-sta_n]) / sta_n
    valid_sta = slice(sta_n - 1, n)
    sta[valid_sta] = (cs[sta_n:] - cs[: n - sta_n + 1]) / sta_n

    valid_lta = slice(lta_n - 1, n)
    lta[valid_lta] = (cs[lta_n:] - cs[: n - lta_n + 1]) / lta_n

    # Donde la LTA todavía no es válida, devolvemos 1.0 (sin información)
    cft = np.ones(n, dtype=np.float32)
    valid = lta > 1e-20  # Evitar división por cero en señales planas
    cft[valid] = (sta[valid] / lta[valid]).astype(np.float32)
    cft[: lta_n - 1] = 1.0
    return cft


# ============================================================
# Detector con estado (historesis)
# ============================================================
class StaLtaDetector:
    """Detector STA/LTA con estado para uso en tiempo real."""

    def __init__(self, sample_rate_hz: int, config: TriggerConfig) -> None:
        if sample_rate_hz <= 0:
            raise ValueError("sample_rate_hz debe ser positivo")
        self._sample_rate = int(sample_rate_hz)
        self._config: TriggerConfig = config

        self._is_triggered: bool = False
        # Marca de tiempo del último disparo (para registrar eventos)
        self._last_trigger_ts: float = 0.0

    # ------------------------------------------------------------------
    # Propiedades / configuración
    # ------------------------------------------------------------------
    @property
    def is_triggered(self) -> bool:
        return self._is_triggered

    @property
    def config(self) -> TriggerConfig:
        return self._config

    def update_config(self, config: TriggerConfig) -> None:
        """Actualiza los parámetros sin perder el estado de disparo."""

        self._config = config

    def reset(self) -> None:
        """Vuelve al estado armado (no disparado)."""

        self._is_triggered = False
        self._last_trigger_ts = 0.0

    # ------------------------------------------------------------------
    # Procesamiento principal
    # ------------------------------------------------------------------
    def process(self, snapshot: BufferSnapshot) -> DetectorState:
        """Procesa la última instantánea y actualiza el estado interno.

        Solo se analiza el canal vertical (Z), que es donde se observan
        primero las ondas P en sismos lejanos.
        """

        # Si está desactivado por configuración, no hacemos nada
        if not self._config.enabled:
            return DetectorState(
                signal=EventSignal.NONE,
                is_triggered=False,
                cft_max=0.0,
                last_timestamp_unix=snapshot.latest_timestamp_unix,
            )

        z = snapshot.samples.get("Z")
        if z is None or z.size == 0:
            return DetectorState(
                signal=EventSignal.NONE,
                is_triggered=self._is_triggered,
                cft_max=0.0,
                last_timestamp_unix=snapshot.latest_timestamp_unix,
            )

        sta_n = max(1, int(self._config.sta_seconds * self._sample_rate))
        lta_n = max(sta_n + 1, int(self._config.lta_seconds * self._sample_rate))

        # Si no hay suficientes muestras, no se puede evaluar
        if z.size <= lta_n:
            return DetectorState(
                signal=EventSignal.NONE,
                is_triggered=self._is_triggered,
                cft_max=0.0,
                last_timestamp_unix=snapshot.latest_timestamp_unix,
            )

        cft = classic_sta_lta(z, sta_n=sta_n, lta_n=lta_n)
        cft_max = float(cft[lta_n:].max()) if cft.size > lta_n else 0.0

        # Decidir transición de estado mirando solo el último valor
        latest_ratio = float(cft[-1])

        signal = EventSignal.NONE
        if not self._is_triggered:
            if latest_ratio >= self._config.threshold_on:
                self._is_triggered = True
                self._last_trigger_ts = snapshot.latest_timestamp_unix
                signal = EventSignal.TRIGGERED
        else:
            if latest_ratio <= self._config.threshold_off:
                self._is_triggered = False
                signal = EventSignal.RELEASED

        return DetectorState(
            signal=signal,
            is_triggered=self._is_triggered,
            cft_max=cft_max,
            last_timestamp_unix=snapshot.latest_timestamp_unix,
        )

    @property
    def last_trigger_timestamp(self) -> Optional[float]:
        """Timestamp Unix del disparo más reciente (None si nunca)."""

        return self._last_trigger_ts if self._last_trigger_ts > 0 else None
