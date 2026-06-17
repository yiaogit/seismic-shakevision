"""Medidas de análisis sobre una ventana de muestras — funciones puras.

v0.7.7: núcleo del "modo análisis" del banco de trabajo. Sin Qt y sin
estado, así que es totalmente testeable. Las usa el panel de forma de onda
al seleccionar una región (LinearRegionItem) o al colocar pickers P/S.

Notas de unidades
-----------------
* ``peak_amplitude`` / ``rms`` devuelven el valor en las MISMAS unidades que
  la entrada (counts si no se ha quitado la respuesta; m/s si sí).
* ``dominant_frequency`` es independiente de unidades.
* ``sp_to_distance_km`` y ``local_magnitude`` son ESTIMACIONES de un único
  canal/estación — útiles como guía, no como solución de red. Se documenta
  su naturaleza aproximada para no dar falsa precisión.
"""

from __future__ import annotations

import numpy as np

# Velocidades crustales típicas (km/s) para la regla S-P → distancia.
_VP_KM_S = 6.0
_VS_KM_S = 3.46
# Factor (Vp·Vs)/(Vp−Vs): distancia ≈ factor × (tiempo S-P).
SP_DISTANCE_FACTOR_KM_S = (_VP_KM_S * _VS_KM_S) / (_VP_KM_S - _VS_KM_S)


def rotate_ne_rt(
    n: np.ndarray, e: np.ndarray, back_azimuth_deg: float
) -> tuple[np.ndarray, np.ndarray]:
    """Rota las componentes horizontales N/E a Radial/Transversal (R/T).

    ``back_azimuth_deg`` es el back-azimuth (dirección receptor→fuente, grados
    desde el Norte, sentido horario). Convención idéntica a ObsPy
    ``rotate_ne_rt`` para que los resultados sean comparables:

        R = −N·cos(ba) − E·sin(ba)
        T =  N·sin(ba) − E·cos(ba)

    R apunta a lo largo de la línea fuente-receptor (separa P-SV); T es
    perpendicular (aísla SH / Love). Función pura, sin Qt ni ObsPy.
    """

    ba = np.radians(float(back_azimuth_deg))
    n = np.asarray(n, dtype=np.float64)
    e = np.asarray(e, dtype=np.float64)
    r = -n * np.cos(ba) - e * np.sin(ba)
    t = n * np.sin(ba) - e * np.cos(ba)
    return r.astype(np.float32), t.astype(np.float32)


