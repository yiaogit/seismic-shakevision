"""
Vista del cuadro de mandos (dashboard) — wrapper Qt sobre la página
HTML/ECharts de ``web/dashboard``.

Convención
----------
La lógica de **agregación** vive aquí en Python, no en JS:

  * permite testear con fixtures locales sin abrir un navegador;
  * usa numpy / itertools en lugar de reinventar la rueda en JS;
  * mantiene ``dashboard.js`` reducido a "render esto que ya viene
    listo".

Flujo
-----

  worker.earthquakes_ready  →  panel.update_earthquakes(quakes)
                                ├── _build_payload(quakes)
                                ├── runJavaScript("setAggregations(...)")
                                └── (la página dibuja las 4 gráficas)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import QObject, QUrl, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from shakevision.i18n import LocaleService, t
from shakevision.services.data_models import Earthquake, ShakeStation
from shakevision.ui.combo_utils import fit_combo
from shakevision.ui.loading_overlay import LoadingOverlay
from shakevision.ui.signal_safety import subscribe
from shakevision.ui.theme import (
    COLOR_PANEL,
    COLOR_PANEL_BORDER,
    COLOR_TEXT_SECONDARY,
)

logger = logging.getLogger(__name__)


WEB_DASHBOARD_DIR: Path = (
    Path(__file__).resolve().parent.parent / "web" / "dashboard"
)


# ============================================================
# Códigos visuales de magnitud (espejo del array MAG_BUCKETS en JS)
# ============================================================
_MAG_BUCKETS: list[tuple[str, float, float, str]] = [
    # (etiqueta, lim_bajo, lim_alto exclusivo, color)
    ("<3.0",    -1e9,  3.0,  "#38bdf8"),
    ("3.0–4.5", 3.0,   4.5,  "#facc15"),
    ("4.5–6.0", 4.5,   6.0,  "#fb923c"),
    ("6.0–7.5", 6.0,   7.5,  "#ef4444"),
    ("≥7.5",    7.5,   1e9,  "#a855f7"),
]

_DEPTH_BUCKETS: list[tuple[str, float, float]] = [
    # (etiqueta, lim_bajo inclusive, lim_alto exclusivo)
    ("0–10",    0.0,    10.0),
    ("10–35",   10.0,   35.0),
    ("35–70",   35.0,   70.0),
    ("70–150",  70.0,   150.0),
    ("150–300", 150.0,  300.0),
    ("≥300",    300.0,  1e9),
]


# ============================================================
# Mapa de algunas regiones / estados USA → país canónico
# ============================================================
_US_STATES: frozenset[str] = frozenset({
    # Nombres completos — los 50 estados + DC + territorios.
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
    "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana",
    "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
    "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
    "New Hampshire", "New Jersey", "New Mexico", "New York",
    "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon",
    "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
    "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
    "West Virginia", "Wisconsin", "Wyoming",
    "Puerto Rico", "U.S. Virgin Islands", "Guam", "American Samoa",
    "District of Columbia",
    # Códigos USPS de 2 letras: USGS los usa en muchos ``place`` de EE. UU.
    # (p. ej. "12km W of Searles Valley, CA") y sin esto se contaban como
    # "países" separados ("CA", "AK"…). Los topónimos extranjeros usan el
    # nombre completo del país, así que no hay colisión en este contexto.
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
    "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
    "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY", "DC", "PR", "GU", "VI", "AS", "MP",
})

# Aliases para regiones marítimas / mesetas oceánicas
_OCEAN_REGIONS: frozenset[str] = frozenset({
    "Mid-Atlantic Ridge", "South Sandwich Islands region",
    "South of Africa", "South of Australia",
    "central Mid-Atlantic Ridge", "northern Mid-Atlantic Ridge",
    "southern Mid-Atlantic Ridge",
})


# ============================================================
# Funciones puras (testeables sin Qt)
# ============================================================
def extract_country(place: str) -> str:
    """Extrae el país (o región) más probable del campo USGS ``place``.

    Reglas:
      * Toma el último segmento separado por coma.
      * Si coincide con un estado/territorio USA → "United States".
      * Si pertenece al conjunto de regiones oceánicas → "Open Ocean".
      * Si está vacío → "Desconocido".
    """

    if not place:
        return "Desconocido"

    last = place.rsplit(",", 1)[-1].strip()
    if not last:
        return "Desconocido"

    if last in _US_STATES:
        return "United States"
    if last in _OCEAN_REGIONS:
        return "Open Ocean"
    return last


def aggregate_by_country(
    quakes: list[Earthquake],
    top_n: int = 10,
    min_magnitude: float = 0.0,
) -> list[dict]:
    """Devuelve los ``top_n`` países más activos con su recuento.

    El parámetro ``min_magnitude`` filtra eventos de baja energía que
    no son representativos del riesgo regional. Por defecto se usa 0
    (sin filtro) para preservar la compatibilidad de los tests
    existentes; el dashboard lo invoca con ``min_magnitude=3.0`` para
    que el Top 10 refleje sismos sentidos por la población.
    """

    counts: dict[str, int] = {}
    for q in quakes:
        if q.magnitude < min_magnitude:
            continue
        country = extract_country(q.place)
        counts[country] = counts.get(country, 0) + 1
    sorted_pairs = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    return [{"name": name, "count": count} for name, count in sorted_pairs[:top_n]]


def aggregate_magnitude_buckets(quakes: list[Earthquake]) -> list[dict]:
    """Cuenta sismos por intervalo de magnitud."""

    out: list[dict] = []
    for label, lo, hi, color in _MAG_BUCKETS:
        n = sum(1 for q in quakes if lo <= q.magnitude < hi)
        out.append({"label": label, "count": n, "color": color})
    return out


def aggregate_depth_buckets(quakes: list[Earthquake]) -> list[dict]:
    """Cuenta sismos por intervalo de profundidad (km)."""

    out: list[dict] = []
    for label, lo, hi in _DEPTH_BUCKETS:
        n = sum(1 for q in quakes if lo <= q.depth_km < hi)
        out.append({"label": label, "count": n})
    return out


def build_timeline_24h(
    quakes: list[Earthquake],
    now_unix: Optional[float] = None,
    min_magnitude: float = 2.5,
    window_seconds: float = 24 * 3600,
) -> list[dict]:
    """Lista de eventos en la ventana solicitada (máx 24 h, mín 1 h).

    Se mantiene el nombre histórico ``build_timeline_24h`` por
    retrocompatibilidad de tests; el parámetro ``window_seconds`` permite
    al dashboard pasar la ventana actualmente seleccionada por el
    usuario, siempre acotada a 24 h porque más allá la línea temporal
    pierde legibilidad (demasiados puntos solapados).
    """

    import time as _time
    now = now_unix if now_unix is not None else _time.time()
    # La timeline nunca debe ser mayor de 24 h (legibilidad) ni menor
    # de 1 h (densidad útil).
    window = max(3600.0, min(float(window_seconds), 24 * 3600.0))
    cutoff = now - window
    filtered = [q for q in quakes
                if q.timestamp_unix >= cutoff and q.magnitude >= min_magnitude]
    filtered.sort(key=lambda q: q.timestamp_unix)
    return [
        {"ts": q.timestamp_unix, "mag": q.magnitude, "place": q.place}
        for q in filtered
    ]


def aggregate_pager_distribution(
    quakes: list[Earthquake],
    region: Optional[str] = None,
) -> list[dict]:
    """Cuenta sismos por nivel PAGER y devuelve también color/etiqueta.

    Solo cuentan los eventos con campo PAGER definido (USGS no asigna
    nivel a sismos pequeños). Para que el radar siempre tenga 4 ejes,
    los niveles ausentes se incluyen con count = 0.

    Si se pasa ``region`` (extraído vía ``extract_country``), solo se
    cuentan los sismos asociados a esa región. ``None`` o ``"all"`` /
    ``"todos"`` desactiva el filtro.
    """

    from shakevision.services.data_models import PAGER_VISUAL, PagerLevel

    region_norm: Optional[str] = None
    if region and region.lower() not in {"all", "todos", ""}:
        region_norm = region

    counts: dict[PagerLevel, int] = {lvl: 0 for lvl in PagerLevel}
    for q in quakes:
        if q.pager is None:
            continue
        if region_norm is not None and extract_country(q.place) != region_norm:
            continue
        counts[q.pager] += 1
    out = []
    for lvl in (PagerLevel.GREEN, PagerLevel.YELLOW,
                PagerLevel.ORANGE, PagerLevel.RED):
        color, _ = PAGER_VISUAL[lvl]
        out.append({
            "level": lvl.value,
            "label": lvl.value.upper(),
            "count": counts[lvl],
            "color": color,
        })
    return out


def list_regions(
    quakes: list[Earthquake],
    min_magnitude: float = 0.0,
) -> list[str]:
    """Lista ordenada (alfabética) de regiones presentes en el catálogo.

    Útil para poblar el desplegable de filtro de PAGER. Se descartan
    "Desconocido" y se aplica filtro de magnitud para evitar polucionar
    el desplegable con sismos micro irrelevantes.
    """

    regions: set[str] = set()
    for q in quakes:
        if q.magnitude < min_magnitude:
            continue
        c = extract_country(q.place)
        if c and c != "Desconocido":
            regions.add(c)
    return sorted(regions)


def build_timeline_density(
    quakes: list[Earthquake],
    now_unix: Optional[float] = None,
    period_seconds: float = 7 * 86400,
    min_magnitude: float = 2.5,
) -> list[dict]:
    """Burbujas diarias para periodos largos (>24 h).

    Devuelve un punto por día con:
      * ``ts``    — centro del día (ms para ECharts)
      * ``count`` — número de eventos ese día (tamaño de burbuja)
      * ``max_mag`` — magnitud máxima del día (eje Y)
      * ``avg_mag`` — magnitud promedio (color)

    La granularidad fija a 1 día funciona bien para 7 d (7 burbujas) y
    30 d (30 burbujas) — suficientemente legible y sin colapsar.
    """

    import time as _time
    now = now_unix if now_unix is not None else _time.time()
    days = max(2, int(round(period_seconds / 86400.0)))
    cutoff = now - days * 86400

    # Centros de día alineados con UTC (mediodía de cada día relativo a 'now')
    buckets: dict[int, dict[str, float]] = {}
    for q in quakes:
        if q.timestamp_unix < cutoff or q.magnitude < min_magnitude:
            continue
        day_idx = int((now - q.timestamp_unix) // 86400)  # 0 = hoy
        if day_idx >= days:
            continue
        b = buckets.setdefault(day_idx, {"count": 0, "max_mag": 0.0, "sum_mag": 0.0})
        b["count"] += 1
        b["sum_mag"] += q.magnitude
        if q.magnitude > b["max_mag"]:
            b["max_mag"] = q.magnitude

    out: list[dict] = []
    for day_idx in range(days):
        center_ts = now - (day_idx + 0.5) * 86400
        b = buckets.get(day_idx)
        if b is None:
            continue  # día sin eventos → no graficar burbuja
        out.append({
            "ts": int(center_ts * 1000),
            "count": int(b["count"]),
            "max_mag": float(b["max_mag"]),
            "avg_mag": float(b["sum_mag"] / b["count"]),
        })
    # Orden cronológico ascendente (más antiguo → más reciente)
    out.sort(key=lambda d: d["ts"])
    return out


def build_period_buckets(
    quakes: list[Earthquake],
    now_unix: Optional[float] = None,
    period_seconds: float = 24 * 3600,
) -> dict[str, Any]:
    """Histograma temporal adaptativo según el periodo seleccionado.

    Regla de granularidad
    ---------------------
      *  ≤   1 h     → 12 buckets × 5 min
      *  ≤   6 h     → 12 buckets × 30 min
      *  ≤  24 h     → 24 buckets × 1 h
      *  ≤   7 d     →  7 buckets × 1 día
      *   30 d        → 30 buckets × 1 día

    Devuelve:
        {"bucket_label": "5 min" | "30 min" | "1 h" | "1 día",
         "buckets": [{ts, count, max_mag}, ...]}
    """

    import time as _time
    now = now_unix if now_unix is not None else _time.time()
    p = float(period_seconds)

    # Elegir tamaño de bucket en segundos + etiqueta legible
    if p <= 3600:
        bucket_s, bucket_label = 5 * 60, "5 min"
    elif p <= 6 * 3600:
        bucket_s, bucket_label = 30 * 60, "30 min"
    elif p <= 24 * 3600:
        bucket_s, bucket_label = 3600, "1 h"
    else:
        bucket_s, bucket_label = 86400, "1 día"

    n_buckets = max(1, int(round(p / bucket_s)))
    start_edge = now - n_buckets * bucket_s
    edges = [start_edge + i * bucket_s for i in range(n_buckets + 1)]

    counts = [0] * n_buckets
    max_mags = [0.0] * n_buckets
    for q in quakes:
        if q.timestamp_unix < edges[0] or q.timestamp_unix >= edges[-1]:
            continue
        idx = min(n_buckets - 1, int((q.timestamp_unix - edges[0]) / bucket_s))
        counts[idx] += 1
        if q.magnitude > max_mags[idx]:
            max_mags[idx] = q.magnitude

    buckets = [
        {
            "ts": int((edges[i] + bucket_s / 2.0) * 1000),  # ms para ECharts
            "count": counts[i],
            "max_mag": max_mags[i],
        }
        for i in range(n_buckets)
    ]
    return {"bucket_label": bucket_label, "buckets": buckets}


def build_48h_trend(
    quakes: list[Earthquake],
    now_unix: Optional[float] = None,
    bucket_hours: int = 1,
) -> list[dict]:
    """Devuelve eventos por hora durante las últimas 48 h.

    Cada bucket lleva: ``ts`` (centro del bucket, ms para ECharts),
    ``count`` (número de eventos), ``max_mag`` (la mayor del bucket o 0).
    """

    import time as _time
    now = now_unix if now_unix is not None else _time.time()
    bucket_s = bucket_hours * 3600
    n_buckets = int(48 / bucket_hours)

    edges = [now - (n_buckets - i) * bucket_s for i in range(n_buckets + 1)]
    counts = [0] * n_buckets
    max_mags = [0.0] * n_buckets
    for q in quakes:
        if q.timestamp_unix < edges[0] or q.timestamp_unix >= edges[-1]:
            continue
        idx = min(n_buckets - 1, int((q.timestamp_unix - edges[0]) / bucket_s))
        counts[idx] += 1
        if q.magnitude > max_mags[idx]:
            max_mags[idx] = q.magnitude

    return [
        {
            "ts": int((edges[i] + bucket_s / 2.0) * 1000),  # ms para ECharts
            "count": counts[i],
            "max_mag": max_mags[i],
        }
        for i in range(n_buckets)
    ]


def build_depth_magnitude_scatter(
    quakes: list[Earthquake],
    now_unix: Optional[float] = None,
    hours: float = 24.0,
) -> list[dict]:
    """Lista de puntos para el scatter profundidad × magnitud."""

    import time as _time
    now = now_unix if now_unix is not None else _time.time()
    cutoff = now - hours * 3600
    out = []
    for q in quakes:
        if q.timestamp_unix < cutoff:
            continue
        out.append({
            "depth": float(q.depth_km),
            "mag": float(q.magnitude),
            "place": q.place,
            "ts": int(q.timestamp_unix * 1000),
            "pager": q.pager.value if q.pager else None,
        })
    return out


def build_station_summary(
    stations: Optional[list[ShakeStation]],
) -> dict[str, int]:
    """Cuenta estaciones disponibles por proveedor.

    Si la lista es ``None`` (el dashboard aún no ha recibido el catálogo
    de estaciones), todos los contadores quedan a 0. El dashboard usa
    estos números como KPI complementario y para etiquetar el filtro de
    fuente.
    """

    counts = {"total": 0, "shakenet": 0, "usgs": 0}
    if not stations:
        return counts
    for s in stations:
        counts["total"] += 1
        if s.provider == "usgs":
            counts["usgs"] += 1
        elif s.provider == "shakenet":
            counts["shakenet"] += 1
    return counts


def _downsample(seq: list, max_points: int = 600) -> list:
    """Reduce una serie a ≤ ``max_points`` puntos (muestreo uniforme por índice).

    La curva acumulada es monótona, así que el submuestreo conserva la forma sin
    inflar el payload con miles de puntos."""

    n = len(seq)
    if n <= max_points:
        return seq
    step = n / float(max_points)
    idx = sorted({int(i * step) for i in range(max_points)} | {n - 1})
    return [seq[i] for i in idx]


def _bbox_contains(bbox: tuple, lat: float, lon: float) -> bool:
    """¿Está (lat, lon) dentro de ``(min_lat, max_lat, min_lon, max_lon)``?"""

    try:
        return (bbox[0] <= lat <= bbox[1]) and (bbox[2] <= lon <= bbox[3])
    except (TypeError, IndexError):
        return True


def build_event_rate(quakes: list[Earthquake], now_unix: float,
                     period_seconds: float, nbins: int = 40) -> list[dict]:
    """Tasa de eventos por bin temporal (sustituye al radar PAGER).

    Devuelve ``[{"ts", "n"}, …]`` con el nº de eventos por bin a lo largo de la
    ventana — se pinta como línea/área (distinto de la distribución por
    periodo, que son barras con magnitud máxima)."""

    start = now_unix - max(60.0, float(period_seconds))
    width = (now_unix - start) / nbins
    if width <= 0:
        return []
    bins = [0] * nbins
    for q in quakes:
        idx = int((q.timestamp_unix - start) / width)
        if 0 <= idx < nbins:
            bins[idx] += 1
    return [{"ts": start + (i + 0.5) * width, "n": c}
            for i, c in enumerate(bins)]


def build_pro_stats(quakes: list[Earthquake]) -> Optional[dict[str, Any]]:
    """Estadística sísmica profesional para la capa de análisis (ver
    ``processing/seismic_stats.py``). Devuelve ``None`` si no hay eventos."""

    if not quakes:
        return None
    from shakevision.processing import seismic_stats as ss

    mags = [q.magnitude for q in quakes]
    times = [q.timestamp_unix for q in quakes]
    depths = [q.depth_km for q in quakes]

    bval = ss.b_value(mags)
    mc = bval["mc"] if bval else ss.magnitude_of_completeness(mags)

    cum = ss.cumulative_series(times, mags)
    # Submuestrear las curvas acumuladas (paralelas) si son enormes.
    if cum["t"]:
        keep = _downsample(list(range(len(cum["t"]))))
        for key in ("t", "count", "moment_cum", "energy_cum"):
            cum[key] = [cum[key][i] for i in keep]

    # Densidad espacial (rejilla lon × lat): "¿dónde se concentra la actividad?"
    # — la pregunta natural de un panorama de gran área y larga ventana. (Mejor
    # que el diagrama espacio-tiempo, que solo lee bien sobre una estructura
    # lineal; ``omori_fit`` sigue disponible para secuencias de réplicas.)
    spatial = ss.spatial_density(
        [q.longitude for q in quakes], [q.latitude for q in quakes], mags)

    # Sección transversal Wadati–Benioff (proyección ⊥ a la fosa), capada.
    section = ss.cross_section(
        [q.latitude for q in quakes], [q.longitude for q in quakes],
        depths, mags)
    section = _downsample(section, max_points=2000)

    return {
        "b_value": bval,
        "mc": mc,
        "fmd": ss.fmd(mags),
        "cumulative": cum,
        "spatial": spatial,
        "mc_b": ss.mc_b_timeseries(times, mags),
        "depth_hist": ss.depth_histogram(depths),
        "depth_pct": ss.depth_percentiles(depths),
        "inter_event": ss.inter_event_times(times),
        "section": section,
    }


def build_payload(
    quakes: list[Earthquake],
    now_unix: Optional[float] = None,
    period_seconds: float = 24 * 3600,
    stations: Optional[list[ShakeStation]] = None,
    pager_region: Optional[str] = None,
    country_min_magnitude: float = 3.0,
    region_bbox: Optional[tuple] = None,
) -> dict[str, Any]:
    """Empaqueta todas las agregaciones para la página, ya filtradas.

    Parámetros
    ----------
    quakes
        Catálogo completo (ya filtrado opcionalmente por fuente USGS/Shake).
    now_unix
        Reloj de referencia. Se permite override para tests deterministas.
    period_seconds
        Ventana temporal aplicada a TODAS las agregaciones (incluido el
        histograma adaptativo que sustituye a la antigua tendencia 48 h).
    stations
        Catálogo de estaciones para calcular ``station_summary``. Si es
        ``None`` se devuelve un summary vacío.
    pager_region
        Si se pasa un nombre de país/región, el radar PAGER se filtra a
        ese ámbito únicamente. ``None`` o ``"all"`` muestra el mundo.
    country_min_magnitude
        Filtra el Top 10 de países por magnitud mínima. Por defecto 3.0:
        evita que las regiones con muchos micro-sismos (Alaska, Hawaii)
        copen la tabla con eventos imperceptibles.
    """

    import time as _time
    now = now_unix if now_unix is not None else _time.time()
    cutoff = now - max(60.0, float(period_seconds))

    in_window = [q for q in quakes if q.timestamp_unix >= cutoff]

    # Top-10 = vista GENERAL/GLOBAL: cuenta todos los eventos (no se filtra por
    # magnitud ni por la región seleccionada) — es el ancla "qué pasa en el
    # mundo". El resto de gráficas SÍ respetan la región (ver más abajo).
    countries = aggregate_by_country(
        in_window, top_n=10, min_magnitude=country_min_magnitude,
    )
    # Filtro de REGIÓN (solo modo en vivo): acota TODO menos el Top-10 global.
    if region_bbox:
        in_window = [q for q in in_window
                     if _bbox_contains(region_bbox, q.latitude, q.longitude)]

    # ─── Timezone del usuario ───
    # Si el TimezoneService está disponible (caso normal de la app),
    # las marcas de tiempo se serializan en la zona del usuario. Si
    # falla la import (tests headless), caemos a UTC.
    try:
        from shakevision.services.timezone_service import TimezoneService
        user_tz_name = TimezoneService.current_iana()
        user_tz = TimezoneService.current_zone()
    except Exception:  # noqa: BLE001
        user_tz_name = "UTC"
        user_tz = timezone.utc

    if in_window:
        latest = max(in_window, key=lambda q: q.timestamp_unix)
        # Mantenemos formato ISO con offset — el JS lo parsea con
        # ``new Date(iso)`` que respeta el offset; pero además pasamos
        # ``timezone`` para que el JS pueda usar ``Intl.DateTimeFormat``
        # con la zona del usuario en el display.
        latest_iso = datetime.fromtimestamp(
            latest.timestamp_unix, tz=user_tz
        ).isoformat()
        max_mag = max(q.magnitude for q in in_window)
    else:
        latest_iso = None
        max_mag = None

    # La línea temporal "scatter clásica" se usa solo para ≤ 24 h.
    # Para 7 d / 30 d usamos un gráfico de burbujas por día (más legible).
    use_density_timeline = period_seconds > 24 * 3600.0
    timeline_window = min(period_seconds, 24 * 3600.0)
    if use_density_timeline:
        timeline_scatter: list[dict] = []
        timeline_density_pts = build_timeline_density(
            in_window, now_unix=now, period_seconds=period_seconds,
        )
    else:
        timeline_scatter = build_timeline_24h(
            in_window, now_unix=now, window_seconds=timeline_window,
        )
        timeline_density_pts = []

    # El scatter profundidad × magnitud usa el mismo periodo seleccionado
    scatter_hours = max(1.0, period_seconds / 3600.0)

    # Histograma adaptativo (sustituye al antiguo trend_48h fijo)
    period_hist = build_period_buckets(
        in_window, now_unix=now, period_seconds=period_seconds,
    )

    # i18n: idioma actual + tabla completa para el JS.
    try:
        current_lang = LocaleService.current_language()
        i18n_table = LocaleService.current_table()
    except Exception:  # noqa: BLE001
        current_lang = "en"
        i18n_table = {}

    return {
        # i18n
        "lang": current_lang,
        "i18n": i18n_table,
        # Zona horaria del usuario (IANA name, p.ej. "America/Mexico_City").
        # El JS la pasa a Intl.DateTimeFormat para mostrar tooltips en
        # la hora local del usuario.
        "timezone": user_tz_name,
        # KPIs (todos relativos al periodo seleccionado, no fijos a 24 h)
        "period_seconds": int(period_seconds),
        "count_24h": len(in_window),  # se mantiene el nombre por compat
        "max_magnitude": max_mag,
        "latest_iso": latest_iso,
        "country_count": len({extract_country(q.place) for q in in_window}),
        # Agregaciones (todas dentro del periodo seleccionado)
        "country_top10": countries,
        "magnitude_buckets": aggregate_magnitude_buckets(in_window),
        "depth_buckets": aggregate_depth_buckets(in_window),
        # Línea temporal en dos sabores: el JS elige cuál renderizar según
        # ``timeline_mode``. Esto evita transferir datos innecesarios.
        "timeline_mode": "density" if use_density_timeline else "scatter",
        "timeline_24h": timeline_scatter,
        "timeline_density": timeline_density_pts,
        # PAGER: con filtro de región opcional + lista de regiones
        # disponibles (M≥3.0 para que el desplegable sea útil).
        "pager_distribution": aggregate_pager_distribution(
            in_window, region=pager_region,
        ),
        "pager_region": pager_region or "all",
        "region_options": list_regions(in_window, min_magnitude=3.0),
        # Histograma adaptativo del periodo (sustituye a trend_48h fijo)
        "period_histogram": period_hist,
        # Mantener trend_48h por retrocompatibilidad (tests / código antiguo)
        "trend_48h": build_48h_trend(quakes, now_unix=now),
        "depth_mag_scatter": build_depth_magnitude_scatter(
            in_window, now_unix=now, hours=scatter_hours,
        ),
        # Resumen de estaciones (para el filtro de fuente del UI)
        "station_summary": build_station_summary(stations),
        # Capa de análisis profesional (b-value / energía / Omori / profundidad)
        "pro": build_pro_stats(in_window),
        # Tasa de eventos (sustituye al radar PAGER)
        "event_rate": build_event_rate(in_window, now, period_seconds),
        # Epicentros (lon, lat, mag) para el mapa de dispersión EN VIVO.
        "epicenters": _downsample(
            [[round(q.longitude, 3), round(q.latitude, 3),
              round(q.magnitude, 1)] for q in in_window], 1500),
        # Magnitud vs tiempo (t_ms, mag) para la secuencia en ANÁLISIS.
        "mag_time": _downsample(
            [[q.timestamp_unix * 1000.0, round(q.magnitude, 1)]
             for q in sorted(in_window, key=lambda x: x.timestamp_unix)],
            1500),
    }


# ============================================================
# Bridge Qt ↔ JS
# ============================================================
class DashboardBridge(QObject):
    """Objeto registrado en QWebChannel como ``window.bridge``."""

    dashboard_ready = Signal()
    # all_hour / all_6h / all_day / all_week / all_month
    period_changed = Signal(str)
    # nombre de región o "all" — filtro local del radar PAGER
    pager_region_changed = Signal(str)

    @Slot()
    def on_dashboard_ready(self) -> None:
        self.dashboard_ready.emit()

    @Slot(str)
    def on_period_changed(self, period: str) -> None:
        self.period_changed.emit(period)

    @Slot(str)
    def on_pager_region_changed(self, region: str) -> None:
        self.pager_region_changed.emit(region)


# ============================================================
# Panel principal
# ============================================================
class DashboardPanel(QFrame):
    """Panel del cuadro de mandos (7 gráficas + KPIs)."""

    # Reenvío de la selección del usuario al main_window
    period_changed = Signal(str)
    pager_region_changed = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("WaveformPanel")
        self.setFrameShape(QFrame.NoFrame)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._view = None
        self._bridge = None
        self._channel = None
        self._ready = False
        self._pending_payload: Optional[dict] = None
        self._got_first_data = False
        # Catálogo de estaciones recibido del worker (para KPI station_summary)
        self._stations_cache: Optional[list[ShakeStation]] = None
        # Modo análisis (catálogo histórico de una región+ventana) vs en vivo.
        self._analysis_mode = False
        self._view_mode = "live"          # "live" | "analysis" (vista actual)
        self._analysis_quakes: list = []  # último catálogo histórico (reporte)
        self._analysis_worker = None
        self._live_region_bbox: Optional[tuple] = None
        self._last_live_args: Optional[tuple] = None
        self._analysis_window_days = 365

        # Barra de análisis (región + ventana + magnitud mín) ANTES de la web.
        layout.addWidget(self._build_analysis_bar())

        try:
            self._init_web_view(layout)
        except ImportError as exc:
            logger.warning("QtWebEngine no disponible: %s", exc)
            layout.addWidget(self._fallback_label(str(exc)))
            return

        self._overlay = LoadingOverlay(self)
        self._overlay.show_loading(
            t("dashboard.loading_title"),
            t("dashboard.loading_subtitle"),
        )

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def update_earthquakes(
        self,
        quakes: list[Earthquake],
        period_seconds: float = 24 * 3600,
        pager_region: Optional[str] = None,
    ) -> None:
        """Recalcula las agregaciones y refresca las gráficas.

        El ``period_seconds`` viene desde MainWindow (que mantiene el
        estado del selector). ``pager_region`` filtra únicamente el
        radar PAGER (el resto de gráficas siempre muestra el mundo).
        """

        if self._view is None:
            return
        # Recordar el último feed en vivo para poder volver desde "Análisis".
        self._last_live_args = (list(quakes), period_seconds, pager_region)
        # En modo análisis NO pisamos el histórico con el feed en vivo.
        if self._analysis_mode:
            return
        payload = build_payload(
            quakes,
            period_seconds=period_seconds,
            stations=self._stations_cache,
            pager_region=pager_region,
            region_bbox=self._live_region_bbox,
        )
        self._push_payload(payload)
        if not self._got_first_data and hasattr(self, "_overlay"):
            self._got_first_data = True
            self._overlay.hide_overlay()

    # ------------------------------------------------------------------
    # Barra de análisis (región + ventana → consulta fdsnws-event)
    # ------------------------------------------------------------------
    def _build_analysis_bar(self) -> QWidget:
        from shakevision.services import region_presets
        from shakevision.ui.signal_safety import subscribe

        bar = QWidget()
        bar.setObjectName("DashboardAnalysisBar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(8)

        # ── Conmutador de modo (prominente): En vivo | Análisis ──
        self.an_mode_live = QPushButton(t("dashboard.live"))
        self.an_mode_an = QPushButton(t("dashboard.analyze"))
        for b in (self.an_mode_live, self.an_mode_an):
            b.setCheckable(True)
            b.setObjectName("SegmentButton")
        self.an_mode_live.setChecked(True)
        self.an_mode_live.clicked.connect(lambda: self._set_dashboard_mode("live"))
        self.an_mode_an.clicked.connect(
            lambda: self._set_dashboard_mode("analysis"))
        row.addWidget(self.an_mode_live)
        row.addWidget(self.an_mode_an)
        row.addSpacing(10)

        loc = self._current_lang()

        # ── Controles EN VIVO: selector de región (el Top-10 sigue global) ──
        self._live_controls = QWidget()
        lrow = QHBoxLayout(self._live_controls)
        lrow.setContentsMargins(0, 0, 0, 0)
        lrow.setSpacing(8)
        self._live_lbl_region = QLabel(t("hist.region"))
        lrow.addWidget(self._live_lbl_region)
        self.live_region = QComboBox()
        for key, name in region_presets.presets(loc):
            self.live_region.addItem(name, userData=key)
        self.live_region.currentIndexChanged.connect(
            self._on_live_region_changed)
        lrow.addWidget(self.live_region)
        row.addWidget(self._live_controls)
        # Nombres de región varían por idioma → medir en todos para no recortar.
        _region_samples = [name
                           for lng in LocaleService.available_languages()
                           for _k, name in region_presets.presets(lng)]
        fit_combo(self.live_region, extra=_region_samples)

        # ── Controles de análisis (ocultos en modo en vivo): 2 filas ──
        from PySide6.QtCore import QDateTime

        from shakevision.ui.range_slider import RangeSlider
        self._an_controls = QWidget()
        cwrap = QVBoxLayout(self._an_controls)
        cwrap.setContentsMargins(0, 0, 0, 0)
        cwrap.setSpacing(4)
        crow = QHBoxLayout()
        crow.setContentsMargins(0, 0, 0, 0)
        crow.setSpacing(8)
        loc = self._current_lang()
        self._an_lbl_region = QLabel(t("hist.region"))
        crow.addWidget(self._an_lbl_region)
        self.an_region = QComboBox()
        for key, name in region_presets.presets(loc):
            self.an_region.addItem(name, userData=key)
        crow.addWidget(self.an_region)
        self._an_lbl_window = QLabel(t("dashboard.window"))
        crow.addWidget(self._an_lbl_window)
        self.an_preset = QComboBox()
        for key, days in (("win_1y", 365), ("win_5y", 365 * 5),
                          ("win_10y", 365 * 10), ("preset_all", -1)):
            self.an_preset.addItem(t(f"dashboard.{key}"), userData=days)
        self.an_preset.currentIndexChanged.connect(self._on_preset_changed)
        crow.addWidget(self.an_preset)
        self._an_lbl_mag = QLabel(t("hist.min_mag"))
        crow.addWidget(self._an_lbl_mag)
        self.an_minmag = QComboBox()
        _mags = (1.0, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0)
        for v in _mags:
            self.an_minmag.addItem(f"≥ {v:.1f}", userData=v)
        # Por defecto 3.0: para estadística (b-value/Mc) hace falta bajar cerca
        # de Mc (≈ M2-3 en redes densas), NO M≥4 (deja demasiados pocos eventos).
        self.an_minmag.setCurrentIndex(_mags.index(3.0))
        crow.addWidget(self.an_minmag)
        fit_combo(self.an_region, extra=_region_samples)
        fit_combo(self.an_preset, i18n_keys=[
            "dashboard.win_1y", "dashboard.win_5y",
            "dashboard.win_10y", "dashboard.preset_all"])
        fit_combo(self.an_minmag)
        self.an_search = QPushButton(t("dashboard.search"))
        self.an_search.setObjectName("PrimaryButton")
        self.an_search.clicked.connect(self._on_search)
        crow.addWidget(self.an_search)
        crow.addStretch(1)
        self.an_status = QLabel("")
        self.an_status.setObjectName("Caption")
        crow.addWidget(self.an_status)
        cwrap.addLayout(crow)
        # Slider de rango temporal (sustituye a los calendarios). Encuadrado en
        # ~1 año por defecto (set_window acerca el rango → lo reciente no queda
        # apretado en un eje 1900-hoy).
        now = QDateTime.currentDateTimeUtc()
        self.an_slider = RangeSlider()
        self.an_slider.set_window(
            float(now.addYears(-1).toSecsSinceEpoch()),
            float(now.toSecsSinceEpoch()))
        cwrap.addWidget(self.an_slider)
        self._an_controls.setVisible(False)
        row.addWidget(self._an_controls, stretch=1)

        subscribe(self, LocaleService.language_changed_signal(),
                  self._retranslate_analysis_bar)
        return bar

    @staticmethod
    def _current_lang() -> str:
        try:
            return LocaleService.current_language() or "en"
        except Exception:  # noqa: BLE001
            return "en"

    def _run_js(self, js: str) -> None:
        if self._view is not None and self._ready:
            self._view.page().runJavaScript(js)

    def _set_dashboard_mode(self, mode: str) -> None:
        """Conmuta En vivo / Análisis: ajusta controles Qt + avisa a la web
        (que oculta el selector de periodo y reparte las gráficas por modo)."""

        is_live = (mode == "live")
        self._view_mode = "live" if is_live else "analysis"
        self.an_mode_live.setChecked(is_live)
        self.an_mode_an.setChecked(not is_live)
        self._an_controls.setVisible(not is_live)
        self._live_controls.setVisible(is_live)
        self._run_js(
            f"window.setDashboardMode && window.setDashboardMode('{mode}')")
        if is_live:
            self._analysis_mode = False
            self.an_status.setText("")
            if self._last_live_args is not None:
                q, ps, pr = self._last_live_args
                self._push_payload(build_payload(
                    q, period_seconds=ps, stations=self._stations_cache,
                    pager_region=pr, region_bbox=self._live_region_bbox))

    def report_context(self):
        """``(quakes, context)`` para el reporte según el modo ACTUAL.

        En análisis: el catálogo histórico + región + rango. En vivo: el último
        feed + periodo. El reporte usa esto para encabezar y maquetar."""

        if self._view_mode == "analysis" and self._analysis_quakes:
            lo, hi = self.an_slider.values()
            return list(self._analysis_quakes), {
                "mode": "analysis",
                "region": self.an_region.currentText(),
                "from": float(lo), "to": float(hi),
                "min_mag": self.an_minmag.currentData(),
            }
        import time as _time
        quakes, period_s, _pr = (self._last_live_args or ([], 86400.0, None))
        # El reporte se acota al PERIODO y a la REGIÓN elegidos, para que las
        # etiquetas (subtítulo, ranking, resumen) coincidan con los datos:
        #  • El feed en vivo siempre trae ~30 d (all_month); sin filtrar, un
        #    reporte de "1 d" mostraba 30 d de datos etiquetados como 1 d.
        #  • El Top-10 EN PANTALLA sigue global por diseño; aquí el reporte sí
        #    se acota. "Global" no filtra por región y se muestra "全球…".
        cutoff = _time.time() - max(60.0, float(period_s))
        quakes = [q for q in quakes if q.timestamp_unix >= cutoff]
        bbox = self._live_region_bbox
        if bbox:
            quakes = [q for q in quakes
                      if _bbox_contains(bbox, q.latitude, q.longitude)]
        ctx = {"mode": "live", "period_seconds": period_s,
               "region": self.live_region.currentText()}
        return list(quakes), ctx

    def _on_live_region_changed(self, _idx: int) -> None:
        from shakevision.services import region_presets
        self._live_region_bbox = region_presets.bbox_for(
            self.live_region.currentData())
        if self._last_live_args is not None and not self._analysis_mode:
            q, ps, pr = self._last_live_args
            self._push_payload(build_payload(
                q, period_seconds=ps, stations=self._stations_cache,
                pager_region=pr, region_bbox=self._live_region_bbox))

    def _ensure_analysis_worker(self):
        if self._analysis_worker is None:
            from shakevision.services.fdsn_worker import FDSNQueryWorker
            self._analysis_worker = FDSNQueryWorker(parent=self)
            self._analysis_worker.results.connect(self._on_analysis_results)
            self._analysis_worker.failed.connect(self._on_analysis_failed)
            self._analysis_worker.counted.connect(self._on_count)
        return self._analysis_worker

    def _on_preset_changed(self, _idx: int) -> None:
        """Preset de ventana → mueve el slider (≥0 = "hace N días", -1 = todo)."""

        from PySide6.QtCore import QDate, QDateTime, Qt
        days = self.an_preset.currentData()
        now = QDateTime.currentDateTimeUtc()
        to = float(now.toSecsSinceEpoch())
        if days == -1:
            frm = float(QDateTime(
                QDate(1900, 1, 1), now.time(), Qt.TimeSpec.UTC
            ).toSecsSinceEpoch())
        else:
            frm = float(now.addDays(-int(days)).toSecsSinceEpoch())
        # set_window encuadra el slider en la ventana elegida (eje lineal,
        # proporcional, sin apretar lo reciente).
        self.an_slider.set_window(frm, to)

    def _analysis_params(self) -> dict:
        from shakevision.services import region_presets
        lo, hi = self.an_slider.values()
        params = {
            "starttime": float(lo),
            "endtime": float(hi),
            "min_magnitude": float(self.an_minmag.currentData() or 4.5),
            "orderby": "time", "limit": 20000,
        }
        bbox = region_presets.bbox_for(self.an_region.currentData())
        if bbox is not None:
            params.update(min_latitude=bbox[0], max_latitude=bbox[1],
                          min_longitude=bbox[2], max_longitude=bbox[3])
        return params

    def _on_search(self) -> None:
        # Pre-chequeo del tope: contamos ANTES de descargar.
        self.an_status.setText(t("dashboard.querying"))
        self.an_search.setEnabled(False)
        self._ensure_analysis_worker().count(self._analysis_params())

    def _on_count(self, n: int, params: dict) -> None:
        from shakevision.services.fdsn_event import FDSN_MAX_LIMIT
        # Si el usuario cambió a "En vivo" mientras contábamos, abortamos.
        if self._view_mode != "analysis":
            self.an_search.setEnabled(True)
            self.an_status.setText("")
            return
        if n < 0:
            # No se pudo contar → seguimos igualmente con la consulta.
            self._ensure_analysis_worker().query(params)
            return
        if n > FDSN_MAX_LIMIT:
            self.an_search.setEnabled(True)
            self.an_status.setText(t("dashboard.count_over", n=f"{n:,}"))
            return
        self.an_status.setText(t("dashboard.count_estimate", n=f"{n:,}"))
        self._ensure_analysis_worker().query(params)

    def _on_analysis_results(self, quakes) -> None:
        self.an_search.setEnabled(True)
        # Resultado TARDÍO tras cambiar a "En vivo" → ignorarlo (no pisar la
        # vista en vivo ni re-bloquear el modo análisis). Antes esto causaba
        # cuelgues/sobrescrituras al alternar modos durante una consulta larga.
        if self._view_mode != "analysis":
            self.an_status.setText("")
            return
        self._analysis_mode = True
        self._analysis_quakes = list(quakes)
        try:
            from_epoch, to_epoch = self.an_slider.values()
            payload = build_payload(
                list(quakes), now_unix=to_epoch,
                period_seconds=max(3600.0, to_epoch - from_epoch),
                stations=self._stations_cache,
            )
            self._push_payload(payload)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Construir el payload de análisis falló")
            self.an_status.setText(str(exc))
            return
        if not self._got_first_data and hasattr(self, "_overlay"):
            self._got_first_data = True
            self._overlay.hide_overlay()
        self.an_status.setText(t(
            "dashboard.analyzing", n=len(quakes),
            region=self.an_region.currentText(),
            window=self.an_preset.currentText()))

    def _on_analysis_failed(self, message: str, too_many: bool) -> None:
        self.an_search.setEnabled(True)
        if self._view_mode == "analysis":
            self.an_status.setText(message)

    def _retranslate_analysis_bar(self) -> None:
        try:
            self.an_mode_live.setText(t("dashboard.live"))
            self.an_mode_an.setText(t("dashboard.analyze"))
            self._live_lbl_region.setText(t("hist.region"))
            self._an_lbl_region.setText(t("hist.region"))
            self._an_lbl_window.setText(t("dashboard.window"))
            self._an_lbl_mag.setText(t("hist.min_mag"))
            self.an_search.setText(t("dashboard.search"))
            for i, key in enumerate(("win_1y", "win_5y", "win_10y",
                                     "preset_all")):
                self.an_preset.setItemText(i, t(f"dashboard.{key}"))
        except RuntimeError:
            pass

    def update_stations(self, stations: list[ShakeStation]) -> None:
        """Recibe el catálogo de estaciones para alimentar el KPI de fuente."""

        self._stations_cache = list(stations) if stations else []

    def show_error(self, message: str) -> None:
        if hasattr(self, "_overlay"):
            self._overlay.show_error(
                t("dashboard.error_title"),
                subtitle=message,
                show_retry=True,
            )

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------
    def _push_payload(self, payload: dict) -> None:
        if not self._ready:
            self._pending_payload = payload
            return
        js = (
            f"window.shakevisionDashboard.setAggregations({json.dumps(payload)});"
        )
        self._view.page().runJavaScript(js)

    def _init_web_view(self, layout: QVBoxLayout) -> None:
        from PySide6.QtWebChannel import QWebChannel
        from PySide6.QtWebEngineCore import QWebEngineSettings
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self._view = QWebEngineView(self)
        layout.addWidget(self._view, stretch=1)

        # Permitir que el HTML local descargue ECharts desde CDN
        settings = self._view.page().settings()
        settings.setAttribute(
            QWebEngineSettings.LocalContentCanAccessRemoteUrls, True
        )
        settings.setAttribute(
            QWebEngineSettings.LocalContentCanAccessFileUrls, True
        )

        # Reenviar consola JS al logger Python
        self._view.page().javaScriptConsoleMessage = self._on_js_console

        self._bridge = DashboardBridge()
        self._bridge.dashboard_ready.connect(self._on_ready)
        self._bridge.period_changed.connect(self.period_changed)
        self._bridge.pager_region_changed.connect(self.pager_region_changed)

        self._channel = QWebChannel(self._view.page())
        self._channel.registerObject("bridge", self._bridge)
        self._view.page().setWebChannel(self._channel)

        index_path = WEB_DASHBOARD_DIR / "index.html"
        if not index_path.exists():
            raise FileNotFoundError(f"No se encontró {index_path}")
        self._view.load(QUrl.fromLocalFile(str(index_path)))

    @staticmethod
    def _on_js_console(level, message: str, line_number: int, source_id: str) -> None:
        try:
            level_int = int(level)
        except Exception:
            level_int = 0
        prefix = ("INFO", "WARN", "ERROR")[min(level_int, 2)]
        short_src = source_id.rsplit("/", 1)[-1] if source_id else "?"
        logger.warning("[Dashboard JS %s] %s:%s %s",
                       prefix, short_src, line_number, message)

    @Slot()
    def _on_ready(self) -> None:
        """Marca el dashboard como listo + oculta overlay de inmediato."""

        self._ready = True
        if hasattr(self, "_overlay"):
            self._overlay.hide_overlay()
        if self._pending_payload is not None:
            self._push_payload(self._pending_payload)
            self._pending_payload = None
        # v0.6 Phase 11: empujar el tema actual + suscribirse a cambios
        # para que las gráficas ECharts respondan al toggle dark/light.
        self._push_theme()
        # v0.7.7 (B1): subscribe() — disconnect en destroyed + guarda.
        from shakevision.ui.theme_manager import ThemeManager
        subscribe(self, ThemeManager.changed_signal(), self._push_theme)

        # v0.7.7 fix: re-traducir el dashboard al cambiar idioma (espejo del
        # globo). Sin esto, al cambiar idioma el dashboard se quedaba con la
        # tabla i18n y el locale de fechas antiguos hasta el próximo refresco
        # de datos (los tooltips del timeline seguían en chino).
        self.push_i18n()
        subscribe(self, LocaleService.language_changed_signal(),
                  self.push_i18n)

    def _push_theme(self) -> None:
        """Envía el tema Qt actual al JS del dashboard.

        El JS recompone TODAS las gráficas con la paleta correspondiente
        (ver setTheme en dashboard.js). Idempotente.
        """

        if self._view is None or not self._ready:
            return
        try:
            from shakevision.ui.theme_manager import ThemeManager
            theme = ThemeManager.current_theme()    # "dark" | "light"
        except Exception:  # noqa: BLE001
            theme = "dark"
        js = (
            "window.shakevisionDashboard.setTheme("
            f"{json.dumps(theme)});"
        )
        self._view.page().runJavaScript(js)

    def push_i18n(self) -> None:
        """Envía la tabla i18n + idioma actual al JS del dashboard.

        El JS re-traduce textos estáticos, re-formatea fechas (Intl con el
        locale de la app, no el del sistema) y re-pinta las gráficas con el
        payload cacheado, sin esperar al próximo refresco de datos. Espejo
        de ``GlobePanel.push_i18n()``.
        """

        if self._view is None or not self._ready:
            return
        try:
            table = LocaleService.current_table()
            lang = LocaleService.current_language()
        except Exception:  # noqa: BLE001
            table = {}
            lang = "en"
        js = (
            "window.shakevisionDashboard.setI18n("
            f"{json.dumps(table)}, {json.dumps(lang)});"
        )
        self._view.page().runJavaScript(js)

    def _fallback_label(self, reason: str) -> QLabel:
        label = QLabel(
            "📊 La vista de datos requiere QtWebEngine.\n\n"
            "Instálalo con:  pip install PySide6-Addons\n\n"
            f"Detalles: {reason}"
        )
        label.setWordWrap(True)
        label.setAlignment(label.alignment().Center)
        label.setStyleSheet(
            f"background-color: {COLOR_PANEL};"
            f" color: {COLOR_TEXT_SECONDARY};"
            f" border: 1px dashed {COLOR_PANEL_BORDER};"
            f" border-radius: 10px; padding: 24px;"
        )
        return label
