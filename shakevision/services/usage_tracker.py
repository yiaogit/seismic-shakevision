"""
``UsageTracker`` — métricas de uso 100 % locales (v0.5 阶段 I).

Propósito
---------
La Profile page (阶段 L) muestra al usuario un resumen amigable de
cómo ha usado SeismicGuard ("Has visto 142 sismos, escuchado 8 min
de sismos, abierto 12 sesiones…"). Para ello necesitamos un store
de contadores y timestamps.

Filosofía
---------
* **Cero red, cero telemetría externa.** Nada de Sentry / Mixpanel /
  Google Analytics. La privacidad de SeismicGuard es una promesa
  contractual con el usuario (ver onboarding.welcome.privacy).
* **Solo agregados.** Guardamos contadores acumulados, no eventos
  individuales — eso reduce el tamaño del store y elimina el riesgo
  de filtrar metadatos sensibles ("este usuario miró un sismo en
  Tehran a las 03:42").
* **Persistencia en QSettings** bajo
  ``"SeismicGuard"/"Usage"`` para que el usuario pueda exportar /
  importar todo desde Ajustes (阶段 M) y para que un wipe
  ``Reset usage`` deje todo a cero sin tocar más estado.

Métricas
--------
=== Identidad de sesión ===
``first_launch_iso``  — ISO 8601 UTC del primer arranque jamás
``last_launch_iso``   — ISO 8601 UTC del arranque más reciente
``launch_count``      — int, número de arranques

=== Tiempo en la app ===
``session_seconds``   — int, segundos acumulados con la app abierta.
                        Se actualiza al cerrar la sesión.

=== Interacción con datos ===
``earthquakes_viewed_count`` — int, clicks en sismos del globo
``stations_clicked_count``   — int, clicks en estaciones del globo
``stations_streamed_count``  — int, conexiones SeedLink iniciadas

=== Funcionalidades avanzadas ===
``audio_played_seconds``     — int, total de segundos sonificados
``reports_generated_count``  — int, reportes HTML/PDF exportados
``replay_sessions_count``    — int, reproducciones históricas IRIS

API
---
Singleton accesible vía la fachada ``UsageTracker``:

    UsageTracker.record_launch()
    UsageTracker.record_earthquake_viewed()
    UsageTracker.record_station_clicked()
    UsageTracker.record_audio_played(seconds=12)
    UsageTracker.start_session()
    UsageTracker.end_session()      # invocar antes de cerrar la app
    stats = UsageTracker.stats()    # dict con todos los contadores
    UsageTracker.reset()            # borra todo (para tests y Ajustes)

Todos los ``record_*`` son re-entrantes y thread-safe.
"""

from __future__ import annotations

import datetime as _dt
import logging
import threading
import time
from typing import Optional


logger = logging.getLogger(__name__)


# ============================================================
# Claves de QSettings
# ============================================================
_QSETTINGS_ORG: str = "SeismicGuard"
_QSETTINGS_APP: str = "Usage"

# Identidad
KEY_FIRST_LAUNCH_ISO:   str = "usage/first_launch_iso"
KEY_LAST_LAUNCH_ISO:    str = "usage/last_launch_iso"
KEY_LAUNCH_COUNT:       str = "usage/launch_count"

# Tiempo
KEY_SESSION_SECONDS:    str = "usage/session_seconds"

# Datos
KEY_EARTHQUAKES_VIEWED: str = "usage/earthquakes_viewed_count"
KEY_STATIONS_CLICKED:   str = "usage/stations_clicked_count"
KEY_STATIONS_STREAMED:  str = "usage/stations_streamed_count"

# Funcionalidades
KEY_AUDIO_SECONDS:      str = "usage/audio_played_seconds"
KEY_REPORTS_COUNT:      str = "usage/reports_generated_count"
KEY_REPLAY_COUNT:       str = "usage/replay_sessions_count"


# Lista canónica para iterar (tests, reset, export):
ALL_KEYS: tuple[str, ...] = (
    KEY_FIRST_LAUNCH_ISO,
    KEY_LAST_LAUNCH_ISO,
    KEY_LAUNCH_COUNT,
    KEY_SESSION_SECONDS,
    KEY_EARTHQUAKES_VIEWED,
    KEY_STATIONS_CLICKED,
    KEY_STATIONS_STREAMED,
    KEY_AUDIO_SECONDS,
    KEY_REPORTS_COUNT,
    KEY_REPLAY_COUNT,
)


# ============================================================
# Helpers QSettings (encapsulados para tests sin Qt en algunos paths)
# ============================================================
def _settings():
    """Devuelve un QSettings o None si Qt no está disponible.

    Los tests que NO requieren Qt aún pueden usar la API si parcheamos
    esta función. El uso normal siempre devuelve un QSettings vivo.
    """

    try:
        from PySide6.QtCore import QSettings
        return QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
    except Exception as exc:  # noqa: BLE001
        logger.debug("UsageTracker: QSettings no disponible (%s)", exc)
        return None


