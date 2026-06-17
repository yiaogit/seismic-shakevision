"""
Panel de **densidad espectral de potencia (PSD)** del tramo seleccionado.

A diferencia del espectrograma (frecuencia × tiempo de TODA la ventana), aquí
se muestra el espectro de UN tramo — el que el usuario marca con la caja
amarilla en el oscilograma. Es el patrón "spectra" de SWARM / análisis clásico:
elegir una porción (p. ej. la onda P, o el ruido) y ver su contenido en
frecuencia.

* Eje X: frecuencia (Hz), 0 → Nyquist.
* Eje Y: potencia en dB (10·log10 de la PSD de Welch).
* Una línea marca la frecuencia dominante del tramo.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout, QWidget

from shakevision.i18n import LocaleService, t
from shakevision.ui.signal_safety import subscribe
from shakevision.ui.theme import COLOR_BACKGROUND


class SpectrumPanel(QFrame):
    """PSD (Welch) del tramo seleccionado."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("WaveformPanel")
        self.setFrameShape(QFrame.NoFrame)
        self.setMinimumHeight(140)   # v0.7.7: no aplastar bajo el splitter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self._header = QLabel(t("spectrum.title"))
        self._header.setObjectName("SectionTitle")
        self._header.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(self._header)

        self._plot = pg.PlotWidget(background=COLOR_BACKGROUND)
        self._plot.setMouseEnabled(x=True, y=True)
        self._plot.setMenuEnabled(False)
        self._plot.showGrid(x=True, y=True, alpha=0.15)
        self._plot.setLabel("bottom", t("spectrum.axis_freq"))
        self._plot.setLabel("left", t("spectrum.axis_power"))
        self._plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        from shakevision.ui.pg_theming import subscribe_pg_plot
        subscribe_pg_plot(self._plot)
        layout.addWidget(self._plot, stretch=1)

        self._curve = self._plot.plot(pen=pg.mkPen("#3b9aff", width=1.4))
        self._fdom_line = pg.InfiniteLine(
            angle=90, movable=False,
            pen=pg.mkPen("#ff8c42", width=1, style=Qt.DashLine),
            label="", labelOpts={"position": 0.9, "color": "#ff8c42"})
        self._fdom_line.setVisible(False)
        self._plot.addItem(self._fdom_line, ignoreBounds=True)

        self._empty = pg.TextItem(
            text=t("spectrum.hint"), color="#9aa0a6", anchor=(0.5, 0.5))
        self._plot.addItem(self._empty)

        subscribe(self, LocaleService.language_changed_signal(), self._retranslate)

    # ------------------------------------------------------------------
    def update_psd(self, freqs: np.ndarray, psd: np.ndarray) -> None:
        """Dibuja la PSD (en dB) y marca la frecuencia dominante."""

        if freqs is None or psd is None or len(freqs) == 0 or len(psd) == 0:
            self.clear()
            return
        self._empty.setVisible(False)
        psd_db = 10.0 * np.log10(np.asarray(psd, dtype=np.float64) + 1e-30)
        self._curve.setData(freqs, psd_db)
        # Frecuencia dominante (ignorando DC).
        if len(psd) > 1:
            idx = int(np.argmax(psd[1:])) + 1
            fdom = float(freqs[idx])
            self._fdom_line.setPos(fdom)
            self._fdom_line.label.setText(f"{fdom:.2f} Hz")
            self._fdom_line.setVisible(True)
        self._plot.enableAutoRange(axis="xy")

    def clear(self) -> None:
        self._curve.clear()
        self._fdom_line.setVisible(False)
        self._empty.setVisible(True)

    def reset(self) -> None:
        self.clear()

    def _retranslate(self) -> None:
        self._header.setText(t("spectrum.title"))
        self._plot.setLabel("bottom", t("spectrum.axis_freq"))
        self._plot.setLabel("left", t("spectrum.axis_power"))
        self._empty.setText(t("spectrum.hint"))
