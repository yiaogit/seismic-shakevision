"""
``TimezoneService`` — singleton de zona horaria.

Política
--------
1. Al primer arranque intenta detectar la zona del sistema (sin red).
2. La elección del usuario sobrescribe la detectada y se persiste en
   ``QSettings``.
3. Cambiar la zona emite ``timezone_changed(iana_name)`` para que
   todos los módulos (dashboard, globo, helicorder, reportes…)
   refresquen sus visualizaciones.
4. Si la detección falla parcial o totalmente, ``detect()`` devuelve
   ``None`` y la UI muestra un error; el valor actual se mantiene.

Sin red
-------
NO consultamos APIs externas (ipapi.co, ip-api.com…) por:
  * privacidad — un sismómetro abierto no debería filtrar la IP
  * fiabilidad — el laboratorio / aula puede estar offline
  * legalidad — algunas regiones requieren consentimiento explícito
    para consultar IP-geo
La detección se basa solo en lo que el sistema operativo expone
localmente: ``/etc/localtime`` en POSIX, registro de Windows, o
``datetime.now().astimezone()`` como fallback.
"""

from __future__ import annotations

import datetime as _dt
import logging
import os
import threading
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from PySide6.QtCore import QObject, Signal


logger = logging.getLogger(__name__)


_QSETTINGS_ORG: str = "ShakeVision"
_QSETTINGS_APP: str = "Locale"
_QSETTINGS_KEY: str = "timezone/iana"
_QSETTINGS_KEY_ADDRESS: str = "locale/address"

# Zona por defecto si todo lo demás falla — UTC es siempre válida.
_FALLBACK_TIMEZONE: str = "UTC"


def detect_system_timezone() -> Optional[str]:
    """Intenta extraer el nombre IANA del sistema, **sin red**.

    Estrategias por orden de fiabilidad:
      1. ``/etc/localtime`` es un symlink al fichero IANA correspondiente
         (típico en macOS y la mayoría de Linux). Extraemos el sufijo
         tras ``zoneinfo/``.
      2. Variable de entorno ``TZ`` (POSIX, si está configurada).
      3. ``datetime.now().astimezone().tzinfo`` — devuelve un objeto
         con offset; si su ``str()`` es un nombre IANA válido, lo
         usamos. Si no, probamos a mapearlo via ``ZoneInfo``.

    Devuelve el nombre IANA (``"America/Mexico_City"``, ``"Asia/Shanghai"``…)
    o ``None`` si ninguna estrategia produjo un nombre válido.
    """

    # 1) /etc/localtime symlink (POSIX)
    try:
        if os.path.islink("/etc/localtime"):
            target = os.readlink("/etc/localtime")
            if "zoneinfo/" in target:
                iana = target.split("zoneinfo/", 1)[1]
                if _is_valid_iana(iana):
                    return iana
    except OSError:
        pass

    # 2) TZ environment variable
    tz_env = os.environ.get("TZ")
    if tz_env and _is_valid_iana(tz_env):
        return tz_env

    # 3) datetime.astimezone()
    try:
        local = _dt.datetime.now().astimezone()
        info = local.tzinfo
        if info is not None:
            name = str(info)
            # ``str(ZoneInfo("X/Y"))`` -> "X/Y" en Python ≥ 3.9
            if _is_valid_iana(name):
                return name
    except Exception:  # noqa: BLE001
        pass

    return None


def _is_valid_iana(name: str) -> bool:
    """¿Existe el fichero zoneinfo correspondiente?"""

    try:
        ZoneInfo(name)
        return True
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return False


def available_timezones() -> list[str]:
    """Lista ordenada de zonas horarias IANA disponibles en el sistema.

    En sistemas con ``tzdata`` instalado son ~400. Devuelve algo aunque
    sea pequeño en sistemas mínimos (al menos UTC y la del sistema).
    """

    try:
        from zoneinfo import available_timezones as _avail
        result = sorted(_avail())
        if result:
            return result
    except Exception:  # noqa: BLE001
        pass
    # Fallback mínimo
    base = ["UTC"]
    detected = detect_system_timezone()
    if detected and detected not in base:
        base.append(detected)
    return base


