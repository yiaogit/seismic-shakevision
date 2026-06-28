"""Pruebas de ``processing.seismic_stats`` (puro, numpy/scipy, sin Qt)."""

from __future__ import annotations

import math

import numpy as np

from shakevision.processing import seismic_stats as ss


# ----------------------------------------------------------------------
# b-value / Mc / FMD
# ----------------------------------------------------------------------
def _synthetic_gr(b_true: float, mc: float, n: int, seed: int = 42,
                  dm: float = 0.1):
    """Catálogo GR sintético: magnitudes exponenciales discretizadas a ``dm``.

    Se muestrea desde ``mc - dm/2`` para que el bin de completitud (centro Mc)
    quede LLENO; así la corrección de binning de Aki–Utsu (Mc − dm/2) recupera
    el b verdadero (si se muestrea desde Mc, ese bin queda a medias y sesga b).
    """

    rng = np.random.default_rng(seed)
    beta = b_true * math.log(10.0)
    mags = (mc - dm / 2.0) + rng.exponential(1.0 / beta, n)
    return np.round(mags / dm) * dm          # discretiza a la rejilla dm


def test_b_value_recovers_known_b() -> None:
    mags = _synthetic_gr(b_true=1.0, mc=2.0, n=30000)
    res = ss.b_value(mags, mc=2.0)
    assert res is not None
    assert abs(res["b"] - 1.0) < 0.07
    assert res["b_err"] > 0
    assert res["n"] > 20000


def test_b_value_recovers_different_b() -> None:
    mags = _synthetic_gr(b_true=0.8, mc=3.0, n=30000, seed=7)
    res = ss.b_value(mags, mc=3.0)
    assert abs(res["b"] - 0.8) < 0.07


def test_mc_maxc_in_range() -> None:
    mags = _synthetic_gr(b_true=1.0, mc=2.0, n=20000)
    mc = ss.magnitude_of_completeness(mags)
    assert mc is not None
    assert 2.0 <= mc <= 2.6          # MAXC del pico + 0.2


def test_fmd_cumulative_is_monotonic() -> None:
    mags = _synthetic_gr(b_true=1.0, mc=2.0, n=5000)
    d = ss.fmd(mags)
    cum = d["cumulative"]
    assert cum == sorted(cum, reverse=True)        # N(≥M) decrece
    assert cum[0] == 5000                          # el primer bin acumula todo
    assert len(d["mag"]) == len(d["incremental"]) == len(cum)


def test_small_sample_returns_none() -> None:
    assert ss.b_value([1.0, 2.0, 3.0]) is None
    assert ss.magnitude_of_completeness([1.0, 2.0]) is None


# ----------------------------------------------------------------------
# Momento / energía
# ----------------------------------------------------------------------
def test_seismic_moment_known() -> None:
    assert math.isclose(ss.seismic_moment(0.0), 10 ** 9.1, rel_tol=1e-9)
    # +1 de magnitud → ×10^1.5 en momento
    assert math.isclose(
        ss.seismic_moment(6.0) / ss.seismic_moment(5.0), 10 ** 1.5, rel_tol=1e-9)


def test_energy_known() -> None:
    assert math.isclose(ss.energy_joules(0.0), 10 ** 4.8, rel_tol=1e-9)
    # +2 de magnitud → ×1000 en energía
    assert math.isclose(
        ss.energy_joules(7.0) / ss.energy_joules(5.0), 1000.0, rel_tol=1e-9)


def test_cumulative_series_sorted_increasing() -> None:
    times = [300.0, 100.0, 200.0]
    mags = [5.0, 6.0, 4.0]
    s = ss.cumulative_series(times, mags)
    assert s["t"] == [100.0, 200.0, 300.0]      # ordenado por tiempo
    assert s["count"] == [1, 2, 3]
    assert s["moment_cum"][0] < s["moment_cum"][1] < s["moment_cum"][2]
    # el momento del M6 (en t=100) domina la suma
    assert s["moment_cum"][-1] > ss.seismic_moment(6.0)


# ----------------------------------------------------------------------
# Omori
# ----------------------------------------------------------------------
def test_omori_fits_decaying_sequence() -> None:
    # Muestreo por inversa de densidad ∝ (t+c)^-p (Omori), p=1.1, c=0.05.
    rng = np.random.default_rng(3)
    p, c, T = 1.1, 0.05, 100.0
    u = rng.random(4000)
    # CDF inversa de (t+c)^-p en [0,T]
    a = (c) ** (1 - p)
    bb = (T + c) ** (1 - p)
    days = (a + u * (bb - a)) ** (1.0 / (1 - p)) - c
    t0 = 1_700_000_000.0
    times = t0 + days * 86400.0
    res = ss.omori_fit(times, t_main=t0)
    assert res is not None
    assert 0.5 <= res["p"] <= 2.0       # recupera un p plausible
    assert res["K"] > 0


def test_omori_none_for_few_events() -> None:
    assert ss.omori_fit([1.0, 2.0, 3.0]) is None


def test_omori_rejects_non_aftershock_catalog() -> None:
    """Con magnitudes uniformes (sin mainshock dominante) → None (no espurio)."""

    rng = np.random.default_rng(11)
    t0 = 1_600_000_000.0
    times = t0 + np.sort(rng.uniform(0, 365 * 5 * 86400, 3000))
    mags = rng.uniform(4.0, 5.2, 3000)          # ninguno domina
    assert ss.omori_fit(times, magnitudes=mags) is None


