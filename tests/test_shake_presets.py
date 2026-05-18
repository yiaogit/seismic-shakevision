"""
Pruebas del almacén ``shake_presets``.

Cubren:
  * Round-trip QSettings → store → QSettings.
  * Reglas de adición (host duplicado reemplaza, no añade duplicado).
  * Renombrar conserva el resto de campos.
  * Borrar es idempotente.
  * ``to_station_preset()`` produce el wiring correcto para SeedLinkSource.
"""

from __future__ import annotations

import os

import pytest

# El módulo importa PySide6.QtCore, así que saltamos si no está.
pytest.importorskip("PySide6.QtCore", reason="PySide6 no instalado")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QSettings  # noqa: E402

from shakevision.services.shake_presets import (  # noqa: E402
    DEFAULT_PORT,
    LanShakePreset,
    ShakePresetStore,
    _reset_for_tests,
)


# ============================================================
# Fixtures
# ============================================================
@pytest.fixture(scope="module")
def qt_app():
    app = QCoreApplication.instance() or QCoreApplication([])
    yield app


@pytest.fixture(autouse=True)
def _clean_settings(qt_app, tmp_path, monkeypatch):
    """Aísla cada test: QSettings en disco temporal + singleton vacío."""

    # Forzar QSettings a usar el tmp_path como ubicación INI.
    QSettings.setPath(
        QSettings.IniFormat, QSettings.UserScope, str(tmp_path),
    )
    _reset_for_tests()
    yield
    ShakePresetStore.clear()
    _reset_for_tests()


# ============================================================
# Modelo
# ============================================================
def test_from_dict_normalizes_fields() -> None:
    p = LanShakePreset.from_dict({
        "label": "  My Shake  ",
        "host": "  192.168.1.42 ",
        "station": " r0e05 ",
        "network": " am ",
        "port": "18000",
    })
    assert p.label == "My Shake"
    assert p.host == "192.168.1.42"
    assert p.station == "R0E05"
    assert p.network == "AM"
    assert p.port == 18000


def test_from_dict_uses_host_as_label_when_empty() -> None:
    p = LanShakePreset.from_dict({"host": "rs.local", "station": "X"})
    assert p.label == "rs.local"


def test_to_station_preset_carries_seedlink_override() -> None:
    lan = LanShakePreset(
        label="Test", host="10.0.0.5", station="R1234",
        network="AM", location="", port=18000,
    )
    sp = lan.to_station_preset()
    assert sp.network == "AM"
    assert sp.station == "R1234"
    assert sp.seedlink_host == "10.0.0.5"
    assert sp.seedlink_port == 18000
    assert sp.channel == "EHZ"


# ============================================================
# Store: CRUD
# ============================================================
def test_initially_empty() -> None:
    assert ShakePresetStore.all() == []


def test_add_new_returns_true() -> None:
    lan = LanShakePreset(label="A", host="rs.local", station="R0001")
    assert ShakePresetStore.add(lan) is True
    assert len(ShakePresetStore.all()) == 1


def test_add_existing_host_replaces_not_duplicates() -> None:
    ShakePresetStore.add(LanShakePreset(label="Old", host="rs.local", station="R0001"))
    result = ShakePresetStore.add(LanShakePreset(label="New", host="rs.local", station="R9999"))
    assert result is False  # "no era nuevo"
    presets = ShakePresetStore.all()
    assert len(presets) == 1
    assert presets[0].label == "New"
    assert presets[0].station == "R9999"


def test_delete_existing_returns_true() -> None:
    ShakePresetStore.add(LanShakePreset(label="A", host="rs.local", station="R0001"))
    assert ShakePresetStore.delete("rs.local") is True
    assert ShakePresetStore.all() == []


def test_delete_missing_returns_false() -> None:
    assert ShakePresetStore.delete("nada.local") is False


def test_rename_only_changes_label() -> None:
    ShakePresetStore.add(LanShakePreset(label="Old", host="rs.local", station="R0001"))
    assert ShakePresetStore.rename("rs.local", "New label") is True
    p = ShakePresetStore.all()[0]
    assert p.label == "New label"
    assert p.station == "R0001"
    assert p.host == "rs.local"


def test_rename_empty_label_rejected() -> None:
    ShakePresetStore.add(LanShakePreset(label="X", host="rs.local", station="R0"))
    assert ShakePresetStore.rename("rs.local", "   ") is False
    assert ShakePresetStore.all()[0].label == "X"


def test_find_by_host_case_insensitive() -> None:
    ShakePresetStore.add(LanShakePreset(label="A", host="RS.local", station="R0"))
    assert ShakePresetStore.find_by_host("rs.LOCAL") is not None


# ============================================================
# Persistencia QSettings round-trip
# ============================================================
def test_round_trip_through_qsettings() -> None:
    ShakePresetStore.add(LanShakePreset(
        label="Lab Shake", host="192.168.1.42", station="R0E05",
        network="AM", port=18000,
    ))
    ShakePresetStore.add(LanShakePreset(
        label="Casa", host="rs.local", station="R1234", port=18000,
    ))

    # Forzar nueva instancia (= leer de QSettings)
    _reset_for_tests()

    presets = ShakePresetStore.all()
    assert len(presets) == 2
    hosts = {p.host for p in presets}
    assert hosts == {"192.168.1.42", "rs.local"}


# ============================================================
# Signal de cambios
# ============================================================
def test_changed_signal_fires_on_add(qt_app) -> None:
    received: list = []
    ShakePresetStore.changed_signal().connect(lambda: received.append(1))
    ShakePresetStore.add(LanShakePreset(label="A", host="rs.local", station="R0"))
    assert received == [1]


def test_changed_signal_fires_on_delete(qt_app) -> None:
    ShakePresetStore.add(LanShakePreset(label="A", host="rs.local", station="R0"))
    received: list = []
    ShakePresetStore.changed_signal().connect(lambda: received.append(1))
    ShakePresetStore.delete("rs.local")
    assert received == [1]
