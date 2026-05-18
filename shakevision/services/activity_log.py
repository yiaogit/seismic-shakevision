"""
ActivityLog — registro cronológico de actividad del usuario
(v0.7-A — reemplaza la sección "Favoritos" en el Profile dialog).

Diferencia con UsageTracker
---------------------------
``UsageTracker`` solo guarda **agregados** ("142 sismos vistos en
total"). ``ActivityLog`` guarda los **N eventos más recientes** con
timestamp, para mostrar una línea de tiempo "qué hice últimamente":

    ┌──────────────────────────────────────────────┐
    │ Hace 5 min — Generaste un reporte           │
    │ Hace 12 min — Conectaste R0E05 (Madrid)     │
    │ Hace 1 h — Viste sismo M5.4 cerca de Tokio  │
    │ Ayer 18:33 — Generaste un PDF                │
    └──────────────────────────────────────────────┘

Política
--------
* **Solo metadatos no-personales.** Guardamos tipo + descripción corta
  (parametrizable con i18n). NUNCA guardamos contenido completo, URLs
  privadas, coordenadas GPS, etc. Cada entrada cabe en ~120 chars.
* **Ring buffer de tamaño fijo (MAX_ENTRIES=50).** La entrada N+1 sobre
  escribe la N-50. Esto pone un techo duro al tamaño en disco — del
  orden de 10 KB en QSettings.
* **Persistencia en QSettings/SeismicGuard/Activity** — separado de
  UsageTracker para que ``clear_cache`` los borre ambos pero por
  separado.
* **Sin clave de tipo libre.** ``ActivityKind`` es un enum cerrado;
  cualquier evento nuevo requiere añadirlo aquí (mejor que strings
  hardcoded esparcidos).

Forma de cada entrada
---------------------
``{"ts": 1715692123, "kind": "report_pdf", "params": {...}}``

* ``ts``     — UNIX seconds (int)
* ``kind``   — string del enum ``ActivityKind``
* ``params`` — dict ``{str: str}`` con los placeholders i18n
              (ej. ``{"place": "Tokyo", "mag": "5.4"}``)

La UI traduce ``kind`` + interpola ``params`` en runtime usando i18n
keys ``activity.<kind>``. Esto permite cambiar idioma sin re-grabar.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import threading
import time
from typing import Optional


logger = logging.getLogger(__name__)


# ============================================================
# Constantes
# ============================================================
_QSETTINGS_ORG: str = "SeismicGuard"
_QSETTINGS_APP: str = "Activity"
_QSETTINGS_KEY: str = "activity/entries"   # JSON array de dicts

MAX_ENTRIES: int = 50


# ============================================================
# Tipos válidos de actividad
# ============================================================
# Añadir nuevos = (1) constante aquí, (2) i18n key activity.<kind>
# en los 4 locales.
KIND_LAUNCH: str           = "launch"
KIND_EARTHQUAKE_VIEWED: str = "quake_viewed"
KIND_STATION_CLICKED: str  = "station_clicked"
KIND_STATION_STREAMED: str = "station_streamed"
KIND_AUDIO_PLAYED: str     = "audio_played"
KIND_REPORT_HTML: str      = "report_html"
KIND_REPORT_PDF: str       = "report_pdf"
KIND_REPLAY: str           = "replay"
KIND_THEME_CHANGED: str    = "theme_changed"
KIND_LANGUAGE_CHANGED: str = "language_changed"
KIND_TIMEZONE_CHANGED: str = "timezone_changed"
KIND_LOCATION_DETECTED: str = "location_detected"
KIND_GITHUB_LOGIN: str     = "github_login"
KIND_GITHUB_LOGOUT: str    = "github_logout"

ALL_KINDS: tuple[str, ...] = (
    KIND_LAUNCH,
    KIND_EARTHQUAKE_VIEWED,
    KIND_STATION_CLICKED,
    KIND_STATION_STREAMED,
    KIND_AUDIO_PLAYED,
    KIND_REPORT_HTML,
    KIND_REPORT_PDF,
    KIND_REPLAY,
    KIND_THEME_CHANGED,
    KIND_LANGUAGE_CHANGED,
    KIND_TIMEZONE_CHANGED,
    KIND_LOCATION_DETECTED,
    KIND_GITHUB_LOGIN,
    KIND_GITHUB_LOGOUT,
)


# ============================================================
# Helpers QSettings
# ============================================================
def _settings():
    try:
        from PySide6.QtCore import QSettings
        return QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
    except Exception as exc:  # noqa: BLE001
        logger.debug("ActivityLog: QSettings no disponible (%s)", exc)
        return None


# ============================================================
# Implementación
# ============================================================
class _Log:
    """Singleton interno; toda la API pública pasa por ``ActivityLog``."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        # Subscribers reciben todas las inserciones — la UI las usa
        # para refrescarse en tiempo real sin polling.
        self._subscribers: list = []

    # ── Mutación ────────────────────────────────────────────
    def record(self, kind: str, **params: str) -> None:
        """Añade una entrada al log. ``params`` debe ser todo strings."""

        if kind not in ALL_KINDS:
            logger.warning("ActivityLog: kind desconocido %r — ignorado", kind)
            return
        # Coerción defensiva — todos los params deben ser strings simples.
        safe_params: dict[str, str] = {}
        for k, v in params.items():
            try:
                safe_params[str(k)] = str(v)
            except Exception:  # noqa: BLE001
                continue
        entry = {
            "ts": int(time.time()),
            "kind": kind,
            "params": safe_params,
        }
        with self._lock:
            entries = self._load_entries()
            entries.append(entry)
            # Recortar a los últimos MAX_ENTRIES (más recientes al final
            # del array; trimmeamos cabeza).
            if len(entries) > MAX_ENTRIES:
                entries = entries[-MAX_ENTRIES:]
            self._save_entries(entries)
        # Notificar subscribers FUERA del lock para evitar deadlocks
        # si un subscriber re-entra en el ActivityLog.
        for cb in list(self._subscribers):
            try:
                cb(entry)
            except Exception as exc:  # noqa: BLE001
                logger.debug("ActivityLog: subscriber lanzó %s", exc)

    # ── Lectura ─────────────────────────────────────────────
    def list_recent(self, limit: int = 10) -> list[dict]:
        """Devuelve las últimas ``limit`` entradas, más reciente primero."""

        with self._lock:
            entries = self._load_entries()
        # Más reciente primero
        entries.reverse()
        return entries[:max(1, int(limit))]

    def reset(self) -> None:
        """Borra todo el log. Usado por clear_cache."""

        with self._lock:
            self._save_entries([])

    # ── Subscripciones (Qt-friendly) ────────────────────────
    def subscribe(self, callback) -> None:
        """``callback(entry: dict)`` se llama tras cada record()."""

        with self._lock:
            if callback not in self._subscribers:
                self._subscribers.append(callback)

    def unsubscribe(self, callback) -> None:
        with self._lock:
            try:
                self._subscribers.remove(callback)
            except ValueError:
                pass

    # ── Persistencia interna ────────────────────────────────
    def _load_entries(self) -> list[dict]:
        s = _settings()
        if s is None:
            return []
        try:
            raw = s.value(_QSETTINGS_KEY, "", type=str)
            if not raw:
                return []
            data = json.loads(raw)
            if not isinstance(data, list):
                return []
            # Filtrar entradas inválidas defensivamente
            valid = []
            for e in data:
                if (isinstance(e, dict)
                        and isinstance(e.get("ts"), int)
                        and isinstance(e.get("kind"), str)
                        and isinstance(e.get("params"), dict)):
                    valid.append(e)
            return valid
        except (json.JSONDecodeError, Exception) as exc:  # noqa: BLE001
            logger.debug("ActivityLog: load falló (%s)", exc)
            return []

    def _save_entries(self, entries: list[dict]) -> None:
        s = _settings()
        if s is None:
            return
        try:
            s.setValue(_QSETTINGS_KEY, json.dumps(entries, ensure_ascii=False))
        except Exception as exc:  # noqa: BLE001
            logger.debug("ActivityLog: save falló (%s)", exc)


