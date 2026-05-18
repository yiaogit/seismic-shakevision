"""
``ThemeManager`` — singleton de selección de tema (v0.4.0+).

Tres modos:
  * ``"dark"``  — tema oscuro permanente
  * ``"light"`` — tema claro permanente
  * ``"auto"`` — el manager elige según la hora local del usuario
    (6:00–18:00 = light, fuera de ese rango = dark)

Cuando el modo es ``auto`` el manager mantiene un QTimer cada 60 s
que comprueba si la franja horaria cambió y emite ``theme_changed``
con el nuevo nombre efectivo (no el modo).

Persistencia
------------
QSettings ``"SeismicGuard"/"Theme"/"theme/mode"`` guarda el modo
elegido por el usuario. ``current_theme()`` siempre devuelve el
efectivo (``"dark"`` o ``"light"``), nunca ``"auto"``.

Uso típico
----------
    from shakevision.ui.theme_manager import ThemeManager
    from shakevision.ui.theme import apply_theme

    # En __main__ tras crear QApplication:
    ThemeManager.init(app)            # detecta modo guardado + aplica
    apply_theme(app, ThemeManager.current_theme())

    # En widgets que quieran reaccionar:
    ThemeManager.changed_signal().connect(self._on_theme_changed)
"""

from __future__ import annotations

import datetime as _dt
import logging
import threading
from typing import Literal, Optional

from PySide6.QtCore import QObject, QTimer, Signal


logger = logging.getLogger(__name__)


ThemeMode = Literal["dark", "light", "auto"]
EffectiveTheme = Literal["dark", "light"]


_QSETTINGS_ORG: str = "SeismicGuard"
_QSETTINGS_APP: str = "Theme"
_QSETTINGS_KEY_MODE: str = "theme/mode"

DEFAULT_MODE: ThemeMode = "auto"

# Rango horario "diurno". Inclusivo al inicio, exclusivo al final.
# Fuera de [DAY_START, DAY_END) usamos dark.
DAY_START_HOUR: int = 6
DAY_END_HOUR:   int = 18

# Frecuencia con que el modo auto re-comprueba la hora (ms).
_AUTO_CHECK_INTERVAL_MS: int = 60_000


# ============================================================
# Singleton interno
# ============================================================
class _Singleton(QObject):
    """Implementación concreta del manager."""

    # Emitido con el tema EFECTIVO (``"dark"`` o ``"light"``), no el modo.
    theme_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.RLock()
        self._mode: ThemeMode = self._load_persisted_mode()
        self._effective: EffectiveTheme = self._compute_effective(self._mode)

        # Timer del modo auto (se inicia solo si _mode == "auto")
        self._timer: Optional[QTimer] = None

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
    def set_mode(self, mode: ThemeMode) -> None:
        """Cambia el modo; emite ``theme_changed`` si el efectivo cambia."""

        if mode not in ("dark", "light", "auto"):
            logger.warning("Modo de tema desconocido %r, ignorado", mode)
            return
        with self._lock:
            if mode == self._mode:
                return
            self._mode = mode
            self._persist_mode(mode)
            new_eff = self._compute_effective(mode)
            changed = new_eff != self._effective
            self._effective = new_eff
            # Gestionar el timer del modo auto
            self._configure_auto_timer()

        if changed:
            self.theme_changed.emit(self._effective)

    # ------------------------------------------------------------------
    # Inicialización del timer auto (público para tests; en producción
    # se llama desde init())
    # ------------------------------------------------------------------
    def _configure_auto_timer(self) -> None:
        if self._mode == "auto":
            if self._timer is None:
                self._timer = QTimer(self)
                self._timer.setInterval(_AUTO_CHECK_INTERVAL_MS)
                self._timer.timeout.connect(self._on_auto_tick)
            if not self._timer.isActive():
                self._timer.start()
        else:
            if self._timer is not None and self._timer.isActive():
                self._timer.stop()

    def _on_auto_tick(self) -> None:
        """Comprueba si la franja horaria cambió y emite si toca."""

        with self._lock:
            if self._mode != "auto":
                return
            new_eff = self._compute_effective("auto")
            if new_eff != self._effective:
                self._effective = new_eff
                changed = True
            else:
                changed = False
        if changed:
            self.theme_changed.emit(self._effective)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _compute_effective(mode: ThemeMode) -> EffectiveTheme:
        if mode == "dark":
            return "dark"
        if mode == "light":
            return "light"
        # auto
        hour = _dt.datetime.now().hour
        return "light" if DAY_START_HOUR <= hour < DAY_END_HOUR else "dark"

    @staticmethod
    def _load_persisted_mode() -> ThemeMode:
        try:
            from PySide6.QtCore import QSettings
            settings = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
            val = settings.value(_QSETTINGS_KEY_MODE, DEFAULT_MODE, type=str)
            if val in ("dark", "light", "auto"):
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
        ``QApplication``. Se encarga de aplicar el tema persistido +
        arrancar el timer del modo auto si corresponde.
        """

        from shakevision.ui.theme import apply_theme

        inst = _get_instance()
        inst._configure_auto_timer()
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
    def set_mode(mode: ThemeMode) -> None:
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
