"""
Cálculo de espectrograma deslizante para visualización en tiempo real.

Para cada llamada calculamos un espectrograma de la ventana de
visualización (≈ 30 s × 100 Hz = 3000 muestras), tan pequeño que SciPy
lo procesa en ~1 ms. La salida son tres arrays:

  - ``freqs``: vector de frecuencias en Hz (eje Y del mapa de calor).
  - ``times``: vector de tiempos en segundos (eje X, relativos a "ahora").
  - ``power_db``: matriz ``(n_freqs, n_times)`` con la potencia en dB.

Decisiones
----------
* Usamos ``scipy.signal.spectrogram`` con ventana Hann, ``nperseg`` ≈
  ``sample_rate`` (1 segundo de resolución temporal) y un solapamiento
  del 75 %. Eso da una buena resolución temporal para el monitoreo
  sin recargar la CPU.
* Convertimos a dB con un piso a -120 dB para evitar ``-inf`` en
  silencios absolutos.
* El eje de tiempos se desplaza para que el extremo derecho coincida
  con el "ahora" del oscilograma (consistente con ``WaveformPanel``).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import spectrogram


# Piso de potencia para la escala dB (evita -inf en bloques silenciosos)
DB_FLOOR: float = -120.0


@dataclass(frozen=True)
class SpectrumResult:
    """Resultado del cálculo de un espectrograma."""

    freqs: np.ndarray       # Hz
    times: np.ndarray       # segundos relativos al "ahora" (≤ 0)
    power_db: np.ndarray    # (n_freqs, n_times) en dB


class SpectrumComputer:
    """Calcula espectrogramas Hann sobre la ventana visible."""

    def __init__(self, sample_rate_hz: int) -> None:
        if sample_rate_hz <= 0:
            raise ValueError("sample_rate_hz debe ser positivo")
        self._sample_rate = int(sample_rate_hz)

        # Parámetros del análisis: ventana de 1 s, 75 % de solape
        self._nperseg = max(64, self._sample_rate)        # 1 s
        self._noverlap = int(self._nperseg * 0.75)        # 75 %

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def compute(self, samples: np.ndarray) -> SpectrumResult:
        """Calcula el espectrograma de un array 1-D de muestras."""

        # Si hay muy pocas muestras, devolvemos un resultado vacío en
        # lugar de fallar — la UI mostrará el mapa en blanco.
        if samples.size < self._nperseg:
            return SpectrumResult(
                freqs=np.zeros(0, dtype=np.float32),
                times=np.zeros(0, dtype=np.float32),
                power_db=np.zeros((0, 0), dtype=np.float32),
            )

        # ``spectrogram`` devuelve potencia (escala "spectrum"). Hacemos
        # la conversión a dB después y aplicamos un piso para evitar
        # -inf en bloques silenciosos.
        freqs, times, sxx = spectrogram(
            samples.astype(np.float64),
            fs=self._sample_rate,
            window="hann",
            nperseg=self._nperseg,
            noverlap=self._noverlap,
            scaling="spectrum",
            mode="magnitude",
        )

        # Convertir magnitud a dB (20·log10) con piso seguro
        magnitude = np.maximum(sxx, 1e-12)
        power_db = (20.0 * np.log10(magnitude)).astype(np.float32)
        np.maximum(power_db, DB_FLOOR, out=power_db)

        # Trasladar el eje temporal para que el extremo derecho sea 0:
        # ``times`` original va de 0 a duración_s. Restamos el último
        # valor para que la columna más reciente caiga en t = 0.
        times_rel = times.astype(np.float32) - times[-1]

        return SpectrumResult(
            freqs=freqs.astype(np.float32),
            times=times_rel,
            power_db=power_db,
        )

    # ------------------------------------------------------------------
    # Mantenimiento
    # ------------------------------------------------------------------
    def update_sample_rate(self, sample_rate_hz: int) -> None:
        """Cambia la frecuencia de muestreo (recalcula los parámetros)."""

        if sample_rate_hz <= 0:
            raise ValueError("sample_rate_hz debe ser positivo")
        self._sample_rate = int(sample_rate_hz)
        self._nperseg = max(64, self._sample_rate)
        self._noverlap = int(self._nperseg * 0.75)
