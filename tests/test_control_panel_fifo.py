"""
Pruebas de ``ControlPanel.append_dynamic_station`` y su FIFO.

Estas pruebas necesitan PySide6 + un QApplication vivo para instanciar
ControlPanel (es un QFrame con widgets). Se omiten si PySide6 no está
disponible (CI mínimo).
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6.QtCore", reason="PySide6 no instalado")
pytest.importorskip("PySide6.QtWidgets", reason="QtWidgets no disponible")

from PySide6.QtWidgets import QApplication  # noqa: E402

from shakevision.config import AppConfig, StationPreset  # noqa: E402
from shakevision.ui.control_panel import ControlPanel  # noqa: E402


@pytest.fixture(scope="module")
def app():
    """QApplication única para todo el módulo."""

    instance = QApplication.instance() or QApplication([])
    return instance


@pytest.fixture
def panel(app):
    return ControlPanel(config=AppConfig())


def _preset(net: str, code: str, label: str | None = None) -> StationPreset:
    return StationPreset(
        label=label or f"{net}.{code}",
        network=net,
        station=code,
        location="*",
        channel="BHZ",
        seedlink_host="rtserve.iris.washington.edu",
        seedlink_port=18000,
    )


def test_append_adds_to_combo(panel) -> None:
    initial = panel.station_combo.count()
    added = panel.append_dynamic_station(_preset("IU", "ANMO"))
    assert added is True
    assert panel.station_combo.count() == initial + 1
    assert panel.dynamic_station_count() == 1


def test_append_duplicate_does_not_duplicate(panel) -> None:
    panel.append_dynamic_station(_preset("IU", "ANMO"))
    initial = panel.station_combo.count()
    added = panel.append_dynamic_station(_preset("IU", "ANMO"))
    assert added is False
    assert panel.station_combo.count() == initial


def test_fifo_evicts_oldest_when_capacity_exceeded(panel) -> None:
    """Al añadir la 9ª se desaloja la 1ª (FIFO)."""

    for i in range(panel.MAX_DYNAMIC_STATIONS):
        panel.append_dynamic_station(_preset("IU", f"S{i:03d}"))
    assert panel.dynamic_station_count() == panel.MAX_DYNAMIC_STATIONS

    # Añadir una más → debe evict S000
    panel.append_dynamic_station(_preset("IU", "NEW"))
    assert panel.dynamic_station_count() == panel.MAX_DYNAMIC_STATIONS

    # S000 ya no debe estar en el combo. Filtramos por isinstance porque
    # v0.3.0 añadió un sentinel "➕ Add LAN Shake…" cuyo userData es un
    # ``object()`` puro, no StationPreset.
    from shakevision.config import StationPreset as _SP

    found_s000 = False
    found_new = False
    for i in range(panel.station_combo.count()):
        d = panel.station_combo.itemData(i)
        if not isinstance(d, _SP):
            continue
        if d.network == "IU" and d.station == "S000":
            found_s000 = True
        if d.network == "IU" and d.station == "NEW":
            found_new = True
    assert found_s000 is False, "S000 (más antigua) debería haber sido desalojada"
    assert found_new is True, "NEW debe estar presente"


def test_config_presets_never_evicted(panel) -> None:
    """Aunque el FIFO se llene, las estaciones de AppConfig se preservan."""

    from shakevision.config import StationPreset as _SP

    # AppConfig() trae LAN Shake (AM.LOCAL) por defecto (v0.8.0: ya NO trae
    # la estación Demo XX.MOCK). Contamos solo presets reales (no el sentinel).
    initial_real_count = sum(
        1 for i in range(panel.station_combo.count())
        if isinstance(panel.station_combo.itemData(i), _SP)
    )
    for i in range(panel.MAX_DYNAMIC_STATIONS + 5):
        panel.append_dynamic_station(_preset("IU", f"X{i:03d}"))

    # AM.LOCAL (preset estático) debe seguir ahí pese al FIFO.
    presets_in_combo = [
        panel.station_combo.itemData(i)
        for i in range(panel.station_combo.count())
        if isinstance(panel.station_combo.itemData(i), _SP)
    ]
    nslc = {(p.network, p.station) for p in presets_in_combo}
    assert ("AM", "LOCAL") in nslc, "LAN Shake no debe ser desalojada"
    # Total presets reales = presets fijos iniciales + MAX_DYNAMIC_STATIONS
    assert len(presets_in_combo) == initial_real_count + panel.MAX_DYNAMIC_STATIONS