# ============================================================
# Singleton + Qt signal helper
# ============================================================
_instance: Optional[_Log] = None
_lock = threading.Lock()


def _get_instance() -> _Log:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = _Log()
    return _instance


class ActivityLog:
    """Fachada estática."""

    @staticmethod
    def record(kind: str, **params: str) -> None:
        _get_instance().record(kind, **params)

    @staticmethod
    def list_recent(limit: int = 10) -> list[dict]:
        return _get_instance().list_recent(limit)

    @staticmethod
    def reset() -> None:
        _get_instance().reset()

    @staticmethod
    def subscribe(callback) -> None:
        _get_instance().subscribe(callback)

    @staticmethod
    def unsubscribe(callback) -> None:
        _get_instance().unsubscribe(callback)

    @staticmethod
    def changed_signal():
        """Qt signal emitida tras cada record() — para que la UI no
        tenga que escribir su propio adaptador subscribe-to-signal.
        """

        return _qt_signal_proxy().changed

    @staticmethod
    def _reset_for_tests() -> None:
        global _instance
        with _lock:
            _instance = None


# ============================================================
# Qt signal proxy (lazy — solo se crea cuando se pide changed_signal)
# ============================================================
_signal_proxy = None
_signal_lock = threading.Lock()


def _qt_signal_proxy():
    global _signal_proxy
    if _signal_proxy is None:
        with _signal_lock:
            if _signal_proxy is None:
                from PySide6.QtCore import QObject, Signal

                class _Proxy(QObject):
                    changed = Signal(dict)  # nueva entrada

                p = _Proxy()
                _get_instance().subscribe(lambda e: p.changed.emit(e))
                _signal_proxy = p
    return _signal_proxy


# ============================================================
# Helper: formateo de tiempo relativo (para la UI)
# ============================================================
def format_relative_time(ts_unix: int, now_unix: Optional[int] = None) -> str:
    """Convierte un timestamp a string relativo legible: "5m", "1h",
    "ayer 14:33", "3 mar", etc.

    Esto es solo el componente numérico/fecha — el sufijo localizable
    ("hace", "ago", "前") lo aplica la UI usando i18n.
    """

    if now_unix is None:
        now_unix = int(time.time())
    delta = max(0, int(now_unix) - int(ts_unix))
    if delta < 60:
        return f"{delta}s"
    if delta < 3600:
        return f"{delta // 60}m"
    if delta < 24 * 3600:
        return f"{delta // 3600}h"
    if delta < 7 * 24 * 3600:
        # < 7 días: "Nd" (ej. "3d")
        return f"{delta // (24 * 3600)}d"
    # Más de una semana: fecha corta
    try:
        dt = _dt.datetime.fromtimestamp(int(ts_unix))
        return dt.strftime("%Y-%m-%d")
    except (OSError, OverflowError, ValueError):
        return "—"
