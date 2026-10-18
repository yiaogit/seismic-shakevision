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

    def __init__(self, sample_rate_hz: int,
                 window_seconds: float | None = None) -> None:
        """``window_seconds=None`` conserva el tamaño histórico
        (``max(64, fs)``); un valor explícito fija la ventana FFT en segundos
        (0.1–10 s, acotado a 8–8192 muestras)."""

        if sample_rate_hz <= 0:
            raise ValueError("sample_rate_hz debe ser positivo")
        self._sample_rate = int(sample_rate_hz)
        self._window_seconds = (
            None if window_seconds is None
            else max(0.1, min(float(window_seconds), 10.0))
        )
        self._rebuild_window()

    # ------------------------------------------------------------------
    # Configuración
    # ------------------------------------------------------------------
    def _rebuild_window(self) -> None:
        if self._window_seconds is None:
            nperseg = max(64, self._sample_rate)
        else:
            nperseg = int(round(self._sample_rate * self._window_seconds))
            nperseg = max(8, min(nperseg, 8192))
        self._nperseg = int(nperseg)
        self._noverlap = int(self._nperseg * 0.75)   # 75 % de solape

    @property
    def window_seconds(self) -> float:
        """Duración efectiva de la ventana FFT, en segundos."""

        return self._nperseg / float(self._sample_rate)

    @property
    def frequency_resolution_hz(self) -> float:
        return self._sample_rate / float(self._nperseg)

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

        # Normalizar por el pico ANTES del espectrograma. La escala dB es
        # relativa (no una PSD calibrada): así una traza en counts (±cientos)
        # y la misma en velocidad (±1e-7 m/s, tras remove_response) producen
        # el mismo color. Sin esto, los datos físicos caían todos al piso
        # -120 dB y el mapa salía uniforme.
        x = samples.astype(np.float64)
        peak = float(np.max(np.abs(x))) if x.size else 0.0
        if peak > 0:
            x = x / peak

        # ``spectrogram`` devuelve potencia (escala "spectrum"). Hacemos
        # la conversión a dB después y aplicamos un piso para evitar
        # -inf en bloques silenciosos.
        freqs, times, sxx = spectrogram(
            x,
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
        self._rebuild_window()

    def set_window_seconds(self, window_seconds: float | None) -> None:
        """Fija (o vuelve a ``None`` = automático) la ventana FFT."""

        self._window_seconds = (
            None if window_seconds is None
            else max(0.1, min(float(window_seconds), 10.0))
        )
        self._rebuild_window()


def rebin_log_frequency(
    freqs: np.ndarray,
    power_db: np.ndarray,
    *,
    n_bins: int = 256,
    f_min: float | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Remuestrea un espectrograma a frecuencia logarítmica.

    ``ImageItem`` pinta píxeles equiespaciados. Para un eje logarítmico hay
    que interpolar las filas de potencia a frecuencias log-espaciadas; el
    widget pinta después en coordenadas ``log10(f)``.

    Devuelve ``(log_freqs, log_power_db)`` con la misma dimensión temporal.
    Si no hay frecuencias positivas o la forma no cuadra, devuelve arrays
    vacíos (el llamador mantiene la vista lineal).
    """

    f = np.asarray(freqs, dtype=np.float64).reshape(-1)
    p = np.asarray(power_db, dtype=np.float64)
    if f.size < 2 or p.ndim != 2 or p.shape[0] != f.size:
        return np.zeros(0, dtype=np.float32), np.zeros((0, 0), dtype=np.float32)

    positive = f[f > 0]
    if positive.size == 0:
        return np.zeros(0, dtype=np.float32), np.zeros((0, p.shape[1]), dtype=np.float32)

    lo = float(f_min) if f_min is not None else float(positive[0])
    hi = float(f[-1])
    if not (lo > 0 and hi > lo):
        return np.zeros(0, dtype=np.float32), np.zeros((0, p.shape[1]), dtype=np.float32)

    target = np.geomspace(lo, hi, max(8, int(n_bins)))

    # Interpolación lineal por filas, vectorizada sobre el tiempo.
    idx = np.searchsorted(f, target, side="right") - 1
    idx = np.clip(idx, 0, f.size - 2)
    f0 = f[idx]
    f1 = f[idx + 1]
    frac = np.clip((target - f0) / np.maximum(f1 - f0, 1e-12), 0.0, 1.0)
    out = (p[idx] * (1.0 - frac[:, None])
           + p[idx + 1] * frac[:, None])
    return target.astype(np.float32), out.astype(np.float32)
