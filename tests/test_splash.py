"""
Pruebas del SplashScreen (v0.5 — rebrand + barra de progreso).

Las pruebas que requieren QApplication usan ``QT_QPA_PLATFORM=offscreen``
en CI; localmente Pytest las salta si PySide6 no está instalado.
"""

from __future__ import annotations

import pytest


pytest.importorskip("PySide6.QtWidgets", reason="PySide6 no instalado")


# ============================================================
# API de progreso (introspección sin pintar)
# ============================================================
def test_set_progress_clamps_and_animates_toward_target(qapp_factory) -> None:
    """set_progress fija el objetivo; _tick interpola hacia él."""

    from shakevision.ui.splash import SplashScreen

    _app = qapp_factory()
    splash = SplashScreen(version="0.5.0")
    try:
        # Estado inicial: ambos en 0
        assert splash._progress == 0.0
        assert splash._progress_target == 0.0

        # Clamp por debajo
        splash.set_progress(-0.5)
        assert splash._progress_target == 0.0

        # Clamp por arriba
        splash.set_progress(1.5)
        assert splash._progress_target == 1.0

        # Valor válido
        splash.set_progress(0.4)
        assert splash._progress_target == pytest.approx(0.4)

        # _tick avanza _progress hacia _progress_target.
        before = splash._progress
        splash._tick()
        assert splash._progress > before
        # No debe sobrepasar el objetivo en un solo tick.
        assert splash._progress <= splash._progress_target + 1e-6
    finally:
        splash.finish_and_close()


def test_set_status_updates_text(qapp_factory) -> None:
    """set_status debe actualizar el texto y forzar repaint."""

    from shakevision.ui.splash import SplashScreen

    _app = qapp_factory()
    splash = SplashScreen(version="0.5.0")
    try:
        splash.set_status("Cargando 1/3")
        assert splash._status == "Cargando 1/3"
        splash.set_status("Cargando 2/3")
        assert splash._status == "Cargando 2/3"
    finally:
        splash.finish_and_close()


def test_logo_is_attempted_at_construction(qapp_factory) -> None:
    """El splash intenta cargar el logo dark al construirse.

    No asertamos que el QPixmap sea non-null porque depende de si el
    PNG está empaquetado en el entorno de test; sí asertamos que la
    referencia existe como atributo (el render fallback al texto
    funciona si es nulo).
    """

    from shakevision.ui.splash import SplashScreen

    _app = qapp_factory()
    splash = SplashScreen(version="0.5.0")
    try:
        assert hasattr(splash, "_logo")
    finally:
        splash.finish_and_close()


# ============================================================
# Fixture local para reutilizar la misma QApplication entre tests
# ============================================================
@pytest.fixture(scope="session")
def qapp_factory():
    """Devuelve un factory que entrega la QApplication singleton."""

    from PySide6.QtWidgets import QApplication

    def _factory():
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        return app

    return _factory