def test_omori_accepts_real_aftershock_sequence() -> None:
    rng = np.random.default_rng(5)
    p, c, T = 1.1, 0.05, 100.0
    u = rng.random(3000)
    a, bb = c ** (1 - p), (T + c) ** (1 - p)
    days = (a + u * (bb - a)) ** (1.0 / (1 - p)) - c
    t0 = 1_700_000_000.0
    times = np.concatenate([[t0], t0 + np.sort(days) * 86400.0])
    # mainshock M7.5 dominante + réplicas <6
    mags = np.concatenate([[7.5], rng.uniform(3.0, 5.8, 3000)])
    res = ss.omori_fit(times, magnitudes=mags, t_main=t0)
    assert res is not None and 0.5 <= res["p"] <= 2.0


# ----------------------------------------------------------------------
# Mc(t) / b(t) — calidad del catálogo
# ----------------------------------------------------------------------
def test_mc_b_timeseries_shape() -> None:
    mags = _synthetic_gr(b_true=1.0, mc=2.0, n=4000)
    times = 1_600_000_000.0 + np.arange(mags.size) * 3600.0
    s = ss.mc_b_timeseries(times, mags, n_windows=8, min_per_window=100)
    assert s is not None
    assert len(s["t"]) >= 2
    assert len(s["t"]) == len(s["b"]) == len(s["mc"]) == len(s["b_err"])
    assert all(0.5 < b < 1.6 for b in s["b"])      # b estable ≈ 1


def test_mc_b_timeseries_none_small() -> None:
    assert ss.mc_b_timeseries([1, 2, 3], [4, 5, 6]) is None


# ----------------------------------------------------------------------
# Sección transversal (Wadati–Benioff)
# ----------------------------------------------------------------------
def test_cross_section_projects_dip() -> None:
    """Fosa N-S, profundidad crece hacia el E → la proyección perpendicular
    (≈ E-O) debe correlacionar con la profundidad."""

    rng = np.random.default_rng(2)
    n = 400
    lat = rng.uniform(-35, -20, n)              # eje largo N-S
    lon = rng.uniform(-72, -66, n)              # eje corto E-O
    depth = (lon + 72) * 25 + rng.normal(0, 10, n)   # más al E = más profundo
    sec = ss.cross_section(lat, lon, depth)
    assert len(sec) == n
    assert all(len(row) == 3 for row in sec)
    dist = np.array([r[0] for r in sec])
    dep = np.array([r[1] for r in sec])
    corr = abs(np.corrcoef(dist, dep)[0, 1])
    assert corr > 0.6                           # proyección capta el buzamiento


def test_cross_section_empty_small() -> None:
    assert ss.cross_section([1.0], [2.0], [3.0]) == []


# ----------------------------------------------------------------------
# Profundidad
# ----------------------------------------------------------------------
def test_depth_histogram_counts_sum() -> None:
    depths = [5, 10, 12, 70, 80, 300, 310, 320]
    h = ss.depth_histogram(depths, bin_km=25.0)
    assert sum(h["counts"]) == len(depths)
    assert len(h["edges"]) == len(h["counts"]) + 1


def test_depth_percentiles_ordered() -> None:
    p = ss.depth_percentiles([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    assert p["min"] <= p["p10"] <= p["p50"] <= p["p90"] <= p["max"]
    assert p["n"] == 10
    assert ss.depth_percentiles([]) is None


def test_spatial_density_none_small() -> None:
    assert ss.spatial_density([1, 2], [1, 2]) is None
    assert ss.spatial_density([], []) is None


def test_spatial_density_counts_and_bins() -> None:
    rng = np.random.default_rng(3)
    # Dos cúmulos separados → la rejilla debe registrar conteos en ambos.
    lon = np.concatenate([rng.normal(-120, 0.3, 60), rng.normal(140, 0.3, 40)])
    lat = np.concatenate([rng.normal(35, 0.3, 60), rng.normal(-5, 0.3, 40)])
    mag = rng.uniform(1, 6, 100)
    r = ss.spatial_density(lon, lat, mag, target_bins=36)
    assert r is not None
    # La suma de conteos de las celdas = nº de eventos.
    assert sum(c[2] for c in r["cells"]) == 100
    assert r["step"] > 0
    # mag_máx por celda dentro del rango de entrada.
    assert all(1.0 <= c[3] <= 6.0 for c in r["cells"])
    # Los dos cúmulos están lejos → más de una celda ocupada.
    assert len(r["cells"]) >= 2


def test_inter_event_times_none_small() -> None:
    assert ss.inter_event_times([1, 2, 3]) is None
    assert ss.inter_event_times([]) is None


def test_inter_event_times_shape_and_counts() -> None:
    rng = np.random.default_rng(7)
    # Proceso de Poisson: tiempos entre eventos exponenciales (tasa 1/h).
    gaps = rng.exponential(scale=3600.0, size=500)
    times = np.cumsum(gaps)
    r = ss.inter_event_times(times, n_bins=20)
    assert r is not None
    assert len(r["hours"]) == 20
    assert len(r["counts"]) == 20
    # Todos los intervalos caen en algún bin → suma = N-1 muestras válidas.
    assert sum(r["counts"]) == len(gaps) - 1
    assert r["median_h"] > 0
    # Centros de bin estrictamente crecientes (eje log de horas).
    assert all(b > a for a, b in zip(r["hours"], r["hours"][1:]))