def _get_int(key: str, default: int = 0) -> int:
    s = _settings()
    if s is None:
        return default
    try:
        return int(s.value(key, default, type=int))
    except (TypeError, ValueError):
        return default


def _set_int(key: str, value: int) -> None:
    s = _settings()
    if s is None:
        return
    s.setValue(key, int(value))


def _get_str(key: str, default: str = "") -> str:
    s = _settings()
    if s is None:
        return default
    val = s.value(key, default, type=str)
    return val if isinstance(val, str) else default


def _set_str(key: str, value: str) -> None:
    s = _settings()
    if s is None:
        return
    s.setValue(key, value)


def _now_iso_utc() -> str:
    """ISO 8601 UTC con sufijo Z, sin microsegundos (más legible)."""

    return _dt.datetime.now(_dt.timezone.utc).replace(
        tzinfo=None, microsecond=0).isoformat() + "Z"


# ============================================================
# Implementación
# ============================================================
class _Tracker:
    """Singleton interno. Toda la API pública pasa por ``UsageTracker``."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        # Marca el monotonic de inicio de la sesión actual. Usamos
        # time.monotonic() en vez de time.time() para resistir cambios
        # del reloj del sistema (DST, NTP, suspensión…).
        self._session_started_at: Optional[float] = None

    # ── Arranque ─────────────────────────────────────────────
    def record_launch(self) -> None:
        """Marca un arranque: incrementa contador + actualiza timestamps."""

        with self._lock:
            now_iso = _now_iso_utc()
            # Primer arranque solo se escribe si no existe ya.
            if not _get_str(KEY_FIRST_LAUNCH_ISO):
                _set_str(KEY_FIRST_LAUNCH_ISO, now_iso)
            _set_str(KEY_LAST_LAUNCH_ISO, now_iso)
            _set_int(KEY_LAUNCH_COUNT, _get_int(KEY_LAUNCH_COUNT) + 1)
        # v0.7-A: mirror al ActivityLog para que aparezca en la
        # línea de tiempo del Profile dialog.
        try:
            from shakevision.services.activity_log import (
                ActivityLog, KIND_LAUNCH,
            )
            ActivityLog.record(KIND_LAUNCH)
        except Exception:  # noqa: BLE001
            pass

    # ── Sesión (tiempo total con la app abierta) ─────────────
    def start_session(self) -> None:
        with self._lock:
            self._session_started_at = time.monotonic()

    def end_session(self) -> None:
        """Acumula la duración de la sesión actual en QSettings.

        Idempotente: si no hay sesión activa no hace nada. Si se llama
        dos veces seguidas, solo la primera contabiliza (se resetea el
        marker tras acumular).
        """

        with self._lock:
            if self._session_started_at is None:
                return
            elapsed = max(0, int(time.monotonic() - self._session_started_at))
            self._session_started_at = None
            if elapsed > 0:
                _set_int(KEY_SESSION_SECONDS,
                         _get_int(KEY_SESSION_SECONDS) + elapsed)

    # ── Eventos de interacción ───────────────────────────────
    def record_earthquake_viewed(self, place: str = "", mag: float = 0.0) -> None:
        with self._lock:
            _set_int(KEY_EARTHQUAKES_VIEWED,
                     _get_int(KEY_EARTHQUAKES_VIEWED) + 1)
        try:
            from shakevision.services.activity_log import (
                ActivityLog, KIND_EARTHQUAKE_VIEWED,
            )
            ActivityLog.record(
                KIND_EARTHQUAKE_VIEWED,
                place=str(place) or "?",
                mag=f"{float(mag):.1f}" if mag else "?",
            )
        except Exception:  # noqa: BLE001
            pass

    def record_station_clicked(self, network: str = "", code: str = "") -> None:
        with self._lock:
            _set_int(KEY_STATIONS_CLICKED,
                     _get_int(KEY_STATIONS_CLICKED) + 1)
        try:
            from shakevision.services.activity_log import (
                ActivityLog, KIND_STATION_CLICKED,
            )
            label = f"{network}.{code}" if (network and code) else (code or network or "?")
            ActivityLog.record(KIND_STATION_CLICKED, station=label)
        except Exception:  # noqa: BLE001
            pass

    def record_station_streamed(self, label: str = "") -> None:
        """Llamar cuando una conexión SeedLink arranca con éxito."""

        with self._lock:
            _set_int(KEY_STATIONS_STREAMED,
                     _get_int(KEY_STATIONS_STREAMED) + 1)
        try:
            from shakevision.services.activity_log import (
                ActivityLog, KIND_STATION_STREAMED,
            )
            ActivityLog.record(KIND_STATION_STREAMED, station=str(label) or "?")
        except Exception:  # noqa: BLE001
            pass

    # ── Funcionalidades ─────────────────────────────────────
    def record_audio_played(self, seconds: float) -> None:
        if seconds <= 0:
            return
        with self._lock:
            _set_int(KEY_AUDIO_SECONDS,
                     _get_int(KEY_AUDIO_SECONDS) + int(seconds))
        try:
            from shakevision.services.activity_log import (
                ActivityLog, KIND_AUDIO_PLAYED,
            )
            ActivityLog.record(KIND_AUDIO_PLAYED, seconds=str(int(seconds)))
        except Exception:  # noqa: BLE001
            pass

    def record_report_generated(self, fmt: str = "html") -> None:
        """``fmt`` es ``"html"`` o ``"pdf"`` — la actividad lo refleja."""

        with self._lock:
            _set_int(KEY_REPORTS_COUNT,
                     _get_int(KEY_REPORTS_COUNT) + 1)
        try:
            from shakevision.services.activity_log import (
                ActivityLog, KIND_REPORT_HTML, KIND_REPORT_PDF,
            )
            kind = KIND_REPORT_PDF if str(fmt).lower() == "pdf" else KIND_REPORT_HTML
            ActivityLog.record(kind)
        except Exception:  # noqa: BLE001
            pass

    def record_replay_session(self) -> None:
        with self._lock:
            _set_int(KEY_REPLAY_COUNT,
                     _get_int(KEY_REPLAY_COUNT) + 1)
        try:
            from shakevision.services.activity_log import (
                ActivityLog, KIND_REPLAY,
            )
            ActivityLog.record(KIND_REPLAY)
        except Exception:  # noqa: BLE001
            pass

    # ── Lectura ─────────────────────────────────────────────
    def stats(self) -> dict:
        """Devuelve un dict con todos los contadores actuales.

        Incluye también la duración de la sesión **en curso** sumada
        a session_seconds, para que la Profile page vea un total
        coherente sin tener que esperar a end_session.
        """

        with self._lock:
            session_extra = 0
            if self._session_started_at is not None:
                session_extra = max(
                    0, int(time.monotonic() - self._session_started_at)
                )
            return {
                "first_launch_iso":          _get_str(KEY_FIRST_LAUNCH_ISO),
                "last_launch_iso":           _get_str(KEY_LAST_LAUNCH_ISO),
                "launch_count":              _get_int(KEY_LAUNCH_COUNT),
                "session_seconds":           _get_int(KEY_SESSION_SECONDS)
                                              + session_extra,
                "earthquakes_viewed_count":  _get_int(KEY_EARTHQUAKES_VIEWED),
                "stations_clicked_count":    _get_int(KEY_STATIONS_CLICKED),
                "stations_streamed_count":   _get_int(KEY_STATIONS_STREAMED),
                "audio_played_seconds":      _get_int(KEY_AUDIO_SECONDS),
                "reports_generated_count":   _get_int(KEY_REPORTS_COUNT),
                "replay_sessions_count":     _get_int(KEY_REPLAY_COUNT),
            }

    def reset(self) -> None:
        """Borra TODAS las claves de uso. Irreversible — usar con cuidado."""

        with self._lock:
            self._session_started_at = None
            s = _settings()
            if s is None:
                return
            for k in ALL_KEYS:
                s.remove(k)


# ============================================================
# Singleton + Fachada
# ============================================================
_instance: Optional[_Tracker] = None
_instance_lock = threading.Lock()


def _get_instance() -> _Tracker:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = _Tracker()
    return _instance


class UsageTracker:
    """Fachada estática del singleton ``_Tracker``."""

    @staticmethod
    def record_launch() -> None:
        _get_instance().record_launch()

    @staticmethod
    def start_session() -> None:
        _get_instance().start_session()

    @staticmethod
    def end_session() -> None:
        _get_instance().end_session()

    @staticmethod
    def record_earthquake_viewed() -> None:
        _get_instance().record_earthquake_viewed()

    @staticmethod
    def record_station_clicked() -> None:
        _get_instance().record_station_clicked()

    @staticmethod
    def record_station_streamed() -> None:
        _get_instance().record_station_streamed()

    @staticmethod
    def record_audio_played(seconds: float) -> None:
        _get_instance().record_audio_played(seconds)

    @staticmethod
    def record_report_generated() -> None:
        _get_instance().record_report_generated()

    @staticmethod
    def record_replay_session() -> None:
        _get_instance().record_replay_session()

    @staticmethod
    def stats() -> dict:
        return _get_instance().stats()

    @staticmethod
    def reset() -> None:
        _get_instance().reset()


def _reset_for_tests() -> None:
    """Vacía el singleton + el store. Solo tests."""

    global _instance
    with _instance_lock:
        if _instance is not None:
            _instance.reset()
        _instance = None
