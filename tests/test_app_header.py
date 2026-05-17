"""
Pruebas de la lógica de la cabecera y del módulo macos_native.

Solo cubrimos lo que se puede validar sin crear widgets reales: el
enum de estados de conexión y la detección de plataforma. Los tests
visuales ocurren en CI con QT_QPA_PLATFORM=offscreen.
"""

from __future__ import annotations

import sys

import pytest


# El widget completo necesita PySide6
pytest.importorskip("PySide6.QtWidgets", reason="PySide6 no instalado")

from shakevision.ui.app_header import ConnectionState  # noqa: E402
from shakevision.ui.macos_native import (  # noqa: E402
    is_macos,
    macos_dependency_hint,
    title_bar_inset_for,
    title_bar_inset_pixels,
)


# ============================================================
# ConnectionState
# ============================================================
def test_connection_state_has_four_values() -> None:
    expected = {"DISCONNECTED", "CONNECTING", "CONNECTED", "ERROR"}
    assert {s.name for s in ConnectionState} == expected


def test_connection_state_values_are_lowercase_strings() -> None:
    for state in ConnectionState:
        assert state.value == state.name.lower()


# ============================================================
# Detección de plataforma
# ============================================================
def test_is_macos_matches_sys_platform() -> None:
    assert is_macos() is (sys.platform == "darwin")


def test_title_bar_inset_pixels_zero_outside_macos() -> None:
    if sys.platform != "darwin":
        assert title_bar_inset_pixels() == 0
    else:
        assert title_bar_inset_pixels() > 0


def test_title_bar_inset_for_uses_global_helper() -> None:
    # No instanciamos QMainWindow real; pasamos None y solo
    # verificamos que la función no falla al consultar la plataforma.
    if sys.platform != "darwin":
        assert title_bar_inset_for(None) == 0  # type: ignore[arg-type]


# ============================================================
# Sugerencia de pyobjc
# ============================================================
def test_macos_dependency_hint_outside_macos_is_none() -> None:
    if sys.platform != "darwin":
        assert macos_dependency_hint() is None


def test_macos_dependency_hint_format() -> None:
    """En cualquier plataforma debe devolver str o None, nunca explotar."""

    hint = macos_dependency_hint()
    assert hint is None or isinstance(hint, str)
    if hint is not None:
        # Debe mencionar pip y el extra "macos"
        assert "pip install" in hint
        assert "macos" in hint
