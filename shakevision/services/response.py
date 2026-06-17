"""Respuesta instrumental → unidades físicas (v0.7.7).

Convierte counts crudos en velocidad del suelo (m/s) usando la metadata de
respuesta del instrumento (StationXML) del servicio FDSN station de IRIS —
exactamente las estaciones IU/US que el banco de trabajo puede conectar.

Dos niveles (ver docs/workbench-assessment.md):
  * **Tiempo real / barato**: escalar counts por la SENSIBILIDAD total
    (``counts_to_velocity``) — un único escalar, unidades correctas, ignora
    la dependencia en frecuencia. Suficiente para el display en vivo y para
    una PGV mucho mejor que el gain fijo anterior.
  * **Ventana congelada / preciso**: ``remove_response_window`` hace la
    deconvolución completa con ObsPy sobre el tramo seleccionado.

El módulo degrada con gracia: si no hay red, ObsPy o metadata, los métodos
devuelven ``None`` y la UI sigue mostrando counts.
"""

from __future__ import annotations

import logging
import urllib.request
from typing import Optional

import numpy as np

from shakevision.services.cache import FileCache

logger = logging.getLogger(__name__)

# Servicio FDSN station de IRIS (mismo host que el catálogo de estaciones).
STATION_RESPONSE_URL = (
    "https://service.iris.edu/fdsnws/station/1/query"
    "?net={net}&sta={sta}&loc={loc}&cha={cha}"
    "&level=response&format=xml&nodata=404"
)
USER_AGENT = "SeismicGuard/0.7.7 (+https://github.com/yiaogit/seismic-shakevision)"
REQUEST_TIMEOUT_S = 15.0
# La respuesta instrumental cambia rara vez: cachear 30 días.
RESPONSE_TTL_S = 30 * 86400


# ----------------------------------------------------------------------
# Funciones puras (testeables sin red ni ObsPy)
# ----------------------------------------------------------------------
def counts_to_velocity(
    samples: np.ndarray, sensitivity_counts_per_m_s: float
) -> np.ndarray:
    """Escala ``samples`` (counts) a velocidad (m/s) dividiendo por la
    sensibilidad total (counts/(m/s)). Si la sensibilidad no es válida,
    devuelve la entrada sin tocar (fallback a counts)."""

    if sensitivity_counts_per_m_s and sensitivity_counts_per_m_s > 0:
        return (np.asarray(samples, dtype=np.float64)
                / float(sensitivity_counts_per_m_s)).astype(np.float32)
    return samples


def scale_velocity_units(value_m_s: float) -> tuple[float, str]:
    """Devuelve ``(valor, unidad)`` legible para una velocidad en m/s.

    Escala a nm/s, µm/s, mm/s o m/s según la magnitud, para que el readout
    no muestre ``0.000000123 m/s``.
    """

    v = abs(float(value_m_s))
    if v == 0.0:
        return 0.0, "m/s"
    if v < 1e-6:
        return value_m_s * 1e9, "nm/s"
    if v < 1e-3:
        return value_m_s * 1e6, "µm/s"
    if v < 1.0:
        return value_m_s * 1e3, "mm/s"
    return value_m_s, "m/s"


