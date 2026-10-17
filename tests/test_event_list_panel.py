"""
Pruebas del ``EventListPanel``: recorte a ``_MAX_ROWS`` y persistencia del
aviso de recorte tras un cambio de idioma.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6.QtWidgets", reason="PySide6 no instalado")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

import shakevision.ui.event_list_panel as elp  # noqa: E402
from shakevision.i18n import t  # noqa: E402


@pytest.fixture(scope="module")
def qt_app():
    yield QApplication.instance() or QApplication([])


def _quake(i: int) -> SimpleNamespace:
    """Objeto mínimo que ``set_events`` necesita (no hace falta Earthquake)."""

    return SimpleNamespace(
        timestamp_unix=1_000_000.0 + i,
        id=f"q{i}",
        magnitude=3.0 + i * 0.1,
        depth_km=10.0,
        place=f"Place {i}",
    )


def test_capped_hint_is_rendered(qt_app, monkeypatch) -> None:
    monkeypatch.setattr(elp, "_MAX_ROWS", 2)
    panel = elp.EventListPanel()

    panel.set_events([_quake(i) for i in range(3)])

    assert panel._table.rowCount() == 2
    assert panel._hint.text() == t(
        "events.showing_capped", shown=2, total=3)


def test_capped_hint_survives_retranslate(qt_app, monkeypatch) -> None:
    """El aviso no debe perderse al cambiar de idioma.

    ``_retranslate`` llama a ``_update_hint``; antes eso reemplazaba el aviso
    de recorte por la instrucción genérica ("doble clic…").
    """

    monkeypatch.setattr(elp, "_MAX_ROWS", 2)
    panel = elp.EventListPanel()
    panel.set_events([_quake(i) for i in range(3)])
    expected = t("events.showing_capped", shown=2, total=3)

    panel._retranslate()

    assert panel._hint.text() == expected


def test_uncapped_hint_uses_instruction(qt_app, monkeypatch) -> None:
    monkeypatch.setattr(elp, "_MAX_ROWS", 2)
    panel = elp.EventListPanel()

    panel.set_events([_quake(0), _quake(1)])

    assert panel._hint.text() == t("events.hint")
