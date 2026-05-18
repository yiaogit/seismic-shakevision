"""
Cliente FDSN **dataselect** del IRIS DMC.

Mientras que ``services.iris`` consulta el catálogo de estaciones,
este módulo descarga **traces MiniSEED** de un intervalo temporal
concreto a través del servicio ``dataselect/1`` de IRIS:

    https://service.iris.edu/fdsnws/dataselect/1/query

Es la fuente de datos para la función "Replay" (v0.2.0): el usuario
elige una estación + un momento histórico y reproduce las formas de
onda en velocidades arbitrarias.

Diseño
------
* **Síncrono**, vive en un hilo trabajador (ReplaySource lo llama
  desde un QThread → no bloquea la UI).
* **Cacheado en disco** con FileCache (TTL muy largo, por defecto 30
  días: los datos históricos no cambian). El caller puede pedir
  ``force_refresh=True`` para saltarse la caché.
* Devuelve un ``obspy.Stream`` listo para ReplaySource. Si IRIS
  responde 204 / 404, devolvemos un Stream vacío en vez de error
  (el caller decide si mostrar "sin datos para este intervalo").
* Sin Qt — totalmente testeable con mock de ``urllib``.
"""

from __future__ import annotations

import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Final, Optional, Union

from shakevision.services.cache import FileCache

logger = logging.getLogger(__name__)


# ============================================================
# Constantes
# ============================================================
DATASELECT_URL: Final[str] = (
    "https://service.iris.edu/fdsnws/dataselect/1/query"
)

# Datos históricos son inmutables → TTL grande (30 días). Si el
# usuario quiere refrescar puede pasar ``force_refresh=True``.
DEFAULT_TTL_S: Final[float] = 30.0 * 86400.0

# Timeout generoso: descargar varios minutos de MiniSEED a través de
# una conexión lenta puede tardar.
REQUEST_TIMEOUT_S: Final[float] = 60.0

USER_AGENT: Final[str] = (
    "ShakeVision/0.2 (+https://github.com/yiaogit/seismic-shakevision)"
)

# Límite duro de duración solicitable. dataselect deja descargar
# hasta ~ 1 día sin paginar pero esto nos protege de errores de UI.
MAX_DURATION_S: Final[float] = 6 * 3600.0   # 6 horas


# ============================================================
# Excepciones
# ============================================================
class DataselectError(Exception):
    """Error genérico al consultar IRIS dataselect."""


class NoDataAvailable(DataselectError):
    """IRIS respondió 204 / 404 — no hay datos para este intervalo.

    Es un caso de uso esperado (estación inactiva, hueco en el
    archivo); el caller debería mostrar un mensaje friendly en vez
    de tratarlo como error.
    """


