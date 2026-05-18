"""
LocationService — detección de ubicación del dispositivo (v0.7-D).

Estrategia
----------
Desktop apps no tienen acceso GPS directo como las apps móviles. Para
"usar dirección local del dispositivo" usamos geolocalización por IP
con un servicio público gratuito (sin API key, sin tracking):

  * ip-api.com  — 45 req/min sin key, devuelve city/country/region.
    HTTP only (HTTPS requiere subscription pero free tier basta).

La llamada es **explícita** (botón "Detectar"), nunca automática en
segundo plano — el usuario decide cuándo se filtra su IP, alineado
con el principio de consentimiento informado.

Si la petición falla (offline, rate limit, DNS), devolvemos un error
descriptivo y la UI cae al input manual.

Forma del resultado
-------------------
``DetectedLocation(city, region, country, lat, lng, formatted)``

``formatted`` es el string listo para mostrar:
  * "Madrid, Spain"
  * "São Paulo, SP, Brazil"

Privacidad
----------
La llamada va a ip-api.com (HTTP). Tu IP sale del proceso una vez,
no se persiste en ip-api más allá de logs estándar de servidor.
Si esto preocupa, usar el campo manual y dejar el botón sin pulsar.
"""

from __future__ import annotations

import json
import logging
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass


logger = logging.getLogger(__name__)


# 5 segundos es suficiente para ip-api.com en condiciones normales.
# Más corto que el default 60s para no bloquear la UI si hay timeout.
_HTTP_TIMEOUT_SECONDS: float = 5.0
_API_URL: str = "http://ip-api.com/json/?fields=status,message,country,regionName,city,lat,lon,timezone,query"


@dataclass(frozen=True)
class DetectedLocation:
    """Resultado de una detección exitosa."""

    city: str
    region: str
    country: str
    lat: float
    lng: float
    timezone: str           # IANA detectada por ip-api — útil para
                            # validar contra detect_system_timezone()
    formatted: str          # "Madrid, Spain" listo para mostrar

    @property
    def has_coords(self) -> bool:
        return not (self.lat == 0.0 and self.lng == 0.0)


class LocationError(Exception):
    """Cualquier fallo durante la detección por IP."""


def detect_from_ip() -> DetectedLocation:
    """Llama a ip-api.com y devuelve la ubicación detectada.

    Bloquea hasta ``_HTTP_TIMEOUT_SECONDS``. El caller debe llamar a
    esto desde un QThread o usar QNetworkAccessManager si no quiere
    bloquear el hilo UI. La SettingsDialog usa QThread (ligero) por
    simplicidad.

    Levanta ``LocationError`` con mensaje legible en cualquier fallo
    (timeout, DNS, rate limit, JSON malformado, status="fail" del API).
    """

    try:
        req = urllib.request.Request(
            _API_URL,
            headers={
                "User-Agent": "SeismicGuard/0.7 (local desktop app)",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_SECONDS) as resp:
            raw = resp.read()
    except socket.timeout as exc:
        raise LocationError(f"timeout tras {_HTTP_TIMEOUT_SECONDS}s") from exc
    except urllib.error.URLError as exc:
        raise LocationError(f"red no disponible: {exc.reason!s}") from exc
    except Exception as exc:  # noqa: BLE001
        raise LocationError(f"error inesperado: {exc!s}") from exc

    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise LocationError(f"respuesta malformada: {exc!s}") from exc

    if data.get("status") != "success":
        msg = data.get("message", "respuesta sin éxito")
        raise LocationError(f"API: {msg}")

    city = (data.get("city") or "").strip()
    region = (data.get("regionName") or "").strip()
    country = (data.get("country") or "").strip()
    lat = float(data.get("lat") or 0.0)
    lng = float(data.get("lon") or 0.0)
    timezone = (data.get("timezone") or "").strip()

    formatted = _format_address(city, region, country)

    logger.info("LocationService: detectado %s (%.3f, %.3f) tz=%s",
                formatted, lat, lng, timezone)
    return DetectedLocation(
        city=city, region=region, country=country,
        lat=lat, lng=lng, timezone=timezone,
        formatted=formatted,
    )


def _format_address(city: str, region: str, country: str) -> str:
    """Devuelve 'City, Region, Country' o variantes según qué exista."""

    parts: list[str] = []
    if city:
        parts.append(city)
    if region and region != city:
        parts.append(region)
    if country:
        parts.append(country)
    return ", ".join(parts) if parts else "—"


# ============================================================
# Helper Qt: detección asíncrona en QThread
# ============================================================
def detect_async(callback) -> None:
    """Lanza detect_from_ip() en un QThread y llama ``callback`` al
    terminar con ``(detected: Optional[DetectedLocation], error: Optional[str])``.

    Wrapper conveniente para la UI que no quiere armar QThread+worker
    a mano. Solo importable cuando hay Qt — si se llama sin QApplication
    el QThread no arranca limpio.
    """

    from PySide6.QtCore import QObject, QThread, Signal

    class _Worker(QObject):
        done = Signal(object, object)  # (DetectedLocation|None, str|None)

        def run(self) -> None:
            try:
                loc = detect_from_ip()
                self.done.emit(loc, None)
            except LocationError as exc:
                self.done.emit(None, str(exc))
            except Exception as exc:  # noqa: BLE001
                self.done.emit(None, f"error inesperado: {exc!s}")

    thread = QThread()
    worker = _Worker()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.done.connect(callback)
    worker.done.connect(thread.quit)
    worker.done.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    # Mantener referencia para que GC no se lleve el thread mientras corre
    detect_async._refs = getattr(detect_async, "_refs", [])  # type: ignore[attr-defined]
    detect_async._refs.append((thread, worker))  # type: ignore[attr-defined]
