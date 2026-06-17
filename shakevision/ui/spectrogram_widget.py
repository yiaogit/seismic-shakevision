"""
Panel de visualización del espectrograma (canal vertical).

Renderiza una matriz tiempo × frecuencia coloreada por potencia (dB).
PyQtGraph dispone de ``ImageItem`` que muestra arrays 2-D directamente,
con soporte para look-up tables (colormaps) y rangos dinámicos.

Convenciones visuales
---------------------
* Eje X: segundos relativos al "ahora" (mismo que el oscilograma).
* Eje Y: frecuencia en Hz, de 0 a Nyquist (50 Hz a 100 Hz de muestreo).
* Color: potencia en dB; usamos el colormap ``viridis`` (perceptual y
  legible en pantallas oscuras).
"""

from __future__ import annotations

from typing import Optional

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout, QWidget

from shakevision.i18n import LocaleService, t
from shakevision.processing.spectrum import SpectrumResult
from shakevision.ui.signal_safety import subscribe
from shakevision.ui.theme import (
    COLOR_BACKGROUND,
)


# Rango dinámico por defecto del mapa de calor (dB)
DEFAULT_DB_MIN: float = -90.0
DEFAULT_DB_MAX: float = -10.0


class SpectrogramPanel(QFrame):
    """Mapa de calor tiempo-frecuencia para el canal vertical."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("WaveformPanel")  # Reutiliza el estilo del panel de ondas
        self.setFrameShape(QFrame.NoFrame)
        # v0.7.7: altura mínima para que el splitter NO lo aplaste a una
        # franja donde no se ven los ticks de frecuencia.
        self.setMinimumHeight(140)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Cabecera (i18n-aware)
        self._header = QLabel(t("spectrogram.title"))
        self._header.setObjectName("SectionTitle")
        self._header.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(self._header)

        # PlotWidget contenedor — v0.6 P11: theme-aware
        self._plot = pg.PlotWidget(background=COLOR_BACKGROUND)
        self._plot.setMouseEnabled(x=True, y=False)
        self._plot.setMenuEnabled(False)
        self._plot.showGrid(x=True, y=True, alpha=0.10)
        self._plot.setLabel("bottom", t("spectrogram.axis_time"))
        self._plot.setLabel("left", t("spectrogram.axis_freq"))
        self._plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        from shakevision.ui.pg_theming import subscribe_pg_plot
        subscribe_pg_plot(self._plot)
        layout.addWidget(self._plot, stretch=1)

        subscribe(self, LocaleService.language_changed_signal(),
                  self._retranslate)  # v0.7.7 (B1)

        # ImageItem que muestra la matriz de potencia
        self._image = pg.ImageItem()
        # ``axisOrder='row-major'`` interpreta el array como (filas=Y, cols=X),
        # que es lo que devuelve ``scipy.signal.spectrogram``.
        self._image.setOpts(axisOrder="row-major")

        # Aplicar el colormap "viridis" como lookup table
        self._cmap = pg.colormap.get("viridis")
        self._image.setLookupTable(self._cmap.getLookupTable())

        # Rango dinámico inicial (dB)
        self._image.setLevels((DEFAULT_DB_MIN, DEFAULT_DB_MAX))

        self._plot.addItem(self._image)

        # v0.7.7: barra de color a la derecha = leyenda de potencia (dB) +
        # CONTRASTE ajustable (se arrastra para mover los niveles). Defensivo:
        # si la versión de pyqtgraph no soporta ColorBarItem, se omite.
        self._colorbar = None
        try:
            self._colorbar = pg.ColorBarItem(
                values=(DEFAULT_DB_MIN, DEFAULT_DB_MAX),
                colorMap=self._cmap, label="dB", interactive=True)
            self._colorbar.setImageItem(
                self._image, insert_in=self._plot.getPlotItem())
        except Exception:  # noqa: BLE001
            self._colorbar = None

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def _retranslate(self) -> None:
        """Re-aplica labels traducidos al cambiar idioma."""

        self._header.setText(t("spectrogram.title"))
        self._plot.setLabel("bottom", t("spectrogram.axis_time"))
        self._plot.setLabel("left", t("spectrogram.axis_freq"))

    def update_from_spectrum(self, spectrum: SpectrumResult) -> None:
        """Refresca el mapa de calor con un nuevo ``SpectrumResult``."""

        if spectrum.power_db.size == 0:
            return

        # Ajustar el ImageItem al rango (X: tiempos, Y: frecuencias).
        # ``setRect`` evita tener que reescalar manualmente el array.
        x0 = float(spectrum.times[0])
        x1 = float(spectrum.times[-1]) if spectrum.times.size > 1 else x0 + 1.0
        y0 = float(spectrum.freqs[0])
        y1 = float(spectrum.freqs[-1])

        self._image.setImage(
            spectrum.power_db,
            autoLevels=False,
            autoDownsample=True,
        )
        self._image.setRect(x0, y0, x1 - x0, y1 - y0)

        # Fijar el rango visible para que coincida con el oscilograma
        self._plot.setXRange(x0, x1, padding=0.0)
        self._plot.setYRange(y0, y1, padding=0.0)

    def reset(self) -> None:
        """Limpia el mapa (se llama al cambiar de estación)."""

        self._image.clear()

    def set_db_range(self, db_min: float, db_max: float) -> None:
        """Permite al usuario ajustar el rango dinámico mostrado."""

        if db_min >= db_max:
            return
        self._image.setLevels((db_min, db_max))
        if self._colorbar is not None:
            try:
                self._colorbar.setLevels((db_min, db_max))
            except Exception:  # noqa: BLE001
                pass
