"""
``ThemeManager`` — singleton de selección de tema (v0.4.0+).

Dos modos:
  * ``"dark"``  — tema oscuro (default)
  * ``"light"`` — tema claro

Historial: hasta v0.7.6 existía un tercer modo ``"auto"`` que alternaba
light/dark según la hora local (6:00-18:00 = light, resto = dark).
Se eliminó en v0.7.6 porque (a) no respetaba el modo del SO, lo que
generaba inconsistencias visuales (MainWindow oscuro + onboarding
claro cuando el wizard re-disparaba el efectivo durante init); (b)
añadía complejidad con un QTimer global solo para auto-tick. Los
usuarios con ``mode="auto"`` persistido migran automáticamente a
``"dark"`` en el próximo arranque (ver ``_load_persisted_mode``).

Persistencia
------------
QSettings ``"SeismicGuard"/"Theme"/"theme/mode"`` guarda el modo
elegido por el usuario. ``current_theme()`` siempre devuelve el
modo actual (``"dark"`` o ``"light"``).

Uso típico
----------
    from shakevision.ui.theme_manager import ThemeManager
    from shakevision.ui.theme import apply_theme

    # En __main__ tras crear QApplication:
    ThemeManager.init(app)            # carga modo guardado + aplica
    apply_theme(app, ThemeManager.current_theme())

    # En widgets que quieran reaccionar:
    ThemeManager.changed_signal().connect(self._on_theme_changed)
"""

from __future__ import annotations

import logging
import threading
from typing import Literal, Optional

from PySide6.QtCore import QObject, Signal


logger = logging.getLogger(__name__)


# v0.7.6: ``"auto"`` eliminado del Literal. El tipo "compat" sigue
# aceptando "auto" como entrada para retro-compat con QSettings
# previas, pero internamente todo se normaliza a dark/light.
ThemeMode = Literal["dark", "light"]
EffectiveTheme = Literal["dark", "light"]


_QSETTINGS_ORG: str = "SeismicGuard"
_QSETTINGS_APP: str = "Theme"
_QSETTINGS_KEY_MODE: str = "theme/mode"

DEFAULT_MODE: ThemeMode = "dark"


# ============================================================
# Singleton interno
# ============================================================
class _Singleton(QObject):
    """Implementación concreta del manager."""

    # Emitido con el tema EFECTIVO (``"dark"`` o ``"light"``).
    theme_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.RLock()
        self._mode: ThemeMode = self._load_persisted_mode()
        # En el nuevo modelo mode == effective siempre.
        self._effective: EffectiveTheme = self._mode

    # ------------------------------------------------------------------
    # Lectura
    # ------------------------------------------------------------------
    def mode(self) -> ThemeMode:
        return self._mode

    def current_theme(self) -> EffectiveTheme:
        return self._effective

    # ------------------------------------------------------------------
    # Mutaciones
    # ------------------------------------------------------------------
    def set_mode(self, mode: str) -> None:
        """Cambia el modo; emite ``theme_changed`` si cambió.

        Acepta str (no ThemeMode estricto) para que callers viejos
        que aún pasen ``"auto"`` no rompan — lo normalizamos a "dark".
        """

        # v0.7.6: normalización de compat — "auto" → "dark".
        if mode == "auto":
            logger.info("ThemeManager: modo 'auto' eliminado en v0.7.6 — "
                        "normalizando a 'dark'.")
            mode = "dark"
        if mode not in ("dark", "light"):
            logger.warning("Modo de tema desconocido %r, ignorado", mode)
            return
        with self._lock:
            if mode == self._mode:
                return
            self._mode = mode  # type: ignore[assignment]
            self._persist_mode(mode)  # type: ignore[arg-type]
            self._effective = mode  # type: ignore[assignment]

        self.theme_changed.emit(self._effective)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _load_persisted_mode() -> ThemeMode:
        """Lee el modo persistido + migra 'auto' (legacy) a 'dark'."""

        try:
            from PySide6.QtCore import QSettings
            settings = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
            val = settings.value(_QSETTINGS_KEY_MODE, DEFAULT_MODE, type=str)
            # v0.7.6 migration: usuarios con auto guardado → dark.
            if val == "auto":
                logger.info("ThemeManager: migrando QSettings 'auto' → 'dark' "
                            "(modo auto eliminado en v0.7.6).")
                settings.setValue(_QSETTINGS_KEY_MODE, "dark")
                return "dark"
            if val in ("dark", "light"):
                return val   # type: ignore[return-value]
        except Exception as exc:  # noqa: BLE001
            logger.debug("ThemeManager: no se pudo leer QSettings (%s)", exc)
        return DEFAULT_MODE

    @staticmethod
    def _persist_mode(mode: ThemeMode) -> None:
        try:
            from PySide6.QtCore import QSettings
            settings = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
            settings.setValue(_QSETTINGS_KEY_MODE, mode)
        except Exception as exc:  # noqa: BLE001
            logger.debug("ThemeManager: no se pudo persistir (%s)", exc)


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


class ThemeManager:
    """Fachada estática del singleton."""

    @staticmethod
    def init(app) -> None:    # noqa: ANN001 (app es QApplication)
        """Arranca el manager y conecta el tema actual a la QApplication.

        Debe llamarse UNA vez en ``__main__`` justo después de crear
        ``QApplication``. Se encarga de aplicar el tema persistido
        sobre la QApplication.
        """

        from shakevision.ui.theme import apply_theme

        inst = _get_instance()
        apply_theme(app, inst.current_theme())

        # Reaplicar el QSS cada vez que el manager cambie de tema.
        inst.theme_changed.connect(lambda theme: apply_theme(app, theme))

    @staticmethod
    def mode() -> ThemeMode:
        return _get_instance().mode()

    @staticmethod
    def current_theme() -> EffectiveTheme:
        return _get_instance().current_theme()

    @staticmethod
    def set_mode(mode: str) -> None:
        _get_instance().set_mode(mode)

    @staticmethod
    def changed_signal():
        return _get_instance().theme_changed


# ============================================================
# Reset para tests
# ============================================================
def _reset_for_tests() -> None:
    """Vacía el singleton — solo tests."""

    global _instance
    with _instance_lock:
        _instance = None
