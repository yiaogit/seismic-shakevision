"""
Pruebas del módulo de animaciones reutilizables.

Verificamos que las tres factorías devuelven ``QPropertyAnimation``
correctamente configuradas (duración, valores, curva, loop count) y
que ``clear_opacity_effect`` deja el widget sin efecto.

Requiere PySide6 — se omite en entornos sin la dependencia.
"""

from __future__ import annotations

import os

import pytest


pytest.importorskip("PySide6.QtWidgets", reason="PySide6 no instalado")

# Backend offscreen para CI sin pantalla
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEasingCurve  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QGraphicsOpacityEffect,
    QWidget,
)

from shakevision.ui.animations import (  # noqa: E402
    DURATION_BREATH_MS,
    DURATION_DEFAULT_MS,
    clear_opacity_effect,
    make_breathing_glow,
    make_fade_in,
    make_pulse_opacity,
)


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


# ============================================================
# make_fade_in
# ============================================================
def test_fade_in_creates_opacity_effect(qt_app) -> None:
    w = QWidget()
    anim = make_fade_in(w, duration_ms=300)
    assert anim.duration() == 300
    assert anim.startValue() == 0.0
    assert anim.endValue() == 1.0
    assert anim.easingCurve().type() == QEasingCurve.OutCubic
    assert isinstance(w.graphicsEffect(), QGraphicsOpacityEffect)


def test_fade_in_default_duration(qt_app) -> None:
    w = QWidget()
    anim = make_fade_in(w)
    assert anim.duration() == DURATION_DEFAULT_MS


def test_fade_in_reuses_existing_effect(qt_app) -> None:
    """Una segunda llamada no debe crear un efecto nuevo."""

    w = QWidget()
    make_fade_in(w)
    first_effect = w.graphicsEffect()
    make_fade_in(w)
    assert w.graphicsEffect() is first_effect


# ============================================================
# make_breathing_glow
# ============================================================
def test_breathing_glow_loops_forever(qt_app) -> None:
    w = QWidget()
    effect = QGraphicsOpacityEffect(w)
    w.setGraphicsEffect(effect)
    anim = make_breathing_glow(effect, b"opacity", low=0.2, high=1.0,
                                duration_ms=800)
    assert anim.duration() == 800
    assert anim.startValue() == 0.2
    assert anim.endValue() == 0.2  # vuelve al inicio
    assert anim.keyValueAt(0.5) == 1.0
    assert anim.loopCount() == -1
    assert anim.easingCurve().type() == QEasingCurve.InOutSine


def test_breathing_glow_default_duration(qt_app) -> None:
    w = QWidget()
    effect = QGraphicsOpacityEffect(w)
    w.setGraphicsEffect(effect)
    anim = make_breathing_glow(effect, b"opacity", 0.0, 1.0)
    assert anim.duration() == DURATION_BREATH_MS


# ============================================================
# make_pulse_opacity
# ============================================================
def test_pulse_opacity_validates_min(qt_app) -> None:
    w = QWidget()
    with pytest.raises(ValueError):
        make_pulse_opacity(w, min_opacity=1.0)
    with pytest.raises(ValueError):
        make_pulse_opacity(w, min_opacity=-0.1)


def test_pulse_opacity_loops_and_attaches_effect(qt_app) -> None:
    w = QWidget()
    anim = make_pulse_opacity(w, duration_ms=600, min_opacity=0.3)
    assert anim.duration() == 600
    assert anim.loopCount() == -1
    assert anim.keyValueAt(0.5) == 0.3
    assert isinstance(w.graphicsEffect(), QGraphicsOpacityEffect)


# ============================================================
# clear_opacity_effect
# ============================================================
def test_clear_opacity_effect_removes_effect(qt_app) -> None:
    w = QWidget()
    make_fade_in(w)
    assert w.graphicsEffect() is not None
    clear_opacity_effect(w)
    assert w.graphicsEffect() is None


def test_clear_opacity_effect_noop_when_no_effect(qt_app) -> None:
    """Si el widget no tenía efecto, la llamada no debe explotar."""

    w = QWidget()
    clear_opacity_effect(w)  # no debe lanzar
    assert w.graphicsEffect() is None
