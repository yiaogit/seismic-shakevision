"""
Cliente FDSN para el catálogo de estaciones Raspberry Shake.

Raspberry Shake expone su catálogo a través de un servicio web FDSN
estándar (el mismo que usan IRIS, INGV, GFZ…) en
``fdsnws.raspberryshake.org``. Aquí solo necesitamos la lista plana
de estaciones, no las respuestas instrumentales completas, por lo que
pedimos formato ``text`` (más liviano que XML/json y trivial de
parsear).

Ejemplo de fila ``text`` que recibimos:

    #Network|Station|Latitude|Longitude|Elevation|SiteName|StartTime|EndTime
    AM|R0E05|40.4168|-3.7038|650.0|My Backyard|2018-01-01T00:00:00|...

Cacheamos por defecto **1 hora** porque el catálogo cambia muy lento.
"""

from __future__ import annotations

import logging
import urllib.error
import urllib.request
from typing import Final, Optional

from shakevision.services.cache import FileCache
from shakevision.services.data_models import ShakeStation

logger = logging.getLogger(__name__)


# Endpoint FDSN oficial del catálogo Raspberry Shake.
#
# IMPORTANTE — el host correcto es `data.raspberryshake.org`, NO el
# antiguo `fdsnws.raspberryshake.org` (CNAME deprecado que devuelve
# 0 estaciones). Confirmado en https://manual.raspberryshake.org/fdsn.html
#
# Parámetros:
#   net=AM             → red de Raspberry Shake (única)
#   level=station      → solo metadatos de estación (sin canales/resp)
#   format=text        → CSV plano, ~10× más ligero que XML
#   starttime/endtime  → ventana de actividad (sin estos suele devolver 0)
#   nodata=404         → fuerza HTTP 404 ante "sin datos" para distinguir
#                         de 200 con cuerpo vacío
SHAKENET_STATION_URL: Final[str] = (
    "https://data.raspberryshake.org/fdsnws/station/1/query"
    "?net={network}&level=station&format=text"
    "&starttime=2014-01-01"
    "&endtime=2099-12-31"
    "&nodata=404"
)

DEFAULT_TTL_S: Final[float] = 3600.0  # 1 hora
REQUEST_TIMEOUT_S: Final[float] = 20.0
USER_AGENT: Final[str] = (
    "SeismicGuard/0.1 (+https://github.com/yourname/SeismicGuard)"
)


class ShakeNetError(Exception):
    """Error genérico al obtener o parsear el catálogo de estaciones."""


class ShakeNetClient:
    """Cliente síncrono del servicio FDSN de Raspberry Shake."""

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
        network: str = "AM",
        force_refresh: bool = False,
    ) -> list[ShakeStation]:
        """Devuelve todas las estaciones de la red indicada.

        Igual que ``USGSClient``, si la red falla pero la caché tiene
        cualquier versión guardada (aunque haya caducado), la devuelve
        en lugar de lanzar.
        """

        cache_key = f"shakenet__{network}__stations"

        if not force_refresh:
            cached = self._cache.get(cache_key, ttl_s=self._ttl)
            if cached is not None:
                try:
                    return parse_fdsn_text(cached)
                except ShakeNetError as exc:
                    logger.warning("Caché ShakeNet corrupta: %s", exc)
                    self._cache.invalidate(cache_key)

        url = SHAKENET_STATION_URL.format(network=network)

        try:
            payload = self._http_get(url)
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
            stale = self._cache.get(cache_key, ttl_s=float("inf"))
            if stale is not None:
                logger.warning(
                    "ShakeNet inalcanzable (%s); devolviendo caché obsoleta.", exc
                )
                return parse_fdsn_text(stale)
            raise ShakeNetError(f"no se pudo contactar a ShakeNet: {exc}") from exc

        self._cache.set(cache_key, payload)
        return parse_fdsn_text(payload)

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------
    @staticmethod
    def _http_get(url: str) -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
            return resp.read()


# ============================================================
# Parsing
# ============================================================
def parse_fdsn_text(raw: bytes) -> list[ShakeStation]:
    """Convierte la respuesta FDSN format=text en una lista de estaciones.

    El formato es muy simple:

      #Network|Station|Latitude|Longitude|Elevation|SiteName|StartTime|EndTime
      AM|R0E05|40.4|-3.7|650.0|Madrid|...|...

    La primera línea (con ``#`` al inicio) es la cabecera y se ignora.
    """

    text = raw.decode("utf-8", errors="replace")
    out: list[ShakeStation] = []

    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("|")
        if len(parts) < 5:
            logger.debug("línea FDSN ignorada (muy corta): %s", line)
            continue
        try:
            station = ShakeStation(
                network=parts[0].strip(),
                code=parts[1].strip(),
                latitude=float(parts[2]),
                longitude=float(parts[3]),
                elevation_m=float(parts[4]),
                site_name=(parts[5].strip() if len(parts) > 5 else ""),
            )
        except (ValueError, IndexError) as exc:
            logger.debug("línea FDSN inválida en %d: %s (%s)", line_no, line, exc)
            continue
        out.append(station)

    if not out:
        # Si el body estaba bien formado pero vacío, devolvemos lista
        # vacía (no es un error). Si no encontramos NI cabecera tampoco,
        # asumimos que recibimos basura.
        if not text.lstrip().startswith("#"):
            raise ShakeNetError("respuesta FDSN sin cabecera reconocible")
        logger.warning(
            "ShakeNet devolvió 0 estaciones. Cabecera presente pero sin "
            "filas. Puede ser que el endpoint requiera otros parámetros, "
            "o que el cortafuegos lo bloquee."
        )

    logger.info("ShakeNet: parseadas %d estaciones", len(out))
    return out