def great_circle_degrees(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """Distancia de círculo máximo en GRADOS entre dos puntos (haversine).

    Útil para la distancia epicentral evento↔estación sin depender de ObsPy.
    """

    import math

    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2)
    return math.degrees(2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def welch_psd(samples: np.ndarray, fs: float, nperseg: int | None = None):
    """Densidad espectral de potencia (método de Welch) de un tramo.

    Devuelve ``(freqs_hz, psd)``; arrays vacíos si no hay datos suficientes.
    ``psd`` está en unidad²/Hz (misma unidad de entrada al cuadrado por Hz).
    Pensado para el tramo seleccionado (caja amarilla) — espectro de una
    ventana, complementario al espectrograma (frecuencia vs tiempo).
    """

    samples = np.asarray(samples, dtype=np.float64)
    if samples.size < 8 or fs <= 0:
        return np.array([]), np.array([])
    from scipy.signal import welch

    nper = int(nperseg) if nperseg else min(256, samples.size)
    nper = max(8, min(nper, samples.size))
    freqs, psd = welch(samples, fs=float(fs), nperseg=nper)
    return freqs.astype(np.float64), psd.astype(np.float64)


def polarization_azimuth(n: np.ndarray, e: np.ndarray):
    """Análisis de polarización 2-D del movimiento de partícula horizontal.

    Devuelve ``(azimut_grados, rectilinearidad)`` o ``None`` si no hay datos
    suficientes. El azimut es la dirección del eje principal medido desde el
    Norte hacia el Este, en ``[0, 180)`` (hay ambigüedad de 180° para una
    polarización lineal). La rectilinearidad ``1 − λ₂/λ₁`` va de 0 (circular,
    ruido) a 1 (perfectamente lineal, típico de la onda P).

    Es una estimación de UNA estación (eigen-análisis de la covarianza E/N),
    útil como guía de la dirección fuente-receptor, no una localización.
    """

    import math

    n = np.asarray(n, dtype=np.float64)
    e = np.asarray(e, dtype=np.float64)
    m = min(n.size, e.size)
    if m < 2:
        return None
    n = n[-m:] - np.mean(n[-m:])
    e = e[-m:] - np.mean(e[-m:])
    # Covarianza 2×2 en orden [E, N].
    cov = np.array([[np.dot(e, e), np.dot(e, n)],
                    [np.dot(n, e), np.dot(n, n)]]) / m
    evals, evecs = np.linalg.eigh(cov)        # ascendente: evals[1] ≥ evals[0]
    if evals[1] <= 0:
        return None
    major = evecs[:, 1]                        # eje principal [E, N]
    az = math.degrees(math.atan2(major[0], major[1])) % 180.0
    rect = 1.0 - (evals[0] / evals[1])
    return az, rect


def peak_amplitude(samples: np.ndarray) -> float:
    """Amplitud de pico (máximo valor absoluto). Misma unidad que la entrada."""

    if samples is None or samples.size == 0:
        return 0.0
    return float(np.max(np.abs(samples)))


def peak_to_peak(samples: np.ndarray) -> float:
    """Amplitud pico-a-pico (máx − mín)."""

    if samples is None or samples.size == 0:
        return 0.0
    return float(np.max(samples) - np.min(samples))


def rms(samples: np.ndarray) -> float:
    """Valor RMS (raíz cuadrática media)."""

    if samples is None or samples.size == 0:
        return 0.0
    x = np.asarray(samples, dtype=np.float64)
    return float(np.sqrt(np.mean(x * x)))


def dominant_frequency(samples: np.ndarray, sample_rate_hz: float) -> float:
    """Frecuencia (Hz) del pico espectral, excluyendo la componente DC.

    Devuelve 0.0 si no hay suficientes muestras o la tasa es inválida.
    """

    if samples is None or samples.size < 4 or sample_rate_hz <= 0:
        return 0.0
    x = np.asarray(samples, dtype=np.float64)
    x = x - x.mean()                       # quitar DC para no sesgar el pico
    spec = np.abs(np.fft.rfft(x))
    freqs = np.fft.rfftfreq(x.size, d=1.0 / sample_rate_hz)
    if spec.size <= 1:
        return 0.0
    # Ignorar el bin 0 (DC) ya quitado, pero por seguridad empezar en 1.
    idx = int(np.argmax(spec[1:])) + 1
    return float(freqs[idx])


def sp_to_distance_km(sp_seconds: float) -> float:
    """Distancia epicentral estimada (km) a partir del tiempo S-P.

    Regla clásica de un solo registro: ``distancia ≈ factor × (S-P)`` con
    ``factor = (Vp·Vs)/(Vp−Vs) ≈ 8.4 km/s`` para corteza típica. Es una
    APROXIMACIÓN (depende del modelo de velocidad y la profundidad).
    """

    if sp_seconds <= 0:
        return 0.0
    return float(sp_seconds * SP_DISTANCE_FACTOR_KM_S)


def local_magnitude(peak_amp_m_s: float, distance_km: float) -> float:
    """Estimación MUY aproximada de magnitud local desde un solo canal.

    Usa una relación log-amplitud + corrección de distancia. NO sustituye a
    una ML calibrada (que requiere simular el sismógrafo Wood-Anderson y
    promediar varias estaciones). Pensada solo como guía de orden de
    magnitud en el modo análisis; el caller debe etiquetarla como estimada.

    ``peak_amp_m_s``: amplitud de pico en m/s (tras quitar respuesta).
    ``distance_km``:  distancia epicentral (p. ej. de ``sp_to_distance_km``).
    """

    if peak_amp_m_s <= 0 or distance_km <= 0:
        return 0.0
    # Amplitud en nm/s para un log10 con números manejables.
    amp_nm_s = peak_amp_m_s * 1e9
    # Corrección de distancia tipo Richter (atenuación log + geométrica).
    return float(np.log10(amp_nm_s) + 1.11 * np.log10(distance_km)
                 + 0.00189 * distance_km - 2.09)
