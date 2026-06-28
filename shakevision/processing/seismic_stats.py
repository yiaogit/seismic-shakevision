"""
Estadística sísmica (pura, sin Qt) para el panel de análisis profesional y el
reporte PDF. Ver ``docs/dashboard-pro.md`` para las decisiones de método.

Todo opera sobre listas/arrays de floats (magnitudes, profundidades, tiempos
epoch) — la capa de UI extrae esos arrays de los ``Earthquake``. Así se puede
testear sin ``QApplication`` ni obspy. Usa numpy; ``scipy`` solo para el ajuste
de Omori (aislado, con fallback a ``None``).
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np

_LOG10_E = math.log10(math.e)   # 0.4342944819…


# ---------------------------------------------------------------------------
# Magnitud-frecuencia: Mc, b-value, FMD
# ---------------------------------------------------------------------------
def magnitude_of_completeness(
    magnitudes, dm: float = 0.1
) -> Optional[float]:
    """Mc por **máxima curvatura (MAXC)** + corrección estándar +0.2.

    Es la magnitud del pico de la FMD no acumulada. Devuelve ``None`` si no hay
    datos suficientes.
    """

    mags = np.asarray([m for m in magnitudes if m is not None], dtype=float)
    mags = mags[np.isfinite(mags)]
    if mags.size < 10:
        return None
    lo = math.floor(mags.min() / dm) * dm
    hi = math.ceil(mags.max() / dm) * dm + dm
    edges = np.arange(lo, hi + dm, dm)
    counts, _ = np.histogram(mags, bins=edges)
    if counts.sum() == 0:
        return None
    peak = int(np.argmax(counts))
    mc = edges[peak] + dm / 2.0          # centro del bin del pico
    return round(float(mc + 0.2), 2)


def b_value(
    magnitudes, mc: Optional[float] = None, dm: float = 0.1
) -> Optional[dict]:
    """b-value / a-value por **máxima verosimilitud (Aki–Utsu)**.

    Devuelve ``{"b","b_err","a","mc","n","mean_mag"}`` o ``None`` si no hay
    suficientes eventos por encima de Mc o el denominador no es válido.
    Incertidumbre por **Shi & Bolt (1982)**.
    """

    mags = np.asarray([m for m in magnitudes if m is not None], dtype=float)
    mags = mags[np.isfinite(mags)]
    if mags.size < 10:
        return None
    if mc is None:
        mc = magnitude_of_completeness(mags, dm=dm)
        if mc is None:
            return None
    above = mags[mags >= mc - dm / 2.0]
    n = int(above.size)
    if n < 10:
        return None
    mean_mag = float(above.mean())
    denom = mean_mag - (mc - dm / 2.0)
    if denom <= 0:
        return None
    b = _LOG10_E / denom
    # Shi & Bolt: σ_b = 2.30·b²·sqrt(Σ(M-<M>)² / (n(n-1)))
    var = float(np.sum((above - mean_mag) ** 2))
    b_err = 2.30 * b * b * math.sqrt(var / (n * (n - 1))) if n > 1 else 0.0
    a = math.log10(n) + b * mc
    return {
        "b": round(b, 3), "b_err": round(b_err, 3),
        "a": round(a, 3), "mc": round(float(mc), 2),
        "n": n, "mean_mag": round(mean_mag, 3),
    }


def fmd(magnitudes, dm: float = 0.1) -> dict:
    """Distribución magnitud-frecuencia para graficar el diagrama GR.

    Devuelve ``{"mag": [...], "incremental": [...], "cumulative": [...]}`` donde
    ``cumulative[i]`` = nº de eventos con M ≥ mag[i].
    """

    mags = np.asarray([m for m in magnitudes if m is not None], dtype=float)
    mags = mags[np.isfinite(mags)]
    if mags.size == 0:
        return {"mag": [], "incremental": [], "cumulative": []}
    lo = math.floor(mags.min() / dm) * dm
    hi = math.ceil(mags.max() / dm) * dm + dm
    edges = np.arange(lo, hi + dm, dm)
    inc, _ = np.histogram(mags, bins=edges)
    centers = edges[:-1] + dm / 2.0
    cum = np.cumsum(inc[::-1])[::-1]      # N(≥M)
    return {
        "mag": [round(float(x), 2) for x in centers],
        "incremental": [int(x) for x in inc],
        "cumulative": [int(x) for x in cum],
    }


# ---------------------------------------------------------------------------
# Momento sísmico / energía
# ---------------------------------------------------------------------------
def seismic_moment(magnitude: float) -> float:
    """Momento sísmico escalar ``M0`` en N·m (Hanks & Kanamori 1979)."""

    return float(10.0 ** (1.5 * float(magnitude) + 9.1))


def energy_joules(magnitude: float) -> float:
    """Energía radiada en julios (Gutenberg–Richter: log10 E = 4.8 + 1.5 M)."""

    return float(10.0 ** (4.8 + 1.5 * float(magnitude)))


def cumulative_series(times_unix, magnitudes) -> dict:
    """Series acumuladas en el tiempo: nº de eventos y momento sísmico.

    Entradas paralelas (tiempo epoch, magnitud). Devuelve ``{"t":[...],
    "count":[...], "moment_cum":[...], "energy_cum":[...]}`` ordenado por tiempo.
    """

    t = np.asarray(times_unix, dtype=float)
    m = np.asarray(magnitudes, dtype=float)
    ok = np.isfinite(t) & np.isfinite(m)
    t, m = t[ok], m[ok]
    if t.size == 0:
        return {"t": [], "count": [], "moment_cum": [], "energy_cum": []}
    order = np.argsort(t)
    t, m = t[order], m[order]
    m0 = 10.0 ** (1.5 * m + 9.1)
    e = 10.0 ** (4.8 + 1.5 * m)
    return {
        "t": [float(x) for x in t],
        "count": [int(i) for i in range(1, t.size + 1)],
        "moment_cum": [float(x) for x in np.cumsum(m0)],
        "energy_cum": [float(x) for x in np.cumsum(e)],
    }


# ---------------------------------------------------------------------------
# Decaimiento de réplicas (Omori modificado)
# ---------------------------------------------------------------------------
def omori_fit(
    times_unix, magnitudes=None, t_main: Optional[float] = None,
    n_bins: int = 30,
) -> Optional[dict]:
    """Ajusta la tasa de réplicas ``n(t) = K / (t + c)^p`` (Omori modificado).

    ``t`` en **días** desde el evento principal (por defecto, el primero).
    Ajuste por mínimos cuadrados sobre la tasa binned. Devuelve
    ``{"K","c","p","t_days","rate"}`` o ``None``.

    **Aplicabilidad (corrección de método):** Omori SOLO tiene sentido para una
    secuencia principal-réplicas. Si se pasan ``magnitudes``, exigimos un
    mainshock DOMINANTE (≥0.8 sobre el 2.º mayor, ~Båth) y que las réplicas
    (eventos posteriores) sean MAYORÍA; si no, devolvemos ``None`` para no
    ajustar un Omori espurio sobre un catálogo regional multianual.
    """

    t = np.asarray(times_unix, dtype=float)
    m = np.asarray(magnitudes, dtype=float) if magnitudes is not None else None
    finite = np.isfinite(t)
    if m is not None and m.size == t.size:
        finite = finite & np.isfinite(m)
    t = t[finite]
    m = m[finite] if (m is not None and m.size == finite.size) else None
    if t.size < 20:
        return None
    order = np.argsort(t)
    t = t[order]
    if m is not None:
        m = m[order]
        # ¿Es realmente una secuencia de réplicas?
        i_main = int(np.argmax(m))
        m_main = float(m[i_main])
        others = np.delete(m, i_main)
        m_2nd = float(np.max(others)) if others.size else -10.0
        t0_main = float(t[i_main])
        n_after = int(np.sum(t > t0_main))
        if (m_main - m_2nd) < 0.8 or n_after < max(15, 0.5 * t.size):
            return None
        if t_main is None:
            t_main = t0_main
    t0 = float(t_main) if t_main is not None else float(t[0])
    days = (t - t0) / 86400.0
    days = days[days > 0]
    if days.size < 15:
        return None
    edges = np.linspace(0, float(days.max()), n_bins + 1)
    counts, _ = np.histogram(days, bins=edges)
    width = np.diff(edges)
    rate = counts / np.where(width > 0, width, 1.0)   # eventos/día
    mid = edges[:-1] + width / 2.0
    keep = rate > 0
    if keep.sum() < 5:
        return None
    mid_k, rate_k = mid[keep], rate[keep]
    try:
        from scipy.optimize import curve_fit

        def _omori(tt, K, c, p):
            return K / np.power(tt + c, p)

        popt, _ = curve_fit(
            _omori, mid_k, rate_k,
            p0=[float(rate_k[0]), 0.1, 1.0],
            bounds=([0, 1e-3, 0.3], [np.inf, 10.0, 3.0]),
            maxfev=10000,
        )
    except Exception:  # noqa: BLE001
        return None
    K, c, p = (float(popt[0]), float(popt[1]), float(popt[2]))
    return {
        "K": round(K, 3), "c": round(c, 4), "p": round(p, 3),
        "t_days": [float(x) for x in mid_k],
        "rate": [float(x) for x in rate_k],
    }


# ---------------------------------------------------------------------------
# Profundidad
# ---------------------------------------------------------------------------
def depth_histogram(depths, bin_km: float = 25.0) -> dict:
    """Histograma de profundidades. ``{"edges":[...], "counts":[...]}``."""

    d = np.asarray([x for x in depths if x is not None], dtype=float)
    d = d[np.isfinite(d)]
    if d.size == 0:
        return {"edges": [], "counts": []}
    hi = math.ceil(d.max() / bin_km) * bin_km + bin_km
    edges = np.arange(0, hi + bin_km, bin_km)
    counts, _ = np.histogram(d, bins=edges)
    return {
        "edges": [float(x) for x in edges],
        "counts": [int(x) for x in counts],
    }


def depth_percentiles(depths) -> Optional[dict]:
    """Percentiles p10/50/90 + min/max de profundidad, o ``None``."""

    d = np.asarray([x for x in depths if x is not None], dtype=float)
    d = d[np.isfinite(d)]
    if d.size == 0:
        return None
    p10, p50, p90 = (float(x) for x in np.percentile(d, [10, 50, 90]))
    return {
        "min": float(d.min()), "p10": round(p10, 1), "p50": round(p50, 1),
        "p90": round(p90, 1), "max": float(d.max()), "n": int(d.size),
    }


# ---------------------------------------------------------------------------
# Calidad del catálogo: Mc(t) / b(t)
# ---------------------------------------------------------------------------
def mc_b_timeseries(
    times_unix, magnitudes, n_windows: int = 12, min_per_window: int = 60
) -> Optional[dict]:
    """Mc y b en ventanas de **igual nº de eventos** a lo largo del tiempo.

    Permite juzgar la CALIDAD del catálogo (¿cambia la completitud?, ¿es estable
    el b?). Devuelve ``{"t","mc","b","b_err"}`` (centro temporal de cada ventana)
    o ``None`` si no hay suficientes eventos.
    """

    t = np.asarray(times_unix, dtype=float)
    m = np.asarray(magnitudes, dtype=float)
    ok = np.isfinite(t) & np.isfinite(m)
    t, m = t[ok], m[ok]
    if t.size < n_windows * min_per_window:
        n_windows = max(2, int(t.size // min_per_window))
    if n_windows < 2 or t.size < 2 * min_per_window:
        return None
    order = np.argsort(t)
    t, m = t[order], m[order]
    edges = np.linspace(0, t.size, n_windows + 1).astype(int)
    out_t, out_mc, out_b, out_be = [], [], [], []
    for i in range(n_windows):
        lo, hi = edges[i], edges[i + 1]
        if hi - lo < min_per_window:
            continue
        seg_m = m[lo:hi]
        bv = b_value(seg_m)
        if bv is None:
            continue
        out_t.append(float(np.median(t[lo:hi])))
        out_mc.append(bv["mc"])
        out_b.append(bv["b"])
        out_be.append(bv["b_err"])
    if len(out_t) < 2:
        return None
    return {"t": out_t, "mc": out_mc, "b": out_b, "b_err": out_be}


# ---------------------------------------------------------------------------
# Sección transversal Wadati–Benioff (proyección perpendicular a la fosa)
# ---------------------------------------------------------------------------
def inter_event_times(times_unix, n_bins: int = 24) -> Optional[dict]:
    """Distribución (log) de tiempos entre eventos consecutivos.

    Distingue catálogos **Poissonianos** (aleatorios → tiempos exponenciales,
    pico ancho) de **agrupados** (réplicas/enjambres → muchos intervalos cortos).
    Devuelve ``{"hours","counts","median_h"}`` (centros de bin en horas) o
    ``None`` si hay pocos eventos.
    """

    t = np.asarray(times_unix, dtype=float)
    t = np.sort(t[np.isfinite(t)])
    if t.size < 10:
        return None
    dt_h = np.diff(t) / 3600.0
    dt_h = dt_h[dt_h > 0]
    if dt_h.size < 5:
        return None
    logd = np.log10(dt_h)
    lo, hi = float(logd.min()), float(logd.max())
    if hi <= lo:
        hi = lo + 1.0
    edges = np.linspace(lo, hi, n_bins + 1)
    counts, _ = np.histogram(logd, bins=edges)
    centers = 10.0 ** ((edges[:-1] + edges[1:]) / 2.0)
    return {
        "hours": [round(float(x), 4) for x in centers],
        "counts": [int(x) for x in counts],
        "median_h": round(float(np.median(dt_h)), 3),
    }


def spatial_density(
    lons, lats, magnitudes=None, target_bins: int = 36
) -> Optional[dict]:
    """Densidad espacial: cuenta sismos en una rejilla **lon × lat**.

    Para un catálogo regional de larga ventana responde "¿DÓNDE se concentra la
    actividad?" — la pregunta natural de un panorama de gran área (a diferencia
    del diagrama espacio-tiempo, que solo lee bien sobre una estructura lineal).

    Rejilla de paso cuadrado (≈ ``span / target_bins`` grados). Devuelve solo
    las celdas no vacías como ``[lon_c, lat_c, conteo, mag_máx]`` más el ``step``
    y las extensiones, o ``None`` si hay pocos eventos.
    """

    lo = np.asarray(lons, dtype=float)
    la = np.asarray(lats, dtype=float)
    ok = np.isfinite(lo) & np.isfinite(la)
    m = None
    if magnitudes is not None:
        m_arr = np.asarray(magnitudes, dtype=float)
        if m_arr.size == ok.size:
            ok = ok & np.isfinite(m_arr)
            m = m_arr[ok]
    lo, la = lo[ok], la[ok]
    if lo.size < 5:
        return None

    lon_min, lon_max = float(lo.min()), float(lo.max())
    lat_min, lat_max = float(la.min()), float(la.max())
    span = max(lon_max - lon_min, lat_max - lat_min, 1e-6)
    step = span / max(1, int(target_bins))
    nlon = int(np.floor((lon_max - lon_min) / step)) + 1
    nlat = int(np.floor((lat_max - lat_min) / step)) + 1

    ix = np.clip(np.floor((lo - lon_min) / step).astype(int), 0, nlon - 1)
    iy = np.clip(np.floor((la - lat_min) / step).astype(int), 0, nlat - 1)

    cells: dict[tuple[int, int], list[float]] = {}
    for k in range(lo.size):
        key = (int(ix[k]), int(iy[k]))
        mg = float(m[k]) if m is not None else 0.0
        slot = cells.get(key)
        if slot is None:
            cells[key] = [1.0, mg]
        else:
            slot[0] += 1.0
            if mg > slot[1]:
                slot[1] = mg

    out = []
    for (gx, gy), (cnt, mx) in cells.items():
        lon_c = lon_min + (gx + 0.5) * step
        lat_c = lat_min + (gy + 0.5) * step
        out.append([round(lon_c, 3), round(lat_c, 3), int(cnt), round(mx, 1)])
    return {
        "cells": out,
        "step": round(step, 4),
        "lon": [round(lon_min, 3), round(lon_max, 3)],
        "lat": [round(lat_min, 3), round(lat_max, 3)],
    }


def cross_section(lats, lons, depths, magnitudes=None) -> list[list]:
    """Proyecta epicentros sobre el eje **perpendicular a la fosa** vía PCA.

    En vez de lat-profundidad (que solo vale si la fosa es N-S), hallamos el eje
    largo de la sismicidad (≈ paralelo a la fosa) y proyectamos sobre su
    perpendicular → "distancia a través de la fosa" (km). Devuelve
    ``[[dist_km, depth_km, mag], …]`` para dibujar la sección de profundidad.
    """

    la = np.asarray(lats, dtype=float)
    lo = np.asarray(lons, dtype=float)
    de = np.asarray(depths, dtype=float)
    ok = np.isfinite(la) & np.isfinite(lo) & np.isfinite(de)
    la, lo, de = la[ok], lo[ok], de[ok]
    if la.size < 3:
        return []
    mg = (np.asarray(magnitudes, dtype=float)[ok]
          if magnitudes is not None else np.zeros(la.size))
    lat0 = float(np.mean(la))
    # Coordenadas locales en km.
    x = (lo - np.mean(lo)) * 111.195 * math.cos(math.radians(lat0))
    y = (la - lat0) * 111.195
    pts = np.column_stack([x, y])
    # PCA: el 2.º componente (menor varianza horizontal) ≈ perpendicular a la
    # fosa = eje de la sección transversal.
    cov = np.cov(pts.T)
    evals, evecs = np.linalg.eigh(cov)         # ascendente
    perp = evecs[:, 0]                          # menor varianza
    dist = pts @ perp                           # proyección (km)
    return [[round(float(dist[i]), 1), round(float(de[i]), 1),
             round(float(mg[i]), 1)] for i in range(la.size)]
