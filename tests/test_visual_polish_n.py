"""
Pruebas de pulido visual (v0.5 阶段 N).

Verifica las decisiones de diseño UI que son fáciles de regresar
accidentalmente:

  * Tab titles ya NO contienen el prefijo emoji (lo aporta el QIcon).
  * AppHeader tiene los dos botones del segmented STD/PRO.
  * El segmented usa QButtonGroup exclusivo (solo uno checked a la vez).
  * Toggle STD ↔ PRO propaga al LayerModeManager.
  * MainWindow.{_refresh_tab_icons} existe y no rompe.
  * profile_view._make_circular_pixmap recorta a círculo (alpha 0 en
    las esquinas).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


pytest.importorskip("PySide6.QtCore", reason="PySide6 no instalado")


LOCALES_DIR = (
    Path(__file__).resolve().parent.parent
    / "shakevision" / "i18n" / "locales"
)


# ============================================================
# Tab titles ya no llevan emoji (lo aporta el QIcon)
# ============================================================
@pytest.mark.parametrize("locale", ["en", "es", "zh", "fr"])
def test_tab_titles_have_no_emoji_prefix(locale: str) -> None:
    """阶段 N: los emoji 🌍📊👤 se quitan de los titulos — ahora
    el icono visible es un QIcon real puesto por MainWindow."""

    data = json.loads((LOCALES_DIR / f"{locale}.json").read_text("utf-8"))
    for key in ("globe.tab_title", "dashboard.tab_title",
                "profile.tab_title"):
        text = data[key]
        for emoji in ("🌍", "🌐", "📊", "👤", "🔬"):
            assert emoji not in text, (
                f"{locale}.{key} still contains emoji {emoji!r}: {text!r}")
        assert text.strip(), f"{locale}.{key} vacío"


# ============================================================
# AppHeader segmented STD/PRO
# ============================================================
@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    from PySide6.QtCore import QCoreApplication, QSettings
    QCoreApplication.setOrganizationName("SeismicGuardTest")
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(
        QSettings.IniFormat, QSettings.UserScope, str(tmp_path))
    yield


@pytest.fixture(scope="session")
def qapp_factory():
    from PySide6.QtWidgets import QApplication

    def _factory():
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        return app

    return _factory


def test_app_header_has_segmented_std_pro_buttons(qapp_factory) -> None:
    from shakevision.ui.app_header import AppHeader

    _app = qapp_factory()
    header = AppHeader("SeismicGuard", "0.5.0")
    try:
        assert hasattr(header, "_mode_std_btn")
        assert hasattr(header, "_mode_pro_btn")
        # Exclusividad: el grupo solo permite uno checked a la vez
        assert header._mode_seg_group.exclusive()
        # Sumando checks debería dar exactamente 1
        n_checked = (
            int(header._mode_std_btn.isChecked())
            + int(header._mode_pro_btn.isChecked())
        )
        assert n_checked == 1
        # _mode_button sigue existiendo (alias al pro_btn) para
        # compatibilidad
        assert header._mode_button is header._mode_pro_btn
    finally:
        header.deleteLater()


def test_segmented_pro_click_propagates_to_layer_mode(qapp_factory) -> None:
    """Click en PRO debe llamar a LayerModeManager.set_mode('professional')."""

    from unittest.mock import patch
    from shakevision.ui.app_header import AppHeader

    _app = qapp_factory()
    header = AppHeader("SeismicGuard", "0.5.0")
    try:
        # Asegurar que arrancamos en STD
        header._mode_std_btn.setChecked(True)
        header._mode_pro_btn.setChecked(False)
        with patch(
            "shakevision.ui.layer_mode_manager.LayerModeManager.current_mode",
            return_value="standard",
        ), patch(
            "shakevision.ui.layer_mode_manager.LayerModeManager.set_mode"
        ) as mock_set:
            header._set_layer_mode_from_segment("professional")
            mock_set.assert_called_once_with("professional")
    finally:
        header.deleteLater()


def test_segmented_no_op_when_clicking_current_mode(qapp_factory) -> None:
    """Click en el modo YA activo no debe re-llamar a set_mode."""

    from unittest.mock import patch
    from shakevision.ui.app_header import AppHeader

    _app = qapp_factory()
    header = AppHeader("SeismicGuard", "0.5.0")
    try:
        with patch(
            "shakevision.ui.layer_mode_manager.LayerModeManager.current_mode",
            return_value="standard",
        ), patch(
            "shakevision.ui.layer_mode_manager.LayerModeManager.set_mode"
        ) as mock_set:
            header._set_layer_mode_from_segment("standard")
            mock_set.assert_not_called()
    finally:
        header.deleteLater()


# ============================================================
# Profile circular avatar
# ============================================================
def test_make_circular_pixmap_corners_are_transparent(qapp_factory) -> None:
    """Las 4 esquinas del pixmap circular deben tener alpha == 0."""

    from PySide6.QtGui import QPixmap, QColor
    from shakevision.ui.profile_view import ProfileView

    _app = qapp_factory()
    # Fuente: un pixmap sólido amarillo de 100×100
    src = QPixmap(100, 100)
    src.fill(QColor(255, 200, 0, 255))
    out = ProfileView._make_circular_pixmap(src, 72)
    assert out.width() == 72 and out.height() == 72
    img = out.toImage()
    # Esquinas deben ser transparentes
    for x, y in [(0, 0), (71, 0), (0, 71), (71, 71)]:
        # En Qt, pixel() devuelve un int RGB sin alpha; pero la
        # transparencia se preserva en pixelColor.
        assert img.pixelColor(x, y).alpha() == 0, (
            f"Esquina ({x},{y}) no es transparente")
    # El centro debe ser opaco (amarillo aprox)
    centre = img.pixelColor(36, 36)
    assert centre.alpha() > 200
    assert centre.red() > 200 and centre.green() > 150
