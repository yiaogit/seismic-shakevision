"""
Pruebas mínimas del SidebarNav.

Verificamos:
  * que se construye con N elementos y crea N botones;
  * que ``set_current_index`` cambia el botón activo;
  * que ``current_changed`` se emite con el índice correcto;
  * que ``add_secondary_item`` añade un nuevo elemento al final.

Requiere PySide6 — se omite si no está instalado.
"""

from __future__ import annotations

import os

import pytest


pytest.importorskip("PySide6.QtWidgets", reason="PySide6 no instalado")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from shakevision.ui.sidebar_nav import (  # noqa: E402
    SIDEBAR_WIDTH_PX,
    NavItem,
    SidebarNav,
)


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def _make_items(n: int = 3) -> list[NavItem]:
    return [
        NavItem(icon="📡", label=f"Item{i}", tooltip=f"Tooltip {i}")
        for i in range(n)
    ]


# ============================================================
# Construcción
# ============================================================
def test_sidebar_has_fixed_width(qt_app) -> None:
    nav = SidebarNav(_make_items(3))
    assert nav.width() == SIDEBAR_WIDTH_PX


def test_sidebar_creates_one_button_per_item(qt_app) -> None:
    nav = SidebarNav(_make_items(4))
    # 4 botones internos; el _group debería contener 4 elementos
    assert len(nav._buttons) == 4


def test_first_button_is_initially_checked(qt_app) -> None:
    nav = SidebarNav(_make_items(3))
    assert nav.current_index() == 0


# ============================================================
# Cambios y señal
# ============================================================
def test_set_current_index_changes_active(qt_app) -> None:
    nav = SidebarNav(_make_items(3))
    nav.set_current_index(2)
    assert nav.current_index() == 2


def test_current_changed_emits_when_index_changes(qt_app) -> None:
    nav = SidebarNav(_make_items(3))
    received: list[int] = []
    nav.current_changed.connect(lambda i: received.append(i))
    nav.set_current_index(1)
    assert 1 in received


def test_set_current_index_out_of_range_is_noop(qt_app) -> None:
    nav = SidebarNav(_make_items(3))
    nav.set_current_index(10)
    assert nav.current_index() == 0  # sigue donde estaba


# ============================================================
# add_secondary_item
# ============================================================
def test_add_secondary_item_appends_button(qt_app) -> None:
    nav = SidebarNav(_make_items(3))
    new_idx = nav.add_secondary_item(
        NavItem(icon="⚙", label="Set", tooltip="Settings")
    )
    assert new_idx == 3
    assert len(nav._buttons) == 4