class DataselectClient:
    """Cliente síncrono de ``service.iris.edu/fdsnws/dataselect/1``."""

    def __init__(
        self,
        cache: Optional[FileCache] = None,
        ttl_s: float = DEFAULT_TTL_S,
        base_url: str = DATASELECT_URL,
    ) -> None:
        self._cache = cache or FileCache()
        self._ttl = float(ttl_s)
        self._base_url = base_url

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def fetch_miniseed(
        self,
        network: str,
        station: str,
        location: str,
        channel: str,
        starttime: Union[datetime, float],
        endtime: Union[datetime, float],
        force_refresh: bool = False,
    ) -> bytes:
        """Descarga (o lee de caché) un blob MiniSEED para el intervalo.

        Parámetros
        ----------
        network/station/location/channel
            Identificadores SEED estándar. ``channel`` puede ser un
            comodín (``"EH?"`` para los 3 componentes ZNE de banda
            corta, ``"BH?"`` para banda ancha). ``location`` vacío
            se serializa como ``"--"`` por el protocolo FDSN.
        starttime, endtime
            ``datetime`` con tz **UTC** o timestamp Unix (float).
            La duración no debe superar ``MAX_DURATION_S``.
        force_refresh
            Si ``True``, ignora la caché y siempre golpea IRIS.

        Devuelve
        --------
        Bytes con el contenido MiniSEED. ObsPy lo lee con
        ``obspy.read(io.BytesIO(blob))``.

        Levanta
        -------
        NoDataAvailable
            IRIS respondió 204 / 404 (sin datos para el intervalo).
        DataselectError
            Cualquier otro fallo (timeout, 5xx, parámetros inválidos).
        """

        start_dt = _to_utc_datetime(starttime)
        end_dt = _to_utc_datetime(endtime)

        if end_dt <= start_dt:
            raise DataselectError(
                f"endtime ({end_dt}) debe ser posterior a starttime ({start_dt})"
            )
        duration = (end_dt - start_dt).total_seconds()
        if duration > MAX_DURATION_S:
            raise DataselectError(
                f"duración {duration / 3600:.1f} h supera el máximo "
                f"{MAX_DURATION_S / 3600:.1f} h. Solicita un intervalo menor."
            )

        url = self._build_url(network, station, location, channel, start_dt, end_dt)
        cache_key = _cache_key_for(network, station, location, channel,
                                    start_dt, end_dt)

        if not force_refresh:
            cached = self._cache.get(cache_key, ttl_s=self._ttl)
            if cached is not None:
                logger.debug("dataselect cache hit: %s", cache_key)
                return cached

        logger.info("dataselect GET %s", url)
        try:
            blob = self._http_get(url)
        except _NoDataResponse as exc:
            raise NoDataAvailable(
                f"IRIS dataselect: sin datos para "
                f"{network}.{station}.{location}.{channel} "
                f"entre {start_dt.isoformat()} y {end_dt.isoformat()} ({exc})"
            ) from exc
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
            # Si tenemos caché obsoleta, devolverla en lugar de fallar.
            stale = self._cache.get(cache_key, ttl_s=float("inf"))
            if stale is not None:
                logger.warning("IRIS dataselect inalcanzable (%s); usando caché obsoleta.", exc)
                return stale
            raise DataselectError(
                f"no se pudo contactar IRIS dataselect: {exc}"
            ) from exc

        self._cache.set(cache_key, blob)
        logger.info("dataselect descargado: %d KB", len(blob) // 1024)
        return blob

    def fetch_stream(
        self,
        network: str,
        station: str,
        location: str,
        channel: str,
        starttime: Union[datetime, float],
        endtime: Union[datetime, float],
        force_refresh: bool = False,
    ):
        """Igual que ``fetch_miniseed`` pero parsea con ObsPy y devuelve
        ``obspy.Stream``.

        Importa ObsPy de forma perezosa para que los tests del módulo
        que mockean la red no requieran tenerlo instalado.
        """

        import io
        import obspy  # type: ignore

        blob = self.fetch_miniseed(
            network, station, location, channel,
            starttime, endtime, force_refresh=force_refresh,
        )
        stream = obspy.read(io.BytesIO(blob))
        return stream

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------
    def _build_url(
        self,
        network: str,
        station: str,
        location: str,
        channel: str,
        start_dt: datetime,
        end_dt: datetime,
    ) -> str:
        """Construye la URL completa con todos los parámetros FDSN."""

        # FDSN: location vacío = "--"
        loc = location.strip() or "--"
        params = {
            "net": network.strip().upper(),
            "sta": station.strip().upper(),
            "loc": loc,
            "cha": channel.strip().upper(),
            "starttime": _fdsn_format(start_dt),
            "endtime": _fdsn_format(end_dt),
            "format": "miniseed",
            "nodata": "404",
        }
        return f"{self._base_url}?{urllib.parse.urlencode(params)}"

    def _http_get(self, url: str) -> bytes:
        """GET binario; convierte 204/404 en ``_NoDataResponse``."""

        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
                # status 204 también lo manejamos como "sin datos"
                if resp.status in (204, 404):
                    raise _NoDataResponse(f"HTTP {resp.status}")
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code in (204, 404):
                raise _NoDataResponse(f"HTTP {exc.code}") from exc
            raise


# ============================================================
# Excepción interna (señaliza 204/404)
# ============================================================
class _NoDataResponse(Exception):
    """Marcador interno para distinguir 204/404 de otros HTTPError."""


# ============================================================
# Helpers de tiempo
# ============================================================
def _to_utc_datetime(value: Union[datetime, float]) -> datetime:
    """Acepta datetime (aware/naive) o Unix timestamp; normaliza a UTC."""

    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    if value.tzinfo is None:
        # Naive → asumimos UTC (convención del proyecto)
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _fdsn_format(dt: datetime) -> str:
    """FDSN espera ``YYYY-MM-DDTHH:MM:SS`` (sin microsegundos, sin Z)."""

    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _cache_key_for(
    network: str, station: str, location: str, channel: str,
    start_dt: datetime, end_dt: datetime,
) -> str:
    """Clave estable para FileCache. No depende del orden de los parámetros."""

    loc = location.strip() or "--"
    s = _fdsn_format(start_dt).replace(":", "").replace("-", "").replace("T", "")
    e = _fdsn_format(end_dt).replace(":", "").replace("-", "").replace("T", "")
    return f"dsel__{network}_{station}_{loc}_{channel}__{s}_{e}"
