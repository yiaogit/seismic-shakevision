"""
Visualización de movimiento de partícula (hodograma) en el plano N-E.

Para los últimos ``window_seconds`` segundos pintamos en el plano
horizontal una curva paramétrica donde X = canal Este (EHE) e
Y = canal Norte (EHN). El resultado es la "trayectoria" del suelo:

  - Una **línea recta** indica polarización lineal (típica de ondas P).
  - Una **elipse** indica una onda S o de superficie con polarización
    elíptica (Rayleigh, Love).
  - Un **manchurrón** sin estructura indica ruido o señal incoherente.

Detalles de renderizado
-----------------------
* La curva se discretiza en ``n_segments`` segmentos y a cada uno se le
  asigna un color del mapa "viridis" (oscuro = pasado, brillante =
  presente). Eso reproduce el clásico efecto "estela de osciloscopio".
* La escala se ajusta automáticamente al máximo absoluto reciente, con
  un suelo mínimo para que la imagen no parpadee en silencios.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout, QWidget

from shakevision.i18n import LocaleService, t
from shakevision.ui.theme import (
    COLOR_BACKGROUND,
    COLOR_PANEL_BORDER,
    COLOR_TEXT_SECONDARY,
)


# ============================================================
# Helpers puros (testeables sin Qt)
# ============================================================
def color_trail(n: int) -> np.ndarray:
    """Genera ``n`` colores RGBA en gradiente viridis (oscuro→brillante).

    Devuelve un array (n, 4) con valores 0–255 listos para PyQtGraph.
    """

    if n <= 0:
        return np.zeros((0, 4), dtype=np.uint8)
    cmap = pg.colormap.get("viridis")
    lut = cmap.getLookupTable(nPts=max(n, 16), alpha=True)
    # Reescalar a la longitud pedida
    indices = np.linspace(0, lut.shape[0] - 1, n).astype(np.int32)
    return lut[indices]


def auto_range(samples: np.ndarray, floor: float = 0.05) -> float:
    """Devuelve un rango simétrico cómodo para el plano N-E."""

    if samples.size == 0:
        return floor
    peak = float(np.max(np.abs(samples)))
    return max(peak * 1.15, floor)


# ============================================================
# Panel Qt
# ============================================================
class ParticleMotionPanel(QFrame):
    """Hodograma N-E con efecto de estela cromática."""

    def __init__(
        self,
        sample_rate_hz: int = 100,
        window_seconds: float = 1.5,
        n_segments: int = 60,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("WaveformPanel")
        self.setFrameShape(QFrame.NoFrame)

        self._sample_rate = int(sample_rate_hz)
        self._window_samples = int(window_seconds * sample_rate_hz)
        self._n_segments = int(n_segments)

        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self._window_seconds_val = float(window_seconds)
        self._header = QLabel(
            t("particle.title", seconds=self._window_seconds_val)
        )
        self._header.setObjectName("SectionTitle")
        self._header.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(self._header)

        # v0.6 P11: theme-aware
        self._plot = pg.PlotWidget(background=COLOR_BACKGROUND)
        self._plot.setMouseEnabled(x=False, y=False)
        self._plot.setMenuEnabled(False)
        self._plot.showGrid(x=True, y=True, alpha=0.10)
        self._plot.setAspectLocked(True)
        self._plot.setLabel("bottom", t("particle.axis_east"))
        self._plot.setLabel("left", t("particle.axis_north"))
        self._plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        from shakevision.ui.pg_theming import subscribe_pg_plot
        subscribe_pg_plot(self._plot)
        layout.addWidget(self._plot, stretch=1)

        LocaleService.language_changed_signal().connect(self._retranslate)

    def _retranslate(self) -> None:
        self._header.setText(
            t("particle.title", seconds=self._window_seconds_val)
        )
        self._plot.setLabel("bottom", t("particle.axis_east"))
        self._plot.setLabel("left", t("particle.axis_north"))

        # Crear ``n_segments`` curvas individuales: cada una recibirá su
        # propio color del gradiente. Es más caro que una sola curva
        # multicolor, pero PyQtGraph no soporta gradiente nativo en
        # PlotCurveItem. Con 60 segmentos el coste es despreciable.
        self._segments: list[pg.PlotCurveItem] = []
        colors = color_trail(self._n_segments)
        for i in range(self._n_segments):
            color = QColor(int(colors[i, 0]), int(colors[i, 1]),
                           int(colors[i, 2]), int(colors[i, 3]))
            pen = QPen(color)
            pen.setWidth(2)
            curve = pg.PlotCurveItem(pen=pen)
            self._plot.addItem(curve)
            self._segments.append(curve)

        # Punto que marca la posición instantánea actual ("ahora")
        self._head = pg.ScatterPlotItem(
            size=10,
            pen=pg.mkPen("#ffffff", width=1),
            brush=pg.mkBrush(255, 255, 255, 220),
        )
        self._plot.addItem(self._head)

        # Líneas guía en el origen
        self._plot.addLine(x=0, pen=pg.mkPen(COLOR_PANEL_BORDER, width=1))
        self._plot.addLine(y=0, pen=pg.mkPen(COLOR_PANEL_BORDER, width=1))

        self._range = 0.05
        self._plot.setXRange(-self._range, self._range, padding=0.0)
        self._plot.setYRange(-self._range, self._range, padding=0.0)

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def update_from_snapshot(self, snapshot) -> None:  # BufferSnapshot
        """Pinta los últimos ``window_samples`` de los canales N y E."""

        n = snapshot.samples.get("N")
        e = snapshot.samples.get("E")
        if n is None or e is None or n.size == 0 or e.size == 0:
            return

        # Tomar la cola
        n_window = n[-self._window_samples :]
        e_window = e[-self._window_samples :]

        # Si las longitudes no coinciden (raro), recortar
        n_min = min(n_window.size, e_window.size)
        n_window = n_window[-n_min:]
        e_window = e_window[-n_min:]

        # Distribuir las muestras en n_segments tramos consecutivos.
        # Cada segmento conecta su última muestra con la primera del
        # siguiente para que la curva sea continua.
        if n_min < self._n_segments + 1:
            return

        seg_len = n_min // self._n_segments
        for i, curve in enumerate(self._segments):
            a = i * seg_len
            b = (i + 1) * seg_len + 1  # +1 para "tocar" el siguiente segmento
            b = min(b, n_min)
            curve.setData(e_window[a:b], n_window[a:b])

        # Cabeza brillante: la última muestra
        self._head.setData([float(e_window[-1])], [float(n_window[-1])])

        # Auto-rango simétrico (con suavizado para evitar parpadeos)
        target_range = auto_range(np.concatenate([n_window, e_window]))
        # Suavizado exponencial: nuevo = 0.7·viejo + 0.3·objetivo
        self._range = 0.7 * self._range + 0.3 * target_range
        self._plot.setXRange(-self._range, self._range, padding=0.0)
        self._plot.setYRange(-self._range, self._range, padding=0.0)

    def reset(self) -> None:
        """Limpia la trayectoria."""

        for curve in self._segments:
            curve.clear()
        self._head.clear()
