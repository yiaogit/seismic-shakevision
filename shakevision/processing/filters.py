"""
Procesador de formas de onda (DSP en tiempo real).

Aplica una cadena ligera y reproducible de:

  1. **Eliminación de tendencia** (resta de la media).
  2. **Filtro pasa-banda Butterworth** de fase cero (``sosfiltfilt``).

Decisiones de diseño
--------------------
* Trabajamos sobre la ventana de visualización completa (≈30 s × 100 Hz
  = 3000 muestras) en cada frame de la UI. Es ínfimo para SciPy y nos
  ahorra el filtro con estado (``sosfilt_zi``), que complica la
  invalidación al cambiar la frecuencia o al limpiar el búfer.
* Empleamos ``scipy.signal.butter(..., output='sos')`` por estabilidad
  numérica frente a la representación clásica ``b, a``.
* El procesador es ÚNICO (no se reinstancia por cada llamada): cachea
  los coeficientes ``sos`` y solo los recalcula cuando cambia el filtro
  o la frecuencia de muestreo. Esto evita un coste constante de diseño
  de filtro a 30 FPS.
* El procesador es agnóstico de Qt: se puede usar también en scripts
  de análisis fuera de línea o en pruebas.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Optional

import numpy as np
from scipy.signal import butter, sosfiltfilt

from shakevision.config import FilterConfig
from shakevision.processing.buffer import BufferSnapshot


class WaveformProcessor:
    """Aplica detrend + pasa-banda Butterworth a bloques de muestras."""

    def __init__(self, sample_rate_hz: int, filt: FilterConfig) -> None:
        if sample_rate_hz <= 0:
            raise ValueError("La frecuencia de muestreo debe ser positiva")

        self._sample_rate = int(sample_rate_hz)
        self._filt: FilterConfig = filt

        # Coeficientes SOS cacheados (None hasta que se diseñen)
        self._sos: Optional[np.ndarray] = None

        # Diseño inicial
        self._rebuild_sos()

    # ------------------------------------------------------------------
    # Configuración
    # ------------------------------------------------------------------
    @property
    def filter_config(self) -> FilterConfig:
        """Configuración actual (lectura)."""

        return self._filt

    def update_filter(self, filt: FilterConfig) -> None:
        """Reemplaza la configuración y rediseña el filtro si hace falta."""

        if (
            filt.lowcut_hz != self._filt.lowcut_hz
            or filt.highcut_hz != self._filt.highcut_hz
            or filt.order != self._filt.order
        ):
            self._filt = filt
            self._rebuild_sos()
        else:
            # Cambios que no afectan al diseño (enabled, detrend...)
            self._filt = filt

    def update_sample_rate(self, sample_rate_hz: int) -> None:
        """Cambia la frecuencia de muestreo (rediseña el filtro)."""

        if sample_rate_hz <= 0:
            raise ValueError("La frecuencia de muestreo debe ser positiva")
        if sample_rate_hz != self._sample_rate:
            self._sample_rate = int(sample_rate_hz)
            self._rebuild_sos()

    # ------------------------------------------------------------------
    # Aplicación del procesador
    # ------------------------------------------------------------------
    def apply(self, samples: np.ndarray) -> np.ndarray:
        """Aplica la cadena DSP a un array 1-D (devuelve un nuevo array)."""

        # Camino rápido: filtro deshabilitado -> devolvemos copia para
        # evitar que el caller modifique nuestro búfer interno.
        if not self._filt.enabled:
            return np.ascontiguousarray(samples, dtype=np.float32)

        if samples.size == 0:
            return samples.astype(np.float32, copy=True)

        x = np.ascontiguousarray(samples, dtype=np.float64)

        # 1. Eliminar la media (detrend constante). Solo si está activado.
        if self._filt.detrend:
            x = x - np.mean(x)

        # 2. Filtro pasa-banda. ``sosfiltfilt`` exige una longitud mínima
        # (≈ 3 × order × 2). Si el array es demasiado corto devolvemos
        # la señal solo con el detrend aplicado, sin filtrar.
        if self._sos is not None:
            min_len = 3 * (2 * self._filt.order) + 1
            if x.size > min_len:
                x = sosfiltfilt(self._sos, x)

        return x.astype(np.float32, copy=False)

    def apply_snapshot(self, snapshot: BufferSnapshot) -> BufferSnapshot:
        """Devuelve una nueva ``BufferSnapshot`` con los tres canales filtrados."""

        new_samples = {
            channel: self.apply(samples)
            for channel, samples in snapshot.samples.items()
        }
        return BufferSnapshot(
            times=snapshot.times,
            samples=new_samples,
            latest_timestamp_unix=snapshot.latest_timestamp_unix,
        )

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------
    def _rebuild_sos(self) -> None:
        """Rediseña los coeficientes SOS a partir de la configuración actual."""

        nyquist = 0.5 * self._sample_rate
        low = self._filt.lowcut_hz
        high = self._filt.highcut_hz

        # Validar que las frecuencias caigan dentro del rango válido
        # (0, nyquist). Si no, deshabilitamos el filtro pasa-banda y
        # dejamos solo el detrend.
        if not (0.0 < low < high < nyquist):
            self._sos = None
            return

        try:
            self._sos = butter(
                N=self._filt.order,
                Wn=[low, high],
                btype="band",
                fs=self._sample_rate,
                output="sos",
            )
        except ValueError:
            # Parámetros inválidos -> deshabilitar pasa-banda
            self._sos = None


# ============================================================
# Helpers de uso puntual
# ============================================================
def design_default_processor(sample_rate_hz: int) -> WaveformProcessor:
    """Crea un procesador con la configuración por defecto del paquete.

    Atajo útil para scripts y para los tests.
    """

    # Importación local para evitar acoplar este módulo con la config
    # global (algunos tests construyen su propia configuración).
    from shakevision.config import FilterConfig as _FC

    return WaveformProcessor(sample_rate_hz=sample_rate_hz, filt=_FC())


def with_enabled(filt: FilterConfig, enabled: bool) -> FilterConfig:
    """Devuelve una copia de ``filt`` con el flag ``enabled`` cambiado.

    Pequeño helper para que el panel de control no tenga que conocer
    los nombres de todos los campos de ``FilterConfig`` al alternar
    el bypass.
    """

    return replace(filt, enabled=enabled)
