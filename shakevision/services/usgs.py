"""
Cliente para los feeds GeoJSON de la USGS.

La USGS publica un conjunto fijo de feeds resumen en
``earthquake.usgs.gov/earthquakes/feed/v1.0/summary/``: por cada
ventana temporal (hora / día / semana / mes) y umbral de magnitud
(1.0+, 2.5+, 4.5+, significant) hay un fichero GeoJSON. Esos feeds
se actualizan cada minuto y son **públicos sin autenticación**.

Aquí:

  * exponemos los presets más útiles en ``USGS_FEEDS``;
  * el método ``USGSClient.fetch_recent`` baja el feed (con caché
    local de 5 min para evitar hammering) y lo parsea a una lista de
    ``Earthquake`` ya enriquecidos con el nivel PAGER cuando existe.

Sin dependencias externas: solo ``urllib`` + ``json`` de la stdlib.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Final, Optional

from shakevision.i18n import t
from shakevision.services.cache import FileCache
from shakevision.services.data_models import Earthquake, PagerLevel

logger = logging.getLogger(__name__)


# ============================================================
# Catálogo de feeds soportados
# ============================================================
USGS_FEEDS: Final[dict[str, str]] = {
    "all_hour":          "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson",
    "all_day":           "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson",
    "all_week":          "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_week.geojson",
    "all_month":         "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_month.geojson",
    "significant_day":   "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_day.geojson",
    "significant_week":  "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_week.geojson",
    "significant_month": "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_month.geojson",
}

# TTL por defecto de la caché del cliente (segundos). El feed real se
# actualiza cada minuto, pero 5 min es un buen compromiso entre
# frescura y respetar al servidor.
DEFAULT_TTL_S: Final[float] = 300.0

# Timeout para las peticiones HTTP.
REQUEST_TIMEOUT_S: Final[float] = 15.0

# User-Agent recomendado por USGS para identificar la app.
USER_AGENT: Final[str] = "SeismicGuard/0.1 (+https://github.com/yourname/SeismicGuard)"


class USGSError(Exception):
    """Error genérico al obtener o parsear datos de USGS."""


class USGSClient:
    """Cliente síncrono de los feeds GeoJSON de USGS.

    Es un objeto ligero: pasa cualquier ``FileCache`` para evitar
    accesos a red repetidos. Para uso desde la UI, envuélvelo en
    ``services.worker.DataRefreshWorker``.
    """

    def __init__(
        self,
        cache: Optional[FileCache] = None,
        ttl_s: float = DEFAULT_TTL_S,
    ) -> None:
        self._cache = cache or FileCache()
        self._ttl = float(ttl_s)

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def fetch_recent(
        self,
        period: str = "all_day",
        force_refresh: bool = False,
    ) -> list[Earthquake]:
        """Devuelve los sismos del feed indicado (orden cronológico inverso).

        Si la caché tiene una versión fresca y ``force_refresh`` es
        falso, devuelve directamente el contenido cacheado y NO toca
        la red.
        """

        url = USGS_FEEDS.get(period)
        if url is None:
            raise USGSError(f"feed desconocido: {period!r}")

        cache_key = f"usgs__{period}__geojson"

        # Cache hit fresco
        if not force_refresh:
            cached = self._cache.get(cache_key, ttl_s=self._ttl)
            if cached is not None:
                try:
                    return parse_usgs_geojson(cached)
                except USGSError as exc:
                    logger.warning("Caché USGS corrupta: %s", exc)
                    self._cache.invalidate(cache_key)

        # Hit a la red
        try:
            payload = self._http_get(url)
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
            # Sin red: si tenemos algo cacheado (aunque haya caducado)
            # devolvemos eso en vez de fallar duro.
            stale = self._cache.get(cache_key, ttl_s=float("inf"))
            if stale is not None:
                logger.warning(
                    "USGS inalcanzable (%s); devolviendo caché obsoleta.", exc
                )
                return parse_usgs_geojson(stale)
            raise USGSError(t("error.usgs.contact", error=str(exc))) from exc

        # Guardar en caché y devolver parseado
        self._cache.set(cache_key, payload)
        return parse_usgs_geojson(payload)

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------
    @staticmethod
    def _http_get(url: str) -> bytes:
        """GET HTTP simple con User-Agent y timeout."""

        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
            return resp.read()


# ============================================================
# Parsing
# ============================================================
def parse_usgs_geojson(raw: bytes) -> list[Earthquake]:
    """Convierte el GeoJSON crudo en una lista ordenada de Earthquake."""

    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise USGSError(f"JSON inválido: {exc}") from exc

    features = doc.get("features")
    if not isinstance(features, list):
        raise USGSError("falta el array 'features' en el GeoJSON")

    out: list[Earthquake] = []
    for feat in features:
        try:
            out.append(_parse_feature(feat))
        except (KeyError, TypeError, ValueError) as exc:
            # Saltarse features malformadas pero no romper el feed entero.
            logger.debug("feature USGS ignorada: %s", exc)

    # Orden cronológico inverso (más reciente primero)
    out.sort(key=lambda e: e.timestamp_unix, reverse=True)
    return out


def _parse_feature(feat: dict) -> Earthquake:
    """Convierte un único Feature de GeoJSON en un Earthquake."""

    props = feat.get("properties") or {}
    geom = feat.get("geometry") or {}
    coords = geom.get("coordinates") or []

    if len(coords) < 3:
        raise ValueError("coordenadas incompletas")

    longitude = float(coords[0])
    latitude = float(coords[1])
    depth_km = float(coords[2])

    # USGS reporta el tiempo en milisegundos UNIX
    time_ms = props.get("time")
    if time_ms is None:
        raise ValueError("falta 'time' en propiedades")
    timestamp_unix = float(time_ms) / 1000.0

    return Earthquake(
        id=str(feat.get("id") or props.get("code") or ""),
        timestamp_unix=timestamp_unix,
        longitude=longitude,
        latitude=latitude,
        depth_km=depth_km,
        magnitude=float(props.get("mag") or 0.0),
        place=str(props.get("place") or ""),
        url=str(props.get("url") or ""),
        pager=PagerLevel.parse(props.get("alert")),
        significance=int(props.get("sig") or 0),
    )
