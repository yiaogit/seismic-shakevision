"""Suscripción segura de widgets a señales de singletons de larga vida.

v0.7.7 (B1). Generaliza el patrón que ``LoadingOverlay`` introdujo en
v0.7.6.1 para evitar el crash *"Internal C++ object already deleted"*.

El problema
-----------
Cuando un ``QWidget`` conecta uno de sus métodos a una señal de un
**singleton de larga vida** (``LocaleService.language_changed_signal()``,
``ThemeManager.changed_signal()``, ``FavoritesStore``, ``ShakePresetStore``,
``LayerModeManager``, ``ActivityLog`` …), la conexión sobrevive al
``deleteLater()`` del widget. Cuando el singleton emite **después** de que
el objeto C++ ya fue destruido (típico en teardowns de pytest-qt, pero
también al cerrar diálogos en producción), el slot dispara contra un
objeto muerto y revienta con ``RuntimeError``. Conectar *lambdas* lo
empeora: no se pueden desconectar por referencia y mantienen vivo al
widget.

La solución
-----------
``subscribe(owner, signal, slot)``:

* Conecta un *wrapper* que envuelve ``slot`` en ``try/except RuntimeError``
  (defensa si el disconnect llega tarde).
* Desconecta automáticamente cuando ``owner`` emite ``destroyed`` (evita
  además que la lista de conexiones del singleton crezca sin límite al
  crear/destruir diálogos repetidamente — fuga lenta).

Uso
---
.. code-block:: python

    from shakevision.ui.signal_safety import subscribe

    subscribe(self, LocaleService.language_changed_signal(), self._retranslate)
    subscribe(self, ThemeManager.changed_signal(), self._on_theme_changed)

El ``slot`` debe ser un *bound method* (no una lambda) para que el
wrapper conserve una referencia estable y el disconnect funcione.
"""

from __future__ import annotations

import inspect
import logging
from typing import Callable

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)


def _max_positional(slot: Callable) -> int | None:
    """Nº de posicionales que acepta ``slot`` (``None`` = ilimitado/*args).

    Replica el comportamiento de Qt: una señal que emite N argumentos se
    puede conectar a un slot que acepta MENOS — Qt descarta los sobrantes.
    Nuestro wrapper usa esto para no pasar de más y provocar ``TypeError``
    (p. ej. ``language_changed(lang)`` → ``_retranslate()`` sin args).
    """

    try:
        params = inspect.signature(slot).parameters.values()
    except (ValueError, TypeError):
        return None  # builtin / sin firma introspectable → pasar todo
    for p in params:
        if p.kind is p.VAR_POSITIONAL:  # *args acepta cualquier cantidad
            return None
    return sum(
        1 for p in params
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    )


def subscribe(owner: QObject, signal: Signal, slot: Callable) -> None:
    """Conecta ``slot`` a ``signal`` con limpieza segura al destruir ``owner``.

    Args:
        owner: El ``QObject``/widget dueño del slot. Debe exponer la señal
            ``destroyed`` (todos los ``QObject`` lo hacen).
        signal: La señal **bound** del singleton, p. ej.
            ``LocaleService.language_changed_signal()``.
        slot: Método (bound) a invocar. Se envuelve para tragar
            ``RuntimeError`` si el objeto C++ muere antes del disconnect.
    """

    n_pos = _max_positional(slot)

    def _guarded(*args) -> None:
        try:
            slot(*args) if n_pos is None else slot(*args[:n_pos])
        except RuntimeError:
            # El objeto C++ ya fue borrado (teardown de pytest-qt o cierre
            # de diálogo). El disconnect en `destroyed` debería habernos
            # quitado de la lista, pero por si llega tarde: silenciar.
            logger.debug(
                "signal_safety: slot %r disparado tras destrucción del "
                "objeto C++ — ignorado.", getattr(slot, "__name__", slot),
            )

    def _disconnect(*_args) -> None:
        try:
            signal.disconnect(_guarded)
        except (TypeError, RuntimeError):
            # Ya desconectado o señal destruida — fine.
            pass

    try:
        signal.connect(_guarded)
        owner.destroyed.connect(_disconnect)
    except Exception:  # noqa: BLE001 — nunca romper la construcción del widget
        logger.debug("signal_safety: no se pudo suscribir %r", owner)