# ----------------------------------------------------------------------
# Servicio (red + ObsPy, perezoso y defensivo)
# ----------------------------------------------------------------------
class ResponseService:
    """Obtiene y cachea la respuesta instrumental por canal SEED."""

    def __init__(self, cache: Optional[FileCache] = None) -> None:
        self._cache = cache or FileCache()
        # seed_id → (inventory, sensitivity). Memo en proceso.
        self._memo: dict[str, tuple[object, Optional[float]]] = {}

    # -- API pública --------------------------------------------------
    def sensitivity_for(
        self, net: str, sta: str, loc: str, cha: str
    ) -> Optional[float]:
        """Sensibilidad total en counts/(m/s), o ``None`` si no disponible."""

        seed = self._seed_id(net, sta, loc, cha)
        if seed in self._memo:
            return self._memo[seed][1]
        inv, sens = self._load(net, sta, loc, cha)
        self._memo[seed] = (inv, sens)
        return sens

    def inventory_for(self, net: str, sta: str, loc: str, cha: str):
        """Devuelve el ``Inventory`` de ObsPy (con respuesta) o ``None``.

        Pensado para deconvolución a nivel de Stream: ``cha`` puede llevar
        comodín (p. ej. ``BH?``) para traer las 3 componentes en un solo
        StationXML. A diferencia de ``_load``, NO llama a ``get_response``
        (que no admite seed-id con comodín). Cacheado vía el cache de XML.
        """

        xml = self._fetch_stationxml(net, sta, loc, cha)
        if xml is None:
            return None
        try:
            import io
            from obspy import read_inventory
            return read_inventory(io.BytesIO(xml))
        except Exception as exc:  # noqa: BLE001
            logger.debug("inventory_for: read_inventory falló (%s)", exc)
            return None

    def coordinates_for(
        self, net: str, sta: str, loc: str, cha: str
    ) -> Optional[tuple[float, float]]:
        """``(lat, lon)`` de la estación (grados) o ``None`` si no disponible.

        Lo usa Replay para calcular la distancia epicentral y los tiempos de
        llegada teóricos (TauP). Degrada con gracia (sin red/metadata → None).
        """

        inv, _ = self._load(net, sta, loc, cha)
        if inv is None:
            return None
        try:
            from obspy import UTCDateTime
            coords = inv.get_coordinates(
                self._seed_id(net, sta, loc, cha), UTCDateTime())
            return float(coords["latitude"]), float(coords["longitude"])
        except Exception as exc:  # noqa: BLE001
            logger.debug("No se pudieron leer coordenadas de estación (%s)", exc)
            return None

    def remove_response_window(
        self, samples: np.ndarray, sample_rate_hz: float,
        net: str, sta: str, loc: str, cha: str,
        output: str = "VEL",
    ) -> Optional[np.ndarray]:
        """Deconvolución completa de un tramo con ObsPy. ``None`` si falla.

        ``output``: "VEL" (m/s), "DISP" (m) o "ACC" (m/s²).
        """

        inv, _ = self._load(net, sta, loc, cha)
        if inv is None or samples is None or samples.size == 0:
            return None
        try:
            from obspy import Trace, UTCDateTime
            tr = Trace(data=np.asarray(samples, dtype=np.float64))
            tr.stats.network = net
            tr.stats.station = sta
            tr.stats.location = "" if loc in ("--", "*") else loc
            tr.stats.channel = cha
            tr.stats.sampling_rate = float(sample_rate_hz)
            tr.stats.starttime = UTCDateTime()
            tr.remove_response(inventory=inv, output=output,
                               water_level=60, taper=True)
            return tr.data.astype(np.float32)
        except Exception as exc:  # noqa: BLE001
            logger.debug("remove_response falló (%s)", exc)
            return None

    # -- Internos -----------------------------------------------------
    @staticmethod
    def _seed_id(net: str, sta: str, loc: str, cha: str) -> str:
        return f"{net}.{sta}.{loc}.{cha}"

    def _load(self, net, sta, loc, cha):
        """Devuelve (inventory|None, sensitivity|None), cacheado en proceso."""

        seed = self._seed_id(net, sta, loc, cha)
        if seed in self._memo:
            return self._memo[seed]
        xml = self._fetch_stationxml(net, sta, loc, cha)
        if xml is None:
            return None, None
        try:
            import io
            from obspy import UTCDateTime, read_inventory
            inv = read_inventory(io.BytesIO(xml))
            resp = inv.get_response(seed, UTCDateTime())
            sens = float(resp.instrument_sensitivity.value)
        except Exception as exc:  # noqa: BLE001
            logger.debug("No se pudo parsear StationXML/sensibilidad (%s)", exc)
            return None, None
        return inv, sens

    def _fetch_stationxml(self, net, sta, loc, cha) -> Optional[bytes]:
        loc_param = loc if loc not in ("", "*") else "--"
        key = f"stationxml__{net}_{sta}_{loc_param}_{cha}"
        cached = self._cache.get(key, ttl_s=RESPONSE_TTL_S)
        if cached:
            return cached
        url = STATION_RESPONSE_URL.format(
            net=net, sta=sta, loc=loc_param, cha=cha)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
                data = resp.read()
        except Exception as exc:  # noqa: BLE001
            logger.debug("StationXML fetch falló %s (%s)", url, exc)
            return None
        if data:
            self._cache.set(key, data)
        return data
