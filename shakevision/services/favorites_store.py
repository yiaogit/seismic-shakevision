"""
``FavoritesStore`` — colección persistente de favoritos (v0.5 阶段 J).

Dos categorías independientes:
  * **Estaciones**: pares ``(network, code)`` con metadatos opcionales
    (``site_name``, ``provider``). Pensadas para que el usuario marque
    sus 5-10 estaciones de interés (su barrio, su universidad, una
    estación remota notable) y la Profile page (阶段 L) las pueda
    listar con un click para reproducir.
  * **Eventos sísmicos**: ID de USGS (``us7000xxx``) + magnitud +
    lugar + ts_unix + un timestamp ``added_at_iso``. Permite "marcar
    un sismo histórico para revisarlo después".

Persistencia
------------
Los favoritos se serializan a JSON dentro de QSettings:

    ``"SeismicGuard"/"Favorites"/"favorites/stations"`` = JSON array
    ``"SeismicGuard"/"Favorites"/"favorites/events"``   = JSON array

Usamos JSON porque QSettings nativo es torpe con listas anidadas
cross-platform, mientras que una cadena JSON funciona idéntica en
macOS plist, Windows registry e INI de Linux. Coste: una decodificación
~50 µs en cada lectura.

Límites
-------
Mantenemos un máximo de ``MAX_STATIONS`` y ``MAX_EVENTS`` por lista
para evitar que un click accidental "favoritea-todo" llene el store
hasta congelarlo. Al llegar al límite, descartar el favorito MÁS
ANTIGUO (FIFO).

Señal
-----
``changed_signal()`` emite cada vez que se añade, quita o se vacía la
lista. Las UIs (Profile page, AppHeader badge contador) escuchan
para refrescarse en vivo.

Privacidad
----------
Igual que ``UsageTracker``: zero red, zero telemetría. El store es
100 % local y exportable como JSON (阶段 M).
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import threading
from dataclasses import asdict, dataclass, field, replace
from typing import Optional

from PySide6.QtCore import QObject, Signal


logger = logging.getLogger(__name__)


# ============================================================
# QSettings
# ============================================================
_QSETTINGS_ORG: str = "SeismicGuard"
_QSETTINGS_APP: str = "Favorites"
_KEY_STATIONS:  str = "favorites/stations"
_KEY_EVENTS:    str = "favorites/events"

MAX_STATIONS: int = 100
MAX_EVENTS:   int = 200


def _now_iso_utc() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(
        tzinfo=None, microsecond=0).isoformat() + "Z"


# ============================================================
# Modelos
# ============================================================
@dataclass(frozen=True)
class FavoriteStation:
    """Una estación marcada como favorita.

    ``site_name`` y ``provider`` son opcionales — si el usuario marca
    desde un sitio que solo tiene network+code, se guarda con strings
    vacíos. La Profile page solo necesita network+code para resolver
    la estación real desde la caché viva.
    """

    network: str
    code: str
    site_name: str = ""
    provider: str = ""
    added_at_iso: str = field(default_factory=_now_iso_utc)

    @property
    def key(self) -> tuple[str, str]:
        return (self.network, self.code)


@dataclass(frozen=True)
class FavoriteEvent:
    """Un sismo (USGS event) marcado como favorito.

    v0.7.7: guarda también lat/lon/depth para que el favorito sea
    auto-suficiente y se pueda **revisar** (estación cercana + TauP) aunque
    ya no esté en el feed actual. Los favoritos antiguos traen 0.0.
    """

    id: str
    magnitude: float
    place: str
    timestamp_unix: float
    latitude: float = 0.0
    longitude: float = 0.0
    depth_km: float = 0.0
    # v0.8.0: estación ENLAZADA al evento (la cercana con la que se revisa).
    # Permite reabrir el favorito con ESA estación, de forma determinista.
    network: str = ""
    station: str = ""
    added_at_iso: str = field(default_factory=_now_iso_utc)


# ============================================================
# Helpers QSettings
# ============================================================
def _settings():
    try:
        from PySide6.QtCore import QSettings
        return QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
    except Exception as exc:  # noqa: BLE001
        logger.debug("FavoritesStore: QSettings indispo (%s)", exc)
        return None


def _read_json_list(key: str) -> list[dict]:
    s = _settings()
    if s is None:
        return []
    raw = s.value(key, "", type=str)
    if not raw:
        return []
    try:
        loaded = json.loads(raw)
        if isinstance(loaded, list):
            # Filtrar entradas no-dict (corrupciones / cambios de esquema)
            return [e for e in loaded if isinstance(e, dict)]
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("FavoritesStore: JSON corrupto en %s (%s)", key, exc)
    return []


def _write_json_list(key: str, items: list[dict]) -> None:
    s = _settings()
    if s is None:
        return
    s.setValue(key, json.dumps(items, ensure_ascii=False))


# ============================================================
# Singleton interno
# ============================================================
class _Store(QObject):
    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.RLock()
        # Cargamos a memoria al construir; las mutaciones reescriben el
        # JSON entero. Es lineal pero las listas son cortas (<200).
        self._stations: list[FavoriteStation] = self._load_stations()
        self._events:   list[FavoriteEvent]   = self._load_events()

    # ── I/O ──────────────────────────────────────────────────
    def _load_stations(self) -> list[FavoriteStation]:
        out: list[FavoriteStation] = []
        for entry in _read_json_list(_KEY_STATIONS):
            try:
                out.append(FavoriteStation(
                    network=str(entry.get("network", "")),
                    code=str(entry.get("code", "")),
                    site_name=str(entry.get("site_name", "")),
                    provider=str(entry.get("provider", "")),
                    added_at_iso=str(entry.get("added_at_iso", _now_iso_utc())),
                ))
            except Exception as exc:  # noqa: BLE001
                logger.debug("FavoritesStore: estación malformada (%s)", exc)
        return out

    def _load_events(self) -> list[FavoriteEvent]:
        out: list[FavoriteEvent] = []
        for entry in _read_json_list(_KEY_EVENTS):
            try:
                out.append(FavoriteEvent(
                    id=str(entry["id"]),
                    magnitude=float(entry.get("magnitude", 0.0)),
                    place=str(entry.get("place", "")),
                    timestamp_unix=float(entry.get("timestamp_unix", 0.0)),
                    latitude=float(entry.get("latitude", 0.0)),
                    longitude=float(entry.get("longitude", 0.0)),
                    depth_km=float(entry.get("depth_km", 0.0)),
                    network=str(entry.get("network", "")),
                    station=str(entry.get("station", "")),
                    added_at_iso=str(entry.get("added_at_iso", _now_iso_utc())),
                ))
            except Exception as exc:  # noqa: BLE001
                logger.debug("FavoritesStore: evento malformado (%s)", exc)
        return out

    def _persist_stations(self) -> None:
        _write_json_list(_KEY_STATIONS, [asdict(s) for s in self._stations])

    def _persist_events(self) -> None:
        _write_json_list(_KEY_EVENTS, [asdict(e) for e in self._events])

    # ── Estaciones ───────────────────────────────────────────
    def add_station(self, network: str, code: str, *,
                    site_name: str = "", provider: str = "") -> bool:
        """Añade una estación. Devuelve True si era nueva.

        Si ya existía (mismo network+code, case-sensitive) actualiza
        los metadatos opcionales pero devuelve False — el caller puede
        usar el bool para decidir si refrescar el ícono "★ marcado".

        Si la lista alcanza ``MAX_STATIONS`` descarta la MÁS antigua.
        """

        if not network or not code:
            return False
        with self._lock:
            key = (network, code)
            for i, s in enumerate(self._stations):
                if s.key == key:
                    # Actualizar metadatos sin tocar added_at_iso
                    self._stations[i] = FavoriteStation(
                        network=network, code=code,
                        site_name=site_name or s.site_name,
                        provider=provider or s.provider,
                        added_at_iso=s.added_at_iso,
                    )
                    self._persist_stations()
                    self.changed.emit()
                    return False
            # Nueva: añadir al final + FIFO si lleno
            new = FavoriteStation(
                network=network, code=code,
                site_name=site_name, provider=provider,
            )
            self._stations.append(new)
            if len(self._stations) > MAX_STATIONS:
                self._stations = self._stations[-MAX_STATIONS:]
            self._persist_stations()
        self.changed.emit()
        return True

    def remove_station(self, network: str, code: str) -> bool:
        with self._lock:
            key = (network, code)
            new_list = [s for s in self._stations if s.key != key]
            if len(new_list) == len(self._stations):
                return False
            self._stations = new_list
            self._persist_stations()
        self.changed.emit()
        return True

    def is_favorite_station(self, network: str, code: str) -> bool:
        with self._lock:
            return any(s.key == (network, code) for s in self._stations)

    def list_stations(self) -> list[FavoriteStation]:
        with self._lock:
            return list(self._stations)

    # ── Eventos ──────────────────────────────────────────────
    def add_event(self, id: str, magnitude: float, place: str,
                  timestamp_unix: float, latitude: float = 0.0,
                  longitude: float = 0.0, depth_km: float = 0.0,
                  network: str = "", station: str = "") -> bool:
        if not id:
            return False
        with self._lock:
            for e in self._events:
                if e.id == id:
                    return False    # ya estaba
            new = FavoriteEvent(
                id=id, magnitude=float(magnitude),
                place=place or "", timestamp_unix=float(timestamp_unix),
                latitude=float(latitude), longitude=float(longitude),
                depth_km=float(depth_km),
                network=(network or "").upper(), station=(station or "").upper(),
            )
            self._events.append(new)
            if len(self._events) > MAX_EVENTS:
                self._events = self._events[-MAX_EVENTS:]
            self._persist_events()
        self.changed.emit()
        return True

    def set_event_station(self, id: str, network: str, station: str) -> bool:
        """Actualiza la estación ENLAZADA de un evento favorito (re-bind al
        revisar). Devuelve ``False`` si el evento no existe."""

        net = (network or "").upper()
        sta = (station or "").upper()
        with self._lock:
            found = False
            new_events = []
            for e in self._events:
                if e.id == id:
                    e = replace(e, network=net, station=sta)
                    found = True
                new_events.append(e)
            if not found:
                return False
            self._events = new_events
            self._persist_events()
        self.changed.emit()
        return True

    def remove_event(self, id: str) -> bool:
        with self._lock:
            new_list = [e for e in self._events if e.id != id]
            if len(new_list) == len(self._events):
                return False
            self._events = new_list
            self._persist_events()
        self.changed.emit()
        return True

    def is_favorite_event(self, id: str) -> bool:
        with self._lock:
            return any(e.id == id for e in self._events)

    def list_events(self) -> list[FavoriteEvent]:
        with self._lock:
            return list(self._events)

    # ── Reset / export ───────────────────────────────────────
    def clear_all(self) -> None:
        with self._lock:
            self._stations = []
            self._events = []
            self._persist_stations()
            self._persist_events()
        self.changed.emit()

    def export_to_dict(self) -> dict:
        """Devuelve un dict serializable (para export JSON — 阶段 M)."""

        with self._lock:
            return {
                "stations": [asdict(s) for s in self._stations],
                "events":   [asdict(e) for e in self._events],
            }

    def import_from_dict(self, payload: dict, *, replace: bool = False) -> int:
        """Importa una lista exportada. Devuelve el número total añadido.

        Si ``replace`` es True, vacía las listas antes; si es False
        (por defecto) fusiona, evitando duplicados.
        """

        added = 0
        with self._lock:
            if replace:
                self._stations = []
                self._events = []
            for entry in payload.get("stations") or []:
                if not isinstance(entry, dict):
                    continue
                net, code = entry.get("network", ""), entry.get("code", "")
                if not net or not code:
                    continue
                if any(s.key == (net, code) for s in self._stations):
                    continue
                self._stations.append(FavoriteStation(
                    network=str(net), code=str(code),
                    site_name=str(entry.get("site_name", "")),
                    provider=str(entry.get("provider", "")),
                    added_at_iso=str(entry.get(
                        "added_at_iso", _now_iso_utc())),
                ))
                added += 1
            for entry in payload.get("events") or []:
                if not isinstance(entry, dict):
                    continue
                ev_id = entry.get("id", "")
                if not ev_id:
                    continue
                if any(e.id == ev_id for e in self._events):
                    continue
                try:
                    self._events.append(FavoriteEvent(
                        id=str(ev_id),
                        magnitude=float(entry.get("magnitude", 0.0)),
                        place=str(entry.get("place", "")),
                        timestamp_unix=float(entry.get("timestamp_unix", 0.0)),
                        network=str(entry.get("network", "")),
                        station=str(entry.get("station", "")),
                        added_at_iso=str(entry.get(
                            "added_at_iso", _now_iso_utc())),
                    ))
                    added += 1
                except (TypeError, ValueError):
                    continue
            # Aplicar límites tras import
            if len(self._stations) > MAX_STATIONS:
                self._stations = self._stations[-MAX_STATIONS:]
            if len(self._events) > MAX_EVENTS:
                self._events = self._events[-MAX_EVENTS:]
            self._persist_stations()
            self._persist_events()
        if added > 0:
            self.changed.emit()
        return added


# ============================================================
# Fachada
# ============================================================
_instance: Optional[_Store] = None
_instance_lock = threading.Lock()


def _get_instance() -> _Store:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = _Store()
    return _instance


class FavoritesStore:
    """Fachada estática del singleton ``_Store``."""

    # ── Estaciones ──
    @staticmethod
    def add_station(network: str, code: str, *,
                    site_name: str = "", provider: str = "") -> bool:
        return _get_instance().add_station(
            network, code, site_name=site_name, provider=provider)

    @staticmethod
    def remove_station(network: str, code: str) -> bool:
        return _get_instance().remove_station(network, code)

    @staticmethod
    def is_favorite_station(network: str, code: str) -> bool:
        return _get_instance().is_favorite_station(network, code)

    @staticmethod
    def list_stations() -> list[FavoriteStation]:
        return _get_instance().list_stations()

    # ── Eventos ──
    @staticmethod
    def add_event(id: str, magnitude: float, place: str,
                  timestamp_unix: float, latitude: float = 0.0,
                  longitude: float = 0.0, depth_km: float = 0.0,
                  network: str = "", station: str = "") -> bool:
        return _get_instance().add_event(
            id, magnitude, place, timestamp_unix,
            latitude=latitude, longitude=longitude, depth_km=depth_km,
            network=network, station=station)

    @staticmethod
    def set_event_station(id: str, network: str, station: str) -> bool:
        return _get_instance().set_event_station(id, network, station)

    @staticmethod
    def remove_event(id: str) -> bool:
        return _get_instance().remove_event(id)

    @staticmethod
    def is_favorite_event(id: str) -> bool:
        return _get_instance().is_favorite_event(id)

    @staticmethod
    def list_events() -> list[FavoriteEvent]:
        return _get_instance().list_events()

    # ── Utilidades ──
    @staticmethod
    def clear_all() -> None:
        _get_instance().clear_all()

    @staticmethod
    def export_to_dict() -> dict:
        return _get_instance().export_to_dict()

    @staticmethod
    def import_from_dict(payload: dict, *, replace: bool = False) -> int:
        return _get_instance().import_from_dict(payload, replace=replace)

    @staticmethod
    def changed_signal():
        return _get_instance().changed


def _reset_for_tests() -> None:
    global _instance
    with _instance_lock:
        if _instance is not None:
            _instance.clear_all()
        _instance = None
