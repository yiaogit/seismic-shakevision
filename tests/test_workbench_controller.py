"""Tests para ``WorkbenchController`` (v0.7.7, S1).

El controlador ahora construye objetos Qt reales (AudioPlayer, QTimer,
RingBuffer, detector…), así que necesita un ``QApplication``. En entornos
sin backend gráfico Qt (p. ej. el sandbox de Cowork, sin libEGL) la
importación de ``QtWidgets`` falla y estos tests se **saltan** limpiamente;
en la máquina del usuario / CI con Qt, se ejecutan con la suite GUI.

Usan un *stub* de vista (en vez de un ``ProWindow`` real) que provee solo
los paneles que el controlador toca durante la construcción y los tests.
"""

from __future__ import annotations

import pytest

# Requiere el stack GUI de Qt; si no se puede importar (p. ej. sandbox sin
# libEGL), saltar TODO el módulo de forma limpia. Usamos try/except en vez
# de importorskip porque el fallo es un ImportError de librería nativa
# (libEGL.so) que importorskip no siempre intercepta.
try:
    from PySide6.QtWidgets import QApplication, QWidget

    from shakevision.config import AppConfig
    from shakevision.ui.workbench_controller import WorkbenchController
except Exception as _exc:  # noqa: BLE001
    pytest.skip(
        f"PySide6 GUI no disponible ({_exc})", allow_module_level=True,
    )


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _StubPanel(QWidget):
    """Panel mínimo. Subclase de ``QWidget`` para soportar la API que el
    controlador toca (``setProperty`` / ``style`` / ``setGraphicsEffect``
    en la animación de alerta), más los métodos de panel que usa."""

    def __init__(self) -> None:
        super().__init__()
        self.label = None

    def set_station_label(self, label) -> None:
        self.label = label

    def refresh(self) -> None:
        ...

    def reset(self) -> None:
        ...


class _StubView:
    """Vista mínima en lugar de un ``ProWindow`` real."""

    def __init__(self) -> None:
        self.waveform_panel = _StubPanel()
        self.spectrogram_panel = _StubPanel()
        self.particle_panel = _StubPanel()
        self.helicorder_panel = _StubPanel()
        self.intensity_card = _StubPanel()
        self.control_panel = _StubPanel()


def _make_controller():
    return WorkbenchController(config=AppConfig(), view=_StubView())


def test_constructs_with_default_config(qapp):
    ctrl = _make_controller()
    # La estación inicial es la primera de la config por defecto.
    assert ctrl.current_station is not None
    assert ctrl.current_station.network == AppConfig().stations[0].network
    assert ctrl.has_source is False
    # El controlador fijó la etiqueta inicial en el panel de ondas.
    assert ctrl.view.waveform_panel.label == ctrl.current_station.label


def test_signals_emit(qapp):
    ctrl = _make_controller()
    received: dict = {}
    ctrl.status_message.connect(lambda t, ms: received.update(status=(t, ms)))
    ctrl.latency_text.connect(lambda s: received.update(latency=s))
    ctrl.station_changed.connect(lambda s: received.update(station=s))
    ctrl.connection_status_changed.connect(
        lambda t, o: received.update(conn=(t, o)))

    ctrl.status_message.emit("hola", 5000)
    ctrl.latency_text.emit("12 ms")
    ctrl.station_changed.emit("IU.ANMO")
    ctrl.connection_status_changed.emit("Conectado", "StatusOk")

    assert received["status"] == ("hola", 5000)
    assert received["latency"] == "12 ms"
    assert received["station"] == "IU.ANMO"
    assert received["conn"] == ("Conectado", "StatusOk")


def test_on_station_changed_updates_state_and_emits(qapp):
    ctrl = _make_controller()
    seen = {}
    ctrl.station_changed.connect(lambda s: seen.update(station=s))

    new_station = AppConfig().stations[-1]
    ctrl.on_station_changed(new_station)

    assert ctrl.current_station is new_station
    assert ctrl.view.waveform_panel.label == new_station.label
    assert seen["station"] == f"{new_station.network}.{new_station.station}"


def test_shutdown_is_safe_without_source(qapp):
    ctrl = _make_controller()
    # Sin fuente activa, shutdown solo para timers/audio (idempotente).
    ctrl.shutdown()
    assert ctrl.has_source is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
