"""
Cliente FDSN del Incorporated Research Institutions for Seismology (IRIS).

IRIS opera el centro de datos sísmico de referencia mundial. A través
de su servicio FDSN ofrece, entre muchas cosas, los catálogos de las
redes profesionales del USGS:

  * **IU** — Global Seismograph Network (≈ 150 estaciones)
  * **US** — USGS National Seismograph Network (≈ 250 estaciones EE.UU.)

Las estaciones devueltas se etiquetan con ``provider="usgs"`` para
que el frontend pueda colorearlas de forma distinta a las Raspberry
Shake (citizen science).

Reutilizamos ``parse_fdsn_text`` de ``services.shakenet`` porque el
formato es el mismo estándar FDSN.

Endpoint: https://service.iris.edu/fdsnws/station/1/query
"""

from __future__ import annotations

import logging
import urllib.error
import urllib.request
from typing import Final, Optional

from dataclasses import replace

from shakevision.services.cache import FileCache
from shakevision.services.data_models import ShakeStation
from shakevision.services.shakenet import parse_fdsn_text, ShakeNetError

logger = logging.getLogger(__name__)


# Endpoint público IRIS — sin autenticación, sin límite de tasa estricto
IRIS_STATION_URL: Final[str] = (
    "https://service.iris.edu/fdsnws/station/1/query"
    "?net={networks}&level=station&format=text"
    "&starttime=2010-01-01"
    "&endtime=2099-12-31"
    "&nodata=404"
)

# Redes USGS por defecto (globales + EE.UU. continental)
DEFAULT_USGS_NETWORKS: Final[str] = "IU,US"

DEFAULT_TTL_S: Final[float] = 3600.0 * 6   # 6 horas (catálogo cambia lento)
REQUEST_TIMEOUT_S: Final[float] = 20.0
USER_AGENT: Final[str] = (
    "SeismicGuard/0.1 (+https://github.com/yourname/SeismicGuard)"
)


class IRISError(Exception):
    """Error genérico al obtener o parsear el catálogo IRIS/USGS."""


class IRISClient:
    """Cliente síncrono del servicio FDSN de IRIS / USGS."""

    def __init__(
        self,
        cache: Optional[FileCache] = None,
        ttl_s: float = DEFAULT_TTL_S,
    ) -> None:
        self._cache = cache or FileCache()
        self._ttl = float(ttl_s)

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------
    def fetch_stations(
        self,
        networks: str = DEFAULT_USGS_NETWORKS,
        force_refresh: bool = False,
    ) -> list[ShakeStation]:
        """Devuelve las estaciones USGS marcadas con ``provider="usgs"``."""

        cache_key = f"iris__{networks.replace(',', '_')}__stations"

        if not force_refresh:
            cached = self._cache.get(cache_key, ttl_s=self._ttl)
            if cached is not None:
                try:
                    return self._tag_as_usgs(parse_fdsn_text(cached))
                except ShakeNetError as exc:
                    logger.warning("Caché IRIS corrupta: %s", exc)
                    self._cache.invalidate(cache_key)

        url = IRIS_STATION_URL.format(networks=networks)

        try:
            payload = self._http_get(url)
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
            stale = self._cache.get(cache_key, ttl_s=float("inf"))
            if stale is not None:
                logger.warning(
                    "IRIS inalcanzable (%s); devolviendo caché obsoleta.", exc
                )
                return self._tag_as_usgs(parse_fdsn_text(stale))
            raise IRISError(f"no se pudo contactar a IRIS: {exc}") from exc

        self._cache.set(cache_key, payload)
        stations = self._tag_as_usgs(parse_fdsn_text(payload))
        logger.info("IRIS/USGS: %d estaciones cargadas (%s)",
                    len(stations), networks)
        return stations

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------
    @staticmethod
    def _tag_as_usgs(stations: list[ShakeStation]) -> list[ShakeStation]:
        """Marca cada estación con provider='usgs' para colorearla."""

        # Los dataclasses son frozen → usamos ``replace`` para no mutar.
        return [replace(s, provider="usgs") for s in stations]

    @staticmethod
    def _http_get(url: str) -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
            return resp.read()
