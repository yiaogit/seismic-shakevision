"""
Pequeño zoo de animaciones reutilizables.

Cada función devuelve un ``QPropertyAnimation`` (o ``QObject`` con uno
adjunto) ya configurado y **parado**. La caller decide cuándo llamar a
``.start()`` y dónde guardar la referencia para que no se destruya por
el GC. Centralizar las curvas y duraciones en un solo módulo nos da
consistencia visual entre componentes.

Tipos disponibles
-----------------
* ``make_fade_in(widget, duration_ms=200)``
    Anima la opacidad de ``widget`` de 0.0 a 1.0. Útil cuando se
    cambia entre vistas o se introduce contenido nuevo.

* ``make_breathing_glow(target, property_name, low, high,
                        duration_ms=1500)``
    Animación cíclica con curva ``InOutSine`` entre dos valores. Pensada
    para indicadores de alerta: en lugar de parpadear de forma dura
    (encendido/apagado), respira suavemente.

* ``make_pulse_opacity(widget, duration_ms=900, min_opacity=0.25)``
    Pulso de opacidad continuo sobre cualquier widget vía
    ``QGraphicsOpacityEffect``. Útil para el LED "Conectando…".
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QObject,
)
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget


# ============================================================
# Constantes de timing (mantener consistencia entre componentes)
# ============================================================
DURATION_FAST_MS: int = 150       # micro-feedback (hover, focus)
DURATION_DEFAULT_MS: int = 250    # transiciones estándar (fade, slide)
DURATION_SLOW_MS: int = 400       # cambios de vista importantes
DURATION_BREATH_MS: int = 1400    # respiración de alertas


# ============================================================
# Fade in
# ============================================================
def make_fade_in(
    widget: QWidget,
    duration_ms: int = DURATION_DEFAULT_MS,
) -> QPropertyAnimation:
    """Devuelve una animación de opacidad 0 → 1 sobre ``widget``.

    Si el widget ya tenía un ``QGraphicsOpacityEffect`` se reutiliza;
    si no, se crea uno nuevo y se le asigna. La animación NO se
    inicia automáticamente: hace falta ``anim.start()``.
    """

    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)

    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(int(duration_ms))
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    return anim


# ============================================================
# Respiración (cíclica con curva sinusoidal)
# ============================================================
def make_breathing_glow(
    target: QObject,
    property_name: bytes,
    low: Any,
    high: Any,
    duration_ms: int = DURATION_BREATH_MS,
) -> QPropertyAnimation:
    """Devuelve una animación cíclica low → high → low con InOutSine.

    Usar para alertas continuas (eventos sísmicos detectados): la
    transición suave se percibe como "respiración" en lugar de
    parpadeo, mucho más profesional y menos cansado para la vista.

    El llamador es responsable de ``setLoopCount(-1)`` ya configurado
    aquí y de iniciar la animación con ``.start()``.
    """

    anim = QPropertyAnimation(target, property_name, target)
    anim.setDuration(int(duration_ms))
    anim.setStartValue(low)
    anim.setKeyValueAt(0.5, high)
    anim.setEndValue(low)
    anim.setEasingCurve(QEasingCurve.InOutSine)
    anim.setLoopCount(-1)
    return anim


# ============================================================
# Pulso de opacidad (LED activo)
# ============================================================
def make_pulse_opacity(
    widget: QWidget,
    duration_ms: int = 900,
    min_opacity: float = 0.25,
) -> QPropertyAnimation:
    """Anima la opacidad de un widget pulsando entre 1.0 y ``min_opacity``.

    Pensado para el LED de "Conectando…": indica visualmente actividad
    en curso sin recurrir a textos cambiantes.
    """

    if not (0.0 <= min_opacity < 1.0):
        raise ValueError("min_opacity debe estar en [0, 1)")

    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)

    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(int(duration_ms))
    anim.setStartValue(1.0)
    anim.setKeyValueAt(0.5, float(min_opacity))
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.InOutSine)
    anim.setLoopCount(-1)
    return anim


# ============================================================
# Helper: detiene y limpia un efecto si existe
# ============================================================
def clear_opacity_effect(widget: QWidget) -> None:
    """Quita el efecto de opacidad y restaura la opacidad a 1.

    Útil al detener un pulso o un fade-in para que el widget vuelva
    a renderizarse sin la capa adicional (cuesta una fracción de
    pintura por frame).
    """

    effect = widget.graphicsEffect()
    if isinstance(effect, QGraphicsOpacityEffect):
        effect.setOpacity(1.0)
        widget.setGraphicsEffect(None)


# ============================================================
# v0.6: HoverPressBehavior — animación micro de feedback macOS-style
# ============================================================
#
# QSS soporta :hover/:pressed pero los cambios son INMEDIATOS (0 ms).
# macOS y iOS tienen ~150 ms ease para hover y ~80 ms para pressed.
# Esto añade percepción de pulido sin necesidad de re-pintar lógica.
#
# Implementación: usamos QGraphicsOpacityEffect en lugar de QSS para
# que el cambio sea animable. La opacidad oscila entre 1.0 (normal),
# 0.86 (hover) y 0.72 (pressed). NO usamos transform de escala
# porque Qt no anima propiedades nativas de widget (rotación/escala)
# sin meterlos en un QGraphicsView — coste demasiado alto.
#
# Uso:
#     from shakevision.ui.animations import attach_hover_press
#     attach_hover_press(my_button)
#
# Una vez instalado, el widget responde solo. Es seguro llamar a la
# misma función dos veces sobre el mismo widget — el behavior se
# reemplaza, no se acumula.
class _HoverPressBehavior(QObject):
    """Event filter que anima opacity en hover/press."""

    NORMAL  = 1.00
    HOVER   = 0.86
    PRESSED = 0.72

    def __init__(self, widget: QWidget) -> None:
        super().__init__(widget)
        self._widget = widget
        # Asegurar que existe un effect
        effect = widget.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(widget)
            effect.setOpacity(1.0)
            widget.setGraphicsEffect(effect)
        self._effect = effect
        # Animación reutilizable (la reasignamos start/end cada vez)
        self._anim = QPropertyAnimation(effect, b"opacity", widget)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        # Instalar como event filter
        widget.installEventFilter(self)

    def _animate_to(self, target: float, duration_ms: int = 150) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._effect.opacity())
        self._anim.setEndValue(float(target))
        self._anim.setDuration(int(duration_ms))
        self._anim.start()

    def eventFilter(self, obj, event):  # noqa: N802
        # Importar localmente para no inflar el module-load
        from PySide6.QtCore import QEvent
        t = event.type()
        if t == QEvent.Enter:
            self._animate_to(self.HOVER, 150)
        elif t == QEvent.Leave:
            self._animate_to(self.NORMAL, 180)
        elif t == QEvent.MouseButtonPress:
            self._animate_to(self.PRESSED, 80)
        elif t == QEvent.MouseButtonRelease:
            # Si sigue dentro vuelve a HOVER, si no a NORMAL
            target = self.HOVER if self._widget.underMouse() else self.NORMAL
            self._animate_to(target, 120)
        return False   # no consumir — dejamos que el evento siga


# Mapping widget → behavior para evitar duplicados.
_BEHAVIORS: dict[int, _HoverPressBehavior] = {}


def attach_hover_press(widget: QWidget) -> None:
    """Instala micro-animación hover/press (macOS-style) en ``widget``.

    Idempotente: llamadas repetidas reemplazan el behavior anterior
    en lugar de apilarlo. Devuelve None — el behavior se mantiene
    vivo por la jerarquía Qt (parented to widget).
    """

    key = id(widget)
    if key in _BEHAVIORS:
        # Ya tiene behavior; nada que hacer
        return
    _BEHAVIORS[key] = _HoverPressBehavior(widget)
