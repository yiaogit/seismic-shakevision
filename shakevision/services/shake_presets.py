"""
Almacén persistente de **LAN Raspberry Shake presets** (v0.3.0).

Esta capa es independiente de la UI: ``ControlPanel`` y
``SettingsDialog`` la consumen para mantener una lista compartida de
estaciones Shake propias del usuario en su red local.

Persistencia
------------
Se serializa como JSON dentro de ``QSettings`` (organización
"SeismicGuard", aplicación "Shakes", clave ``"shakes/lan_presets"``).
Es legible/editable a mano sin riesgo de corromper el binario.

Esquema de una entrada
----------------------
```json
{
    "label":   "Mi Shake del salón",
    "host":    "192.168.1.42",   // IP o hostname mDNS (rs.local)
    "port":    18000,
    "network": "AM",
    "station": "R0E05",          // código real del aparato
    "location": ""               // típicamente vacío en Shake
}
```

API pública
-----------
Patrón singleton (igual que LocaleService) para que cualquier punto
de la app pueda llamar a ``ShakePresetStore.all()`` y reciba la
misma lista en vivo.

Emite la señal ``presets_changed`` cada vez que se añade / borra /
modifica una entrada, para que los desplegables y los listados se
refresquen sin polling.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass, replace
from typing import List, Optional

from PySide6.QtCore import QObject, Signal

from shakevision.config import StationPreset


logger = logging.getLogger(__name__)


_QSETTINGS_ORG: str = "SeismicGuard"
_QSETTINGS_APP: str = "Shakes"
_QSETTINGS_KEY: str = "shakes/lan_presets"

DEFAULT_PORT: int = 18000

# Límite blando para evitar listas inmanejables.
MAX_PRESETS: int = 32


# ============================================================
# Modelo
# ============================================================
@dataclass(frozen=True)
class LanShakePreset:
    """Una entrada de la libreta de Shakes LAN del usuario."""

    label: str
    host: str
    station: str
    network: str = "AM"
    location: str = ""
    port: int = DEFAULT_PORT

    # ------------------------------------------------------------------
    # Conversión a StationPreset (el tipo que ControlPanel ya entiende)
    # ------------------------------------------------------------------
    def to_station_preset(self) -> StationPreset:
        return StationPreset(
            label=self.label,
            network=self.network,
            station=self.station,
            location=self.location,
            channel="EHZ",                      # Shake siempre short-period
            seedlink_host=self.host,
            seedlink_port=self.port,
        )

    @staticmethod
    def from_dict(d: dict) -> "LanShakePreset":
        return LanShakePreset(
            label=str(d.get("label", "")).strip() or d.get("host", "Shake"),
            host=str(d.get("host", "")).strip(),
            station=str(d.get("station", "")).strip().upper() or "R0000",
            network=str(d.get("network", "AM")).strip().upper() or "AM",
            location=str(d.get("location", "")).strip(),
            port=int(d.get("port", DEFAULT_PORT)),
        )


# ============================================================
# Singleton
# ============================================================
class _Singleton(QObject):
    """Implementación interna; ``ShakePresetStore`` lo expone."""

    presets_changed = Signal()       # se emite tras cualquier mutación

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.RLock()
        self._presets: List[LanShakePreset] = []
        self._loaded = False

    # ------------------------------------------------------------------
    # Lecturas
    # ------------------------------------------------------------------
    def all(self) -> List[LanShakePreset]:
        """Lista actual (copia defensiva)."""

        with self._lock:
            self._ensure_loaded()
            return list(self._presets)

    def find_by_host(self, host: str) -> Optional[LanShakePreset]:
        host = host.strip().lower()
        with self._lock:
            self._ensure_loaded()
            for p in self._presets:
                if p.host.lower() == host:
                    return p
        return None

    # ------------------------------------------------------------------
    # Mutaciones
    # ------------------------------------------------------------------
    def add(self, preset: LanShakePreset) -> bool:
        """Añade una entrada. Si el host ya existe, REEMPLAZA la entrada
        manteniendo la posición; devuelve ``False`` para señalar "ya
        existía" y ``True`` para "se añadió nueva".
        """

        with self._lock:
            self._ensure_loaded()
            for i, existing in enumerate(self._presets):
                if existing.host.lower() == preset.host.lower():
                    self._presets[i] = preset
                    self._save_locked()
                    self.presets_changed.emit()
                    return False
            if len(self._presets) >= MAX_PRESETS:
                self._presets.pop(0)
            self._presets.append(preset)
            self._save_locked()
        self.presets_changed.emit()
        return True

    def delete(self, host: str) -> bool:
        """Borra por host. ``True`` si encontrada y borrada."""

        host = host.strip().lower()
        with self._lock:
            self._ensure_loaded()
            before = len(self._presets)
            self._presets = [p for p in self._presets if p.host.lower() != host]
            if len(self._presets) == before:
                return False
            self._save_locked()
        self.presets_changed.emit()
        return True

    def rename(self, host: str, new_label: str) -> bool:
        """Cambia solo la etiqueta humana. Conserva el resto."""

        new_label = new_label.strip()
        if not new_label:
            return False
        with self._lock:
            self._ensure_loaded()
            for i, p in enumerate(self._presets):
                if p.host.lower() == host.strip().lower():
                    self._presets[i] = replace(p, label=new_label)
                    self._save_locked()
                    self.presets_changed.emit()
                    return True
        return False

    def clear(self) -> None:
        """Borra todo. Útil para tests / 'reset'."""

        with self._lock:
            self._presets = []
            self._save_locked()
        self.presets_changed.emit()

    # ------------------------------------------------------------------
    # I/O — QSettings con fallback a memoria
    # ------------------------------------------------------------------
    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            from PySide6.QtCore import QSettings
            settings = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
            raw = settings.value(_QSETTINGS_KEY, "", type=str)
            if raw:
                data = json.loads(raw)
                if isinstance(data, list):
                    for entry in data:
                        try:
                            self._presets.append(LanShakePreset.from_dict(entry))
                        except Exception as exc:  # noqa: BLE001
                            logger.warning("Preset Shake inválido, omitido: %s", exc)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ShakePresetStore: no se pudo cargar QSettings (%s)", exc)

    def _save_locked(self) -> None:
        """Persiste en QSettings. Llamar SIEMPRE con el lock tomado."""

        try:
            from PySide6.QtCore import QSettings
            settings = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
            payload = json.dumps([asdict(p) for p in self._presets])
            settings.setValue(_QSETTINGS_KEY, payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ShakePresetStore: no se pudo persistir (%s)", exc)


# ============================================================
# Façade pública
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


class ShakePresetStore:
    """Fachada estática del singleton."""

    @staticmethod
    def all() -> List[LanShakePreset]:
        return _get_instance().all()

    @staticmethod
    def add(preset: LanShakePreset) -> bool:
        return _get_instance().add(preset)

    @staticmethod
    def delete(host: str) -> bool:
        return _get_instance().delete(host)

    @staticmethod
    def rename(host: str, new_label: str) -> bool:
        return _get_instance().rename(host, new_label)

    @staticmethod
    def find_by_host(host: str) -> Optional[LanShakePreset]:
        return _get_instance().find_by_host(host)

    @staticmethod
    def clear() -> None:
        _get_instance().clear()

    @staticmethod
    def changed_signal():
        """Devuelve el Signal para que la UI se suscriba."""

        return _get_instance().presets_changed


# ============================================================
# Reset solo para testing (no expuesto en __all__)
# ============================================================
def _reset_for_tests() -> None:
    """Vacía el singleton — para que cada test arranque limpio."""

    global _instance
    with _instance_lock:
        _instance = None