class _Singleton(QObject):
    timezone_changed = Signal(str)  # nuevo nombre IANA

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.RLock()
        # Estado inicial: leer persistido o detectar.
        saved = self._load_persisted_timezone()
        if saved:
            self._current = saved
        else:
            detected = detect_system_timezone()
            self._current = detected if detected else _FALLBACK_TIMEZONE
        # Dirección libre (texto del usuario, opcional)
        self._address: str = self._load_persisted_address()

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def current_iana(self) -> str:
        return self._current

    def current_zone(self) -> ZoneInfo:
        """Devuelve el ``ZoneInfo`` listo para usar con datetime."""

        try:
            return ZoneInfo(self._current)
        except (ZoneInfoNotFoundError, ValueError, OSError):
            return ZoneInfo(_FALLBACK_TIMEZONE)

    def set_timezone(self, iana_name: str) -> bool:
        """Cambia la zona. Devuelve True si el nombre es válido."""

        if not _is_valid_iana(iana_name):
            logger.warning("Timezone inválido: %s — ignorado", iana_name)
            return False
        with self._lock:
            if iana_name == self._current:
                return True
            self._current = iana_name
            self._persist_timezone(iana_name)
        self.timezone_changed.emit(iana_name)
        return True

    def address(self) -> str:
        return self._address

    def set_address(self, text: str) -> None:
        text = (text or "").strip()
        with self._lock:
            self._address = text
            self._persist_address(text)

    def format_local(
        self,
        timestamp_unix: float,
        fmt: str = "%Y-%m-%d %H:%M:%S %Z",
    ) -> str:
        """Formatea un timestamp UNIX en la zona horaria actual."""

        dt = _dt.datetime.fromtimestamp(timestamp_unix, tz=self.current_zone())
        return dt.strftime(fmt)

    def to_iso_local(self, timestamp_unix: float) -> str:
        """Devuelve ISO 8601 con offset en la zona local del usuario."""

        dt = _dt.datetime.fromtimestamp(timestamp_unix, tz=self.current_zone())
        return dt.isoformat()

    # ------------------------------------------------------------------
    # Persistencia
    # ------------------------------------------------------------------
    def _load_persisted_timezone(self) -> Optional[str]:
        try:
            from PySide6.QtCore import QSettings
            settings = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
            value = settings.value(_QSETTINGS_KEY, None, type=str)
            if value and _is_valid_iana(value):
                return value
        except Exception:  # noqa: BLE001
            pass
        return None

    def _persist_timezone(self, iana: str) -> None:
        try:
            from PySide6.QtCore import QSettings
            settings = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
            settings.setValue(_QSETTINGS_KEY, iana)
        except Exception:  # noqa: BLE001
            pass

    def _load_persisted_address(self) -> str:
        try:
            from PySide6.QtCore import QSettings
            settings = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
            return settings.value(_QSETTINGS_KEY_ADDRESS, "", type=str)
        except Exception:  # noqa: BLE001
            return ""

    def _persist_address(self, text: str) -> None:
        try:
            from PySide6.QtCore import QSettings
            settings = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
            settings.setValue(_QSETTINGS_KEY_ADDRESS, text)
        except Exception:  # noqa: BLE001
            pass


# ============================================================
# Singleton público (lazy)
# ============================================================
_instance: Optional[_Singleton] = None
_instance_lock = threading.Lock()


def _get_instance() -> _Singleton:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = _Singleton()
    return _instance


class TimezoneService:
    """Fachada estática."""

    @staticmethod
    def current_iana() -> str:
        return _get_instance().current_iana()

    @staticmethod
    def current_zone() -> ZoneInfo:
        return _get_instance().current_zone()

    @staticmethod
    def set_timezone(iana_name: str) -> bool:
        return _get_instance().set_timezone(iana_name)

    @staticmethod
    def address() -> str:
        return _get_instance().address()

    @staticmethod
    def set_address(text: str) -> None:
        _get_instance().set_address(text)

    @staticmethod
    def format_local(ts: float, fmt: str = "%Y-%m-%d %H:%M:%S %Z") -> str:
        return _get_instance().format_local(ts, fmt)

    @staticmethod
    def to_iso_local(ts: float) -> str:
        return _get_instance().to_iso_local(ts)

    @staticmethod
    def timezone_changed_signal():
        return _get_instance().timezone_changed

    @staticmethod
    def detect_system_timezone() -> Optional[str]:
        return detect_system_timezone()

    @staticmethod
    def available_timezones() -> list[str]:
        return available_timezones()
