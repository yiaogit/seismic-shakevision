"""
Sonificación: convertir muestras sísmicas en audio reproducible.

Idea básica
-----------
La sismología cubre frecuencias muy por debajo del oído humano
(~0.1–30 Hz). Para "oír" un sismograma basta con **acelerar** la señal:
si reproducimos a velocidad ``× speed_factor`` lo que originalmente
ocurría a lo largo de 60 s suena en 1 s (con ``speed_factor = 60``)
y las frecuencias ascienden 60 veces, llevándolas al rango audible
(6–1800 Hz, que es donde está la mayor parte de la información de un
sismo local o regional).

Pipeline
--------
1. Tomar las muestras del canal vertical (EHZ) a 100 Hz.
2. Considerar que tras el cambio de velocidad cada muestra dura
   ``1 / (input_rate × speed_factor)`` segundos.
3. Remuestrear de esa frecuencia "efectiva" a 44 100 Hz (audio CD).
4. Normalizar al pico al ``target_amplitude × 32767`` para que no
   sature ni se quede inaudible.
5. Devolver un array ``int16`` listo para ``QAudioSink``.

Decisiones
----------
* ``scipy.signal.resample_poly`` es estable, lineal, y rápida (~1 ms
  para 6 s de entrada). Usamos ``Fraction.limit_denominator(1000)``
  para reducir el ratio a algo manejable.
* La normalización siempre se hace por pico (no por RMS) para que un
  evento fuerte no salga proporcionalmente más fuerte que el ruido;
  el cerebro ya hace ese mapeo por sí solo y nos interesa que cada
  clip suene claro independientemente del nivel absoluto.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Final

import numpy as np
from scipy.signal import resample_poly


# Frecuencia objetivo del audio (CD quality). 44.1 kHz se reproduce en
# todos los sistemas operativos sin necesidad de remuestreo extra del SO.
AUDIO_RATE_HZ: Final[int] = 44_100

# Amplitud objetivo (sobre 1.0 = pico int16). 0.7 deja margen para evitar
# clipping si el sistema introduce un pequeño boost.
DEFAULT_TARGET_AMPLITUDE: Final[float] = 0.7

# Rango razonable del factor de aceleración (lo expone la UI)
MIN_SPEED_FACTOR: Final[int] = 10
MAX_SPEED_FACTOR: Final[int] = 300
DEFAULT_SPEED_FACTOR: Final[int] = 60


@dataclass(frozen=True)
class SonifyResult:
    """Resultado de la sonificación."""

    audio: np.ndarray            # int16 PCM mono
    audio_rate_hz: int           # típicamente 44 100
    input_samples: int           # cuántas muestras de entrada se usaron
    audio_duration_s: float      # duración del clip generado
    peak_amplitude_int16: int    # pico (para indicador visual de "volumen")


def sonify(
    samples: np.ndarray,
    input_rate_hz: int,
    speed_factor: float,
    audio_rate_hz: int = AUDIO_RATE_HZ,
    target_amplitude: float = DEFAULT_TARGET_AMPLITUDE,
) -> SonifyResult:
    """Convierte un array sísmico en audio mono int16.

    Parameters
    ----------
    samples:
        Vector 1-D del canal vertical (EHZ) en cuentas o velocidad.
        Cualquier dtype: se convierte a float32.
    input_rate_hz:
        Frecuencia de muestreo original (típicamente 100 Hz).
    speed_factor:
        Cuántas veces se acelera la reproducción. 60 es un buen punto
        de partida: un clip de 60 s suena en 1 s y la energía cae en
        un rango muy audible.
    audio_rate_hz:
        Frecuencia del flujo de salida. 44 100 Hz por defecto.
    target_amplitude:
        Pico relativo a la escala int16. Entre 0 y 1.

    Returns
    -------
    SonifyResult con el array int16 y metadatos.
    """

    if input_rate_hz <= 0:
        raise ValueError("input_rate_hz debe ser positivo")
    if speed_factor <= 0:
        raise ValueError("speed_factor debe ser positivo")
    if not (0.0 < target_amplitude <= 1.0):
        raise ValueError("target_amplitude debe estar en (0, 1]")

    if samples.size == 0:
        return SonifyResult(
            audio=np.zeros(0, dtype=np.int16),
            audio_rate_hz=audio_rate_hz,
            input_samples=0,
            audio_duration_s=0.0,
            peak_amplitude_int16=0,
        )

    x = np.asarray(samples, dtype=np.float32)

    # Quitar la media (detrend) para que un offset DC no domine el pico
    x = x - np.mean(x)

    # Frecuencia "efectiva" tras la aceleración
    effective_input_rate = float(input_rate_hz) * float(speed_factor)

    # Calcular el ratio audio_rate / effective_input_rate como fracción
    # racional. ``limit_denominator(1000)`` evita ratios extremos que
    # harían lento a resample_poly.
    ratio = Fraction(audio_rate_hz / effective_input_rate).limit_denominator(1000)
    up, down = ratio.numerator, ratio.denominator

    # Si el ratio queda en 1:1 o muy cercano, ahorrar el resample
    if up == down:
        resampled = x
    else:
        resampled = resample_poly(x, up=up, down=down)

    # Normalización por pico
    peak = float(np.max(np.abs(resampled))) if resampled.size else 0.0
    if peak > 0:
        scale = (32767.0 * target_amplitude) / peak
    else:
        scale = 0.0

    audio = np.clip(resampled * scale, -32768.0, 32767.0).astype(np.int16)
    peak_int16 = int(np.max(np.abs(audio))) if audio.size else 0

    return SonifyResult(
        audio=audio,
        audio_rate_hz=audio_rate_hz,
        input_samples=int(samples.size),
        audio_duration_s=float(audio.size) / float(audio_rate_hz),
        peak_amplitude_int16=peak_int16,
    )


def estimate_audio_duration_s(
    input_samples: int,
    input_rate_hz: int,
    speed_factor: float,
) -> float:
    """Predicción rápida de la duración del clip sin remuestrear.

    Útil para mostrar al usuario "≈ 1.0 s de audio" antes de pulsar
    el botón.
    """

    if input_rate_hz <= 0 or speed_factor <= 0:
        return 0.0
    real_duration_s = float(input_samples) / float(input_rate_hz)
    return real_duration_s / float(speed_factor)
