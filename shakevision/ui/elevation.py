"""
``elevation`` — sombras Material/macOS reutilizables (v0.6).

Por qué un módulo separado
--------------------------
Las sombras en Qt no son CSS-property. Hay que usar
``QGraphicsDropShadowEffect`` que es un ``QObject`` aparte. Para no
ensuciar cada widget con 6-8 líneas repetidas (color, blurRadius,
offsetX, offsetY, parentar al widget), centralizamos aquí los
"presets" de elevación.

Presets (Material Design 3 inspired)
------------------------------------
* ``elevation_0`` — sin sombra (flat). Se usa para anular una elevación
  previa, no hace falta llamarlo si nunca aplicaste.
* ``elevation_1`` — sombras muy sutiles, ~4 px blur. Tarjetas
  estáticas dentro del flujo (StatCard, FavoriteRow).
* ``elevation_2`` — sombras medias, ~12 px blur. Diálogos, popovers,
  ProfileDialog.
* ``elevation_3`` — sombras pronunciadas, ~24 px blur. Modales sobre
  fondo blureado (no implementado aún).

Color de la sombra
------------------
Negro semi-transparente. Funciona en ambos temas: en oscuro casi no
se nota la sombra (lo cual es correcto — los temas oscuros usan luces
en lugar de sombras para indicar elevación), en claro produce el
"float" típico de macOS.

Uso
---
    from shakevision.ui.elevation import elevation_1
    elevation_1(my_card)

Idempotente: dos llamadas sobreescriben el effect, no se acumulan.
"""

from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QWidget


def _apply_shadow(widget: QWidget, *, blur: int, dy: int, alpha: int) -> None:
    """Núcleo: monta un QGraphicsDropShadowEffect en ``widget``."""

    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, dy)
    effect.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(effect)


def elevation_0(widget: QWidget) -> None:
    """Sin sombra — limpia cualquier sombra previa."""

    widget.setGraphicsEffect(None)


def elevation_1(widget: QWidget) -> None:
    """Sombra muy sutil (4 px blur, 1 px Y, alpha ~25)."""

    _apply_shadow(widget, blur=4, dy=1, alpha=25)


def elevation_2(widget: QWidget) -> None:
    """Sombra media (12 px blur, 4 px Y, alpha ~40). Tarjetas / diálogos."""

    _apply_shadow(widget, blur=12, dy=4, alpha=40)


def elevation_3(widget: QWidget) -> None:
    """Sombra pronunciada (24 px blur, 8 px Y, alpha ~55). Modales."""

    _apply_shadow(widget, blur=24, dy=8, alpha=55)
