"""
Pruebas mínimas del LoadingOverlay (smoke test, requiere PySide6).
"""

from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6.QtWidgets", reason="PySide6 no instalado")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFrame  # noqa: E402

from shakevision.ui.loading_overlay import LoadingOverlay  # noqa: E402


@pytest.fixture(scope="module")
def qt_app():
    yield QApplication.instance() or QApplication([])


def test_loading_overlay_shows_loading(qt_app) -> None:
    parent = QFrame()
    parent.resize(400, 300)
    overlay = LoadingOverlay(parent)
    overlay.show_loading("Cargando", "subtítulo")
    assert overlay.isVisible()


def test_loading_overlay_shows_error_with_retry(qt_app) -> None:
    parent = QFrame()
    parent.resize(400, 300)
    overlay = LoadingOverlay(parent)
    overlay.show_error("Falló la red")
    assert overlay.isVisible()


def test_loading_overlay_emits_retry_clicked(qt_app) -> None:
    parent = QFrame()
    parent.resize(400, 300)
    overlay = LoadingOverlay(parent)
    overlay.show_error("Falló")
    received: list = []
    overlay.retry_clicked.connect(lambda: received.append(True))
    overlay._retry_button.click()
    assert received == [True]


def test_loading_overlay_hide(qt_app) -> None:
    parent = QFrame()
    parent.resize(400, 300)
    overlay = LoadingOverlay(parent)
    overlay.show_loading()
    overlay.hide_overlay()
    assert not overlay.isVisible()
