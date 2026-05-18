"""
Pruebas de LocalizameScreen (v0.5 阶段 G).

Cubrimos:
  * Persistencia de la bandera "ya hecho" (sin Qt completo).
  * Cómputo del texto detectado vía detect_and_show con timezone mock.
  * Existencia de las claves i18n en los 4 idiomas.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest


pytest.importorskip("PySide6.QtCore", reason="PySide6 no instalado")


# ============================================================
# Claves i18n (no requieren Qt — solo JSON)
# ============================================================
LOCALES_DIR = (
    Path(__file__).resolve().parent.parent
    / "shakevision" / "i18n" / "locales"
)


@pytest.mark.parametrize("locale", ["en", "es", "zh", "fr"])
def test_localizame_i18n_keys_present(locale: str) -> None:
    """Las 3 claves de Localízame deben existir en cada idioma."""

    data = json.loads((LOCALES_DIR / f"{locale}.json").read_text("utf-8"))
    for key in (
        "localizame.heading",
        "localizame.detected_prefix",
        "localizame.detected_unknown",
    ):
        assert key in data, f"{locale}.json no contiene {key!r}"
        # Ningún valor debería estar vacío
        assert data[key].strip(), f"{locale}.json {key} está vacío"


# ============================================================
# Persistencia QSettings (sin GUI)
# ============================================================
def test_completed_flag_round_trip(tmp_path) -> None:
    """mark_completed + has_been_completed deben formar un par estable."""

    from PySide6.QtCore import QCoreApplication, QSettings
    from shakevision.ui import localizame_view

    # Aislar QSettings en el directorio temporal para no contaminar
    # el QSettings real del usuario que ejecuta los tests.
    QCoreApplication.setOrganizationName("SeismicGuardTest")
    QCoreApplication.setApplicationName("Onboarding")
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path))

    # Estado inicial: no completado
    localizame_view._reset_for_tests()
    # No comprobamos False directamente porque otro test puede haber
    # tocado QSettings del proceso. Lo importante es el round-trip.
    localizame_view.mark_completed()
    assert localizame_view.has_been_completed() is True
    localizame_view._reset_for_tests()


# ============================================================
# detect_and_show — usa detect_system_timezone parcheado
# ============================================================
def test_detect_and_show_uses_timezone_and_i18n(qapp_factory) -> None:
    """detect_and_show debe poblar heading + detected con i18n + tz mock."""

    from shakevision.ui.localizame_view import LocalizameScreen

    _app = qapp_factory()
    screen = LocalizameScreen()
    try:
        with patch(
            "shakevision.services.timezone_service.detect_system_timezone",
            return_value="Asia/Shanghai",
        ):
            screen.detect_and_show()
        # heading viene de i18n (en español/inglés/etc., no asertamos
        # valor exacto: solo que cambió del placeholder inicial)
        assert screen._heading and screen._heading != ""
        # detected debe contener la zona detectada
        assert "Asia/Shanghai" in screen._detected
    finally:
        screen.finish_now()


def test_detect_and_show_handles_failed_detection(qapp_factory) -> None:
    """Si detect_system_timezone devuelve None mostramos texto "unknown"."""

    from shakevision.ui.localizame_view import LocalizameScreen

    _app = qapp_factory()
    screen = LocalizameScreen()
    try:
        with patch(
            "shakevision.services.timezone_service.detect_system_timezone",
            return_value=None,
        ):
            screen.detect_and_show()
        # El texto debe ser distinto del prefijo (es el fallback unknown)
        assert "UTC" in screen._detected or "Unknown" in screen._detected \
            or "Desconocida" in screen._detected \
            or "Inconnu" in screen._detected \
            or "未知" in screen._detected
    finally:
        screen.finish_now()


def test_finished_signal_fires_on_finish_now(qapp_factory) -> None:
    """finish_now debe disparar el signal finished antes de cerrar."""

    from shakevision.ui.localizame_view import LocalizameScreen

    _app = qapp_factory()
    screen = LocalizameScreen()
    fired = []
    screen.finished.connect(lambda: fired.append(True))
    screen.finish_now()
    assert fired == [True]


# ============================================================
# Fixture
# ============================================================
@pytest.fixture(scope="session")
def qapp_factory():
    from PySide6.QtWidgets import QApplication

    def _factory():
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        return app

    return _factory
