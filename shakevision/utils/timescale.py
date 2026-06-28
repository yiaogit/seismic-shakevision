"""
Mapeo no-lineal valor↔fracción para el slider de rango temporal (puro, sin Qt).

Problema: el rango útil va de ~1900 a *ahora* (~125 años). Un mapeo lineal deja
las fechas RECIENTES (donde se hacen casi todas las consultas) apretadas en un
extremo. Aplicamos un *warp* que da **más resolución a lo reciente**: la
distancia desde "ahora" se comprime con una potencia ``p<1`` (sqrt por defecto).

Sea ``u = (t_max - value) / (t_max - t_min)`` ∈ [0,1]  (0 = ahora, 1 = más viejo)
    ``frac = 1 - u**p``        (fracción 0…1 de izquierda a derecha)
    inverso: ``u = (1 - frac)**(1/p)`` → ``value = t_max - u·(t_max - t_min)``

Con ``p = 0.5`` lo reciente ocupa bastante más ancho que lo antiguo.
"""

from __future__ import annotations

DEFAULT_WARP: float = 0.5


def frac_for_value(value: float, t_min: float, t_max: float,
                   warp: float = DEFAULT_WARP) -> float:
    """Fracción ∈ [0,1] (izq→der) de un instante en el eje warpeado."""

    if t_max <= t_min:
        return 0.0
    v = min(max(float(value), t_min), t_max)
    u = (t_max - v) / (t_max - t_min)
    frac = 1.0 - u ** warp
    return min(1.0, max(0.0, frac))


def value_for_frac(frac: float, t_min: float, t_max: float,
                   warp: float = DEFAULT_WARP) -> float:
    """Instante (epoch) para una fracción ∈ [0,1] del eje warpeado."""

    if t_max <= t_min:
        return t_min
    f = min(1.0, max(0.0, float(frac)))
    u = (1.0 - f) ** (1.0 / warp)
    return t_max - u * (t_max - t_min)


def clamp_range(lo: float, hi: float, t_min: float, t_max: float,
                min_gap: float = 0.0) -> tuple[float, float]:
    """Asegura ``t_min ≤ lo ≤ hi ≤ t_max`` con un hueco mínimo ``min_gap``."""

    lo = min(max(float(lo), t_min), t_max)
    hi = min(max(float(hi), t_min), t_max)
    if hi < lo:
        lo, hi = hi, lo
    if min_gap > 0 and (hi - lo) < min_gap:
        # Empuja el que se pueda sin salir de los bordes.
        hi = min(t_max, lo + min_gap)
        lo = max(t_min, hi - min_gap)
    return lo, hi
