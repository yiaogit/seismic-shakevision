"""
Cliente para el servicio de **catálogo histórico** de la USGS,
``fdsnws-event`` (ANSS ComCat, retrocede a ~1900).

A diferencia de los *summary feeds* (``services/usgs.py``), que son ficheros
fijos de ventana ≤ 1 mes, este endpoint es una **consulta por parámetros**:
tiempo, magnitud, caja geográfica, orden y paginación. Devuelve el MISMO
GeoJSON que los feeds, así que reutilizamos ``parse_usgs_geojson``.

Endpoint:
    https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&…

Restricciones del servicio (las modelamos explícitamente):
  * **Máximo 20 000 eventos por consulta** → si se supera, el servidor
    responde 400; lo traducimos a un error claro pidiendo acotar.
  * Es bajo demanda → cacheamos por clave de consulta (no por "periodo").

Sin dependencias externas: ``urllib`` + ``json`` de la stdlib (igual que
``usgs.py``).
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Final, Optional

from shakevision.i18n import t
from shakevision.services.cache import FileCache
from shakevision.services.data_models import Earthquake
from shakevision.services.usgs import (
    USER_AGENT,
    parse_usgs_geojson,
)

logger = logging.getLogger(__name__)

FDSN_EVENT_URL: Final[str] = "https://earthquake.usgs.gov/fdsnws/event/1/query"
FDSN_COUNT_URL: Final[str] = "https://earthquake.usgs.gov/fdsnws/event/1/count"

#: Tope duro del servicio: una consulta no puede pedir más de 20 000 eventos.
FDSN_MAX_LIMIT: Final[int] = 20_000

#: Órdenes válidos del parámetro ``orderby`` de fdsnws-event.
ORDERBY_VALUES: Final[tuple[str, ...]] = (
    "time", "time-asc", "magnitude", "magnitude-asc",
)

DEFAULT_TTL_S: Final[float] = 3600.0  # las consultas históricas no cambian

#: Timeout más LARGO que los feeds en vivo: descargar hasta 20 000 eventos
#: históricos puede tardar bastante; 15 s daba "no se pudo acceder" en falso.
FDSN_TIMEOUT_S: Final[float] = 90.0


class FDSNEventError(Exception):
    """Error genérico al consultar fdsnws-event."""


class FDSNTooManyError(FDSNEventError):
    """La consulta excede el tope de 20 000 eventos del servicio."""


def _iso_utc(value) -> Optional[str]:
    """Normaliza un instante a ``YYYY-MM-DDTHH:MM:SS`` (UTC) para fdsnws.

    Acepta epoch (int/float) o una cadena ya formateada (se pasa tal cual).
    ``None`` → ``None`` (parámetro omitido).
    """

    if value is None:
        return None
    if isinstance(value, str):
        return value
    dt = _dt.datetime.fromtimestamp(float(value), tz=_dt.timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def build_query_params(
    *,
    starttime=None,
    endtime=None,
    min_magnitude: Optional[float] = None,
    max_magnitude: Optional[float] = None,
    min_latitude: Optional[float] = None,
    max_latitude: Optional[float] = None,
    min_longitude: Optional[float] = None,
    max_longitude: Optional[float] = None,
    orderby: str = "time",
    limit: int = 500,
    offset: int = 1,
    eventid: Optional[str] = None,
) -> dict:
    """Construye el dict de parámetros de la consulta (puro, testable).

    ``eventid`` tiene prioridad: si se da, fdsnws devuelve ese único evento y
    el resto de filtros se ignoran (los omitimos para no confundir al server).
    """

    if eventid:
        return {"format": "geojson", "eventid": str(eventid)}

    if orderby not in ORDERBY_VALUES:
        orderby = "time"
    lim = max(1, min(int(limit), FDSN_MAX_LIMIT))

    params: dict[str, object] = {"format": "geojson", "orderby": orderby,
                                 "limit": lim}
    st, et = _iso_utc(starttime), _iso_utc(endtime)
    if st:
        params["starttime"] = st
    if et:
        params["endtime"] = et
    if min_magnitude is not None:
        params["minmagnitude"] = float(min_magnitude)
    if max_magnitude is not None:
        params["maxmagnitude"] = float(max_magnitude)
    if min_latitude is not None:
        params["minlatitude"] = float(min_latitude)
    if max_latitude is not None:
        params["maxlatitude"] = float(max_latitude)
    if min_longitude is not None:
        params["minlongitude"] = float(min_longitude)
    if max_longitude is not None:
        params["maxlongitude"] = float(max_longitude)
    if offset and int(offset) > 1:
        params["offset"] = int(offset)
    return params


def build_query_url(**kwargs) -> str:
    """URL completa de la consulta (puro, testable)."""

    params = build_query_params(**kwargs)
    return f"{FDSN_EVENT_URL}?{urllib.parse.urlencode(params)}"


def build_count_url(**kwargs) -> str:
    """URL del endpoint ``/count`` (sólo nº de eventos, para pre-chequear el
    tope de 20 000 ANTES de descargar). Reusa los filtros de la consulta pero
    quita ``format``/``limit``/``orderby`` (irrelevantes para contar)."""

    params = build_query_params(**kwargs)
    for k in ("format", "limit", "orderby"):
        params.pop(k, None)
    return f"{FDSN_COUNT_URL}?{urllib.parse.urlencode(params)}"


def cache_key_for_url(url: str) -> str:
    """Clave de caché de longitud FIJA (hash) para una URL de consulta.

    Usar la URL entera como nombre de fichero rebasaba el límite de 255 bytes
    del SO ("File name too long"); el hash da una clave corta y estable.
    """

    return "fdsn__" + hashlib.sha256(url.encode("utf-8")).hexdigest()


class FDSNEventClient:
    """Cliente síncrono de ``fdsnws-event``.

    Para uso desde la UI, envolver en un hilo/worker: las consultas históricas
    grandes pueden tardar segundos.
    """

    def __init__(self, cache: Optional[FileCache] = None,
                 ttl_s: float = DEFAULT_TTL_S) -> None:
        self._cache = cache or FileCache()
        self._ttl = float(ttl_s)

    def query(self, *, force_refresh: bool = False, **kwargs) -> list[Earthquake]:
        """Ejecuta la consulta y devuelve ``[Earthquake]`` (recientes primero).

        Lanza ``FDSNTooManyError`` si el servidor rechaza por exceso de
        resultados, y ``FDSNEventError`` para otros fallos de red/parseo.
        """

        url = build_query_url(**kwargs)
        cache_key = cache_key_for_url(url)

        if not force_refresh:
            cached = self._cache.get(cache_key, ttl_s=self._ttl)
            if cached is not None:
                try:
                    return parse_usgs_geojson(cached)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Caché fdsn corrupta: %s", exc)
                    self._cache.invalidate(cache_key)

        try:
            payload = self._http_get(url)
        except urllib.error.HTTPError as exc:
            # 400 con cuerpo que menciona el límite → demasiados eventos.
            if exc.code == 400:
                body = ""
                try:
                    body = exc.read().decode("utf-8", "replace")
                except Exception:  # noqa: BLE001
                    pass
                if "limit" in body.lower() or "20000" in body:
                    raise FDSNTooManyError(
                        t("error.fdsn.too_many")) from exc
                raise FDSNEventError(
                    t("error.fdsn.bad_request")) from exc
            raise FDSNEventError(
                t("error.fdsn.contact", error=str(exc))) from exc
        except (urllib.error.URLError, OSError) as exc:
            raise FDSNEventError(
                t("error.fdsn.contact", error=str(exc))) from exc

        self._cache.set(cache_key, payload)
        return parse_usgs_geojson(payload)

    def count(self, **kwargs) -> int:
        """Nº de eventos que casan SIN descargarlos (endpoint ``/count``).

        El servicio devuelve el número como texto plano; ``204 No Content`` o
        cuerpo vacío → 0. Lanza ``FDSNEventError`` ante fallo de red."""

        url = build_count_url(**kwargs)
        try:
            payload = self._http_get(url)
        except (urllib.error.URLError, OSError) as exc:
            raise FDSNEventError(
                t("error.fdsn.contact", error=str(exc))) from exc
        text = payload.decode("utf-8", "replace").strip()
        try:
            return int(text) if text else 0
        except ValueError:
            return 0

    @staticmethod
    def _http_get(url: str) -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=FDSN_TIMEOUT_S) as resp:
            return resp.read()
