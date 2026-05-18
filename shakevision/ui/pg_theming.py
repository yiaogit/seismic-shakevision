"""
``pg_theming`` — adapta pyqtgraph PlotWidgets al tema activo (v0.6 P11).

Problema
--------
pyqtgraph guarda colores (background, pen del eje, text pen) en el
``__init__`` del PlotWidget. Cambiar de tema en caliente NO los actualiza
— se quedan en los colores del arranque. Esto hace que en modo claro
los plots del Workbench aparezcan con fondo negro (heredado de la
v0.3 dark-only) — feo y a veces ilegible.

Solución
--------
Una pequeña función ``subscribe_pg_plot(plot)`` que:

  1. Aplica los colores correctos al PlotWidget basándose en el tema
     activo (``ThemeManager.current_theme()``).
  2. Se suscribe a ``ThemeManager.changed_signal`` para re-aplicar
     cada vez que el usuario cambia el tema.

Las curvas (líneas de datos) NO se tocan — su pen lo define el caller
con ``mkPen(WAVEFORM_COLORS[ch])`` y esos colores son semánticos
(Z / N / E), no temáticos.

Uso
---
    from shakevision.ui.pg_theming import subscribe_pg_plot

    plot = pg.PlotWidget()
    subscribe_pg_plot(plot)   # ← una sola llamada, lo demás es automático
"""

from __future__ import annotations

import logging
import weakref
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pyqtgraph as pg


logger = logging.getLogger(__name__)


# Lista WeakReferences a los plots suscritos. Cuando cambia el tema
# iteramos y reaplicamos. WeakReferences porque queremos que los plots
# se puedan recolectar como basura sin que nos importe limpiar — al
# disparar la señal saltamos los que ya no estén vivos.
_subscribed: "list[weakref.ref[pg.PlotWidget]]" = []
_signal_connected: bool = False


def _apply_theme_to_plot(plot) -> None:
    """Aplica los colores del tema actual a un PlotWidget."""

    try:
        from shakevision.ui import theme as _t
        plot.setBackground(_t.COLOR_BACKGROUND)
        # Reaplica los pen de ambos ejes con el color de borde dinámico
        # y el text pen con el de texto secundario.
        for axis_name in ("bottom", "left", "right", "top"):
            try:
                ax = plot.getAxis(axis_name)
            except Exception:  # noqa: BLE001
                continue
            if ax is None:
                continue
            try:
                ax.setPen(_t.COLOR_PANEL_BORDER)
                ax.setTextPen(_t.COLOR_TEXT_SECONDARY)
            except Exception as exc:  # noqa: BLE001
                logger.debug("pg_theming: axis %s skip (%s)", axis_name, exc)
    except Exception as exc:  # noqa: BLE001
        logger.debug("pg_theming: no se pudo retematizar (%s)", exc)


def _on_theme_changed(_theme: str = "") -> None:
    """Slot conectado a ThemeManager.changed_signal."""

    # Reaplicar a todos los plots vivos
    alive = []
    for ref in _subscribed:
        plot = ref()
        if plot is None:
            continue
        _apply_theme_to_plot(plot)
        alive.append(ref)
    _subscribed[:] = alive


def subscribe_pg_plot(plot) -> None:
    """Aplica el tema actual al ``plot`` y lo registra para futuros cambios.

    Idempotente: si el mismo plot se suscribe dos veces, la segunda
    llamada es silenciosa (la WeakReference se compara por identidad).
    """

    global _signal_connected
    # Aplicar tema ahora mismo
    _apply_theme_to_plot(plot)
    # Suscribirse a futuros cambios solo si no está ya suscrito
    existing_ids = {id(r()) for r in _subscribed if r() is not None}
    if id(plot) not in existing_ids:
        _subscribed.append(weakref.ref(plot))
    # Conectar la señal una sola vez por proceso
    if not _signal_connected:
        try:
            from shakevision.ui.theme_manager import ThemeManager
            ThemeManager.changed_signal().connect(_on_theme_changed)
            _signal_connected = True
        except Exception as exc:  # noqa: BLE001
            logger.debug("pg_theming: no se pudo conectar señal (%s)", exc)
