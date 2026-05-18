"""
Pruebas del diálogo ``AddShakeDialog``.

Cubren la lógica que NO requiere mostrar la ventana:
  * ``result_preset()`` devuelve un LanShakePreset correcto.
  * ``result_preset()`` devuelve None si los campos críticos están vacíos.
  * El OK queda deshabilitado cuando host o station están vacíos.
  * Inicialización a partir de un preset existente (edición).

NOTA: no probamos el worker TCP porque depende de la red; eso queda
para tests de integración manual con un Shake real.
"""

from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6.QtWidgets", reason="PySide6 no instalado")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialogButtonBox  # noqa: E402

from shakevision.services.shake_presets import LanShakePreset  # noqa: E402
from shakevision.ui.add_shake_dialog import AddShakeDialog     # noqa: E402


# ============================================================
# Fixture global de QApplication
# ============================================================
@pytest.fixture(scope="module")
def qt_app():
    yield QApplication.instance() or QApplication([])


# ============================================================
# Estado inicial — sin valores iniciales
# ============================================================
def test_default_initial_values(qt_app) -> None:
    dlg = AddShakeDialog()
    assert dlg.host_edit.text() == "rs.local"
    assert dlg.station_edit.text() == "R0000"
    assert dlg.port_spin.value() == 18000


def test_ok_enabled_when_host_and_station_present(qt_app) -> None:
    dlg = AddShakeDialog()
    # Valores por defecto son válidos → OK debe estar habilitado
    assert dlg.buttons.button(QDialogButtonBox.Ok).isEnabled() is True


def test_ok_disabled_when_host_empty(qt_app) -> None:
    dlg = AddShakeDialog()
    dlg.host_edit.setText("")
    assert dlg.buttons.button(QDialogButtonBox.Ok).isEnabled() is False


def test_ok_disabled_when_station_empty(qt_app) -> None:
    dlg = AddShakeDialog()
    dlg.station_edit.setText("")
    assert dlg.buttons.button(QDialogButtonBox.Ok).isEnabled() is False


# ============================================================
# result_preset()
# ============================================================
def test_result_preset_returns_built_preset(qt_app) -> None:
    dlg = AddShakeDialog()
    dlg.label_edit.setText("Lab Shake")
    dlg.host_edit.setText("192.168.1.42")
    dlg.station_edit.setText("r0e05")
    dlg.port_spin.setValue(18000)

    out = dlg.result_preset()
    assert out is not None
    assert out.label == "Lab Shake"
    assert out.host == "192.168.1.42"
    assert out.station == "R0E05"
    assert out.network == "AM"
    assert out.port == 18000


def test_result_preset_label_defaults_to_host(qt_app) -> None:
    dlg = AddShakeDialog()
    dlg.label_edit.setText("")
    dlg.host_edit.setText("10.0.0.5")
    dlg.station_edit.setText("R001")
    out = dlg.result_preset()
    assert out is not None
    assert out.label == "Shake @ 10.0.0.5"


def test_result_preset_returns_none_when_host_missing(qt_app) -> None:
    dlg = AddShakeDialog()
    dlg.host_edit.setText("")
    dlg.station_edit.setText("R001")
    assert dlg.result_preset() is None


# ============================================================
# Inicialización para edición
# ============================================================
def test_initial_preset_prefills_fields(qt_app) -> None:
    existing = LanShakePreset(
        label="Casa", host="rs.local", station="R0123",
        network="AM", location="", port=18001,
    )
    dlg = AddShakeDialog(initial=existing)
    assert dlg.label_edit.text() == "Casa"
    assert dlg.host_edit.text() == "rs.local"
    assert dlg.station_edit.text() == "R0123"
    assert dlg.port_spin.value() == 18001
