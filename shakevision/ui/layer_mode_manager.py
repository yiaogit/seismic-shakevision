"""
``LayerModeManager`` — singleton del **modo de capa visual** (v0.4.0+).

Concepto
--------
SeismicGuard tiene dos modos de presentación globales que el usuario
puede alternar desde la barra superior:

  * ``"standard"`` — Modo estándar. La paleta de la app y la capa del
    globo siguen al ``ThemeManager``:
        - tema oscuro  → globo en capa nocturna (Earth at night)
        - tema claro   → globo en capa diurna (Earth Blue Marble)
    El usuario controla el tema con el otro botón (☀/🌙/🤖).

  * ``"professional"`` — Modo "Pro". El globo se vuelve **holográfico**
    (capa estilo CRT/sci-fi con fronteras de países y placas) y la
    paleta de la app se **fuerza a oscura** independientemente del
    modo de tema (porque los colores holográficos no se leen bien
    sobre fondos claros). Al volver a "standard" se restaura el modo
    de tema previo.

Persistencia
------------
``QSettings``:
    * ``"layer/mode"`` = ``"standard"`` | ``"professional"``
    * ``"layer/saved_theme_mode"`` = el modo de tema vigente antes de
      pasar a Pro, para restaurarlo al volver.

Señales
-------
* ``mode_changed(str)`` — emitido con ``"standard"`` o ``"professional"``
  tras cualquier cambio. ``GlobePanel`` escucha esta señal para pedir
  al JS ``window.shakevisionGlobe.setLayerMode(...)``.

Uso típico
----------
    from shakevision.ui.layer_mode_manager import LayerModeManager
    LayerModeManager.init()                     # arranca con el modo persistido
    LayerModeManager.set_mode("professional")   # entra en Pro
    print(LayerModeManager.current_mode())      # "professional"
"""

from __future__ import annotations

import logging
import threading
from typing import Literal, Optional

from PySide6.QtCore import QObject, Signal


logger = logging.getLogger(__name__)


LayerMode = Literal["standard", "professional"]


_QSETTINGS_ORG: str = "SeismicGuard"
_QSETTINGS_APP: str = "Layer"
_QSETTINGS_KEY_MODE: str = "layer/mode"
_QSETTINGS_KEY_SAVED_THEME: str = "layer/saved_theme_mode"

DEFAULT_MODE: LayerMode = "standard"


# ============================================================
# Singleton
# ============================================================
class _Singleton(QObject):
    mode_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.RLock()
        self._mode: LayerMode = self._load_persisted_mode()
        # Modo de tema previo (solo se usa al entrar/salir de Pro).
        self._saved_theme_mode: Optional[str] = self._load_saved_theme_mode()

    # ------------------------------------------------------------------
    # Lectura
    # ------------------------------------------------------------------
    def current_mode(self) -> LayerMode:
        return self._mode

    # ------------------------------------------------------------------
    # Mutación
    # ------------------------------------------------------------------
    def set_mode(self, mode: LayerMode) -> None:
        """Cambia el modo de capa del globo. v0.5.3: NO afecta al tema.

        Decisión de diseño (revertida): antes Pro forzaba tema oscuro
        porque los efectos holográficos se asumían incompatibles con
        fondo claro. Pero el usuario quiere libertad total — preferir
        Pro de día sin tener que cambiar la UI a oscura. Por tanto:

          * LayerMode (standard / professional) controla SOLO la
            apariencia del globo 3D (texturas, shading, postEffect).
          * ThemeManager (light / dark / auto) controla SOLO la
            paleta de la app (fondos, textos, bordes).
          * Son completamente ortogonales — 4 combinaciones válidas:
              standard + light, standard + dark,
              professional + light, professional + dark.

        El globo web-view se renderiza siempre sobre fondo negro
        independientemente del tema Qt para asegurar legibilidad.
        """

        if mode not in ("standard", "professional"):
            logger.warning("LayerMode desconocido %r, ignorado", mode)
            return
        with self._lock:
            if mode == self._mode:
                return
            self._mode = mode
            self._persist_mode(mode)
            # NO _apply_theme_side_effect — el tema no se toca.

        self.mode_changed.emit(mode)

    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------
    @staticmethod
    def _load_persisted_mode() -> LayerMode:
        try:
            from PySide6.QtCore import QSettings
            settings = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
            val = settings.value(_QSETTINGS_KEY_MODE, DEFAULT_MODE, type=str)
            if val in ("standard", "professional"):
                return val   # type: ignore[return-value]
        except Exception as exc:  # noqa: BLE001
            logger.debug("LayerModeManager: read QSettings failed (%s)", exc)
        return DEFAULT_MODE

    @staticmethod
    def _persist_mode(mode: LayerMode) -> None:
        try:
            from PySide6.QtCore import QSettings
            settings = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
            settings.setValue(_QSETTINGS_KEY_MODE, mode)
        except Exception as exc:  # noqa: BLE001
            logger.debug("LayerModeManager: persist failed (%s)", exc)

    @staticmethod
    def _load_saved_theme_mode() -> Optional[str]:
        try:
            from PySide6.QtCore import QSettings
            settings = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
            val = settings.value(_QSETTINGS_KEY_SAVED_THEME, "", type=str)
            return val or None
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _persist_saved_theme_mode(value: Optional[str]) -> None:
        try:
            from PySide6.QtCore import QSettings
            settings = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
            settings.setValue(_QSETTINGS_KEY_SAVED_THEME, value or "")
        except Exception:  # noqa: BLE001
            pass


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


class LayerModeManager:
    """Fachada estática."""

    @staticmethod
    def init() -> None:
        """Inicializa el manager (sin side-effect; el modo persistido ya
        está cargado en el constructor)."""

        _get_instance()

    @staticmethod
    def current_mode() -> LayerMode:
        return _get_instance().current_mode()

    @staticmethod
    def set_mode(mode: LayerMode) -> None:
        _get_instance().set_mode(mode)

    @staticmethod
    def changed_signal():
        return _get_instance().mode_changed


def _reset_for_tests() -> None:
    """Solo tests — vacía el singleton."""

    global _instance
    with _instance_lock:
        _instance = None
