"""
Panel de visualización de formas de onda (tres canales apilados).

Renderizado
-----------
Cada canal se pinta en su propio ``PlotWidget`` y los tres comparten el
eje X (tiempo, en segundos relativos al instante actual). El método
``update_from_snapshot`` recibe un ``BufferSnapshot`` ya empaquetado
por la ventana principal y refresca las tres trazas en una sola llamada,
lo que minimiza el coste por frame.

El eje X muestra valores negativos (segundos hacia el pasado) porque el
"ahora" siempre está pegado al borde derecho del gráfico — es la
convención visual de los osciloscopios y de las estaciones sísmicas
profesionales.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout, QWidget

from shakevision.i18n import LocaleService, t
from shakevision.processing.buffer import BufferSnapshot
from shakevision.ui.theme import (
    COLOR_BACKGROUND,
    COLOR_PANEL_BORDER,
    COLOR_TEXT_SECONDARY,
    WAVEFORM_COLORS,
)


# Lista de canales mostrados, en el orden vertical EHZ -> EHN -> EHE
_CHANNELS: list[str] = ["Z", "N", "E"]


def _build_plot_widget(channel: str) -> pg.PlotWidget:
    """Crea un ``PlotWidget`` que sigue el tema activo en caliente."""

    plot = pg.PlotWidget(background=COLOR_BACKGROUND)
    plot.setMouseEnabled(x=True, y=False)             # Solo zoom horizontal
    plot.setMenuEnabled(False)
    plot.showGrid(x=True, y=True, alpha=0.15)
    plot.setLabel("left", f"EH{channel}")
    plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    # v0.6 P11: suscribir al ThemeManager — el helper aplica
    # background + axis pens con la paleta actual y re-aplica al
    # cambiar de tema. Reemplaza las llamadas estáticas setPen /
    # setTextPen que se quedaban "congeladas" al arranque.
    from shakevision.ui.pg_theming import subscribe_pg_plot
    subscribe_pg_plot(plot)
    return plot


class WaveformPanel(QFrame):
    """Panel con tres trazas apiladas (Z, N, E)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("WaveformPanel")
        self.setFrameShape(QFrame.NoFrame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Cabecera con la etiqueta de la estación actual. Guardamos
        # la etiqueta cruda para poder retraducir al cambiar idioma.
        self._station_text: str = "—"
        self.station_header = QLabel(t("waveform.station_label", label="—"))
        self.station_header.setObjectName("SectionTitle")
        self.station_header.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(self.station_header)

        # Crear un PlotWidget por canal y guardarlos en un diccionario
        self._plots: dict[str, pg.PlotWidget] = {}
        self._curves: dict[str, pg.PlotDataItem] = {}

        for channel in _CHANNELS:
            plot = _build_plot_widget(channel)
            curve = plot.plot(
                pen=pg.mkPen(WAVEFORM_COLORS[channel], width=1.2),
            )
            self._plots[channel] = plot
            self._curves[channel] = curve
            layout.addWidget(plot, stretch=1)

        # Compartir el eje X entre los tres gráficos para que el zoom y
        # el desplazamiento sean síncronos.
        for channel in _CHANNELS[1:]:
            self._plots[channel].setXLink(self._plots[_CHANNELS[0]])

        # Solo el gráfico inferior muestra etiqueta del eje X (segundos);
        # los otros la ocultan para ganar espacio vertical.
        self._plots[_CHANNELS[-1]].setLabel("bottom", t("waveform.axis_time"))
        for channel in _CHANNELS[:-1]:
            self._plots[channel].getAxis("bottom").setStyle(showValues=False)

        # Bloquear el rango Y inicial para que las primeras llegadas no
        # provoquen un "salto" visual; el usuario puede ajustarlo después.
        for plot in self._plots.values():
            plot.setYRange(-2.0, 2.0, padding=0.0)

        # Re-traducir cabecera y eje X al cambiar idioma en caliente.
        LocaleService.language_changed_signal().connect(self._retranslate)

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def set_station_label(self, label: str) -> None:
        """Actualiza la cabecera con la estación seleccionada."""

        self._station_text = label
        self.station_header.setText(
            t("waveform.station_label", label=label)
        )

    def _retranslate(self) -> None:
        """Re-aplica labels traducidos al cambiar idioma."""

        self.station_header.setText(
            t("waveform.station_label", label=self._station_text)
        )
        self._plots[_CHANNELS[-1]].setLabel("bottom", t("waveform.axis_time"))

    def update_from_snapshot(self, snapshot: BufferSnapshot) -> None:
        """Refresca las tres trazas a partir de una instantánea del búfer."""

        times = snapshot.times
        for channel in _CHANNELS:
            samples = snapshot.samples.get(channel)
            if samples is None or samples.size == 0:
                continue
            self._curves[channel].setData(times, samples)

        # Fijar el rango X exactamente a la ventana solicitada para que
        # el "ahora" quede en el borde derecho y se aprecie el desplazamiento.
        if times.size:
            x_min = float(times[0])
            x_max = float(times[-1])
            self._plots[_CHANNELS[0]].setXRange(x_min, x_max, padding=0.0)

    def update_channel(self, channel: str, samples: np.ndarray) -> None:
        """Compatibilidad: refresca un único canal con su array de muestras.

        Útil para pruebas o para futuras integraciones puntuales.
        """

        curve: Optional[pg.PlotDataItem] = self._curves.get(channel)
        if curve is None:
            return
        curve.setData(samples)

    def reset(self) -> None:
        """Limpia todas las trazas (al cambiar de estación, por ejemplo)."""

        for curve in self._curves.values():
            curve.clear()
