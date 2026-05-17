"""
Vista tipo "helicorder" (rollo de tambor) — 24 horas en una pantalla.

Convención
----------
* Cada fila representa un intervalo fijo (por defecto 1 hora).
* El ancho del panel se reparte entre las 60 minutos de la fila, igual
  que en los antiguos sismógrafos de papel rotatorio.
* La fila más reciente está abajo (consistente con cómo "cae" el papel).
* Para mostrar un día entero (8.64 millones de muestras a 100 Hz) sin
  saturar la GPU, cada fila se decima a la resolución de pantalla
  conservando la envolvente min/max — así un pico de 5 ms sigue siendo
  visible aunque solo ocupe un píxel.

Almacenamiento
--------------
La fuente de datos siempre llega en bloques de ~10 muestras. El panel
acumula esos bloques en un único ``numpy.ndarray`` circular que cubre
la totalidad de la ventana temporal (≈ 8.64 MB para 24 h × 100 Hz);
es despreciable comparado con el coste de un frame de PyQtGraph.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout, QWidget

from shakevision.ui.theme import (
    COLOR_BACKGROUND,
    COLOR_PANEL_BORDER,
    COLOR_TEXT_SECONDARY,
    WAVEFORM_COLORS,
)


# Resolución horizontal a la que se decima cada fila (≈ ancho típico)
DEFAULT_PIXELS_PER_ROW: int = 1200


# ============================================================
# Helpers puros (testeables sin Qt)
# ============================================================
def envelope_decimate(
    samples: np.ndarray, target_len: int
) -> tuple[np.ndarray, np.ndarray]:
    """Reduce un array a ``target_len`` puntos conservando min/max por bloque.

    Devuelve ``(low, high)``: dos arrays de longitud ``target_len`` con,
    respectivamente, el mínimo y el máximo de cada bloque. Si la entrada
    es más corta que ``target_len``, se devuelve la propia señal en
    ambos canales.
    """

    n = samples.size
    if n == 0:
        empty = np.zeros(target_len, dtype=np.float32)
        return empty, empty.copy()
    if n <= target_len:
        return samples.astype(np.float32), samples.astype(np.float32)

    step = n // target_len
    usable = step * target_len
    chunks = samples[:usable].reshape(target_len, step)
    return chunks.min(axis=1).astype(np.float32), chunks.max(axis=1).astype(np.float32)


# ============================================================
# Búfer largo (no comparte código con RingBuffer porque su semántica es
# diferente: aquí solo nos interesa Z y queremos eficiencia de "agregar").
# ============================================================
class _HelicorderBuffer:
    """Buffer circular de un solo canal pensado para visualización a largo plazo."""

    def __init__(self, capacity_samples: int) -> None:
        self._cap = int(capacity_samples)
        self._data = np.zeros(self._cap, dtype=np.float32)
        self._write_pos = 0
        self._total = 0

    @property
    def total_written(self) -> int:
        return self._total

    @property
    def capacity(self) -> int:
        return self._cap

    def ingest(self, samples: np.ndarray) -> None:
        """Añade un bloque de muestras al final."""

        x = np.ascontiguousarray(samples, dtype=np.float32).reshape(-1)
        if x.size == 0:
            return
        if x.size >= self._cap:
            # Si llega un bloque más grande que el búfer entero, nos
            # quedamos con la cola.
            self._data[:] = x[-self._cap :]
            self._write_pos = 0
            self._total += x.size
            return

        end = self._write_pos + x.size
        if end <= self._cap:
            self._data[self._write_pos : end] = x
        else:
            first = self._cap - self._write_pos
            self._data[self._write_pos :] = x[:first]
            self._data[: end - self._cap] = x[first:]
        self._write_pos = end % self._cap
        self._total += x.size

    def linearized(self) -> np.ndarray:
        """Devuelve un array contiguo con las muestras en orden temporal."""

        if self._total < self._cap:
            return self._data[: self._total].copy()
        # Concatenar [write_pos:] + [:write_pos]
        return np.concatenate([self._data[self._write_pos :], self._data[: self._write_pos]])


# ============================================================
# Panel Qt
# ============================================================
class HelicorderPanel(QFrame):
    """Vista helicorder de 24 h × 1 canal (EHZ por defecto)."""

    def __init__(
        self,
        sample_rate_hz: int = 100,
        hours: int = 24,
        minutes_per_row: int = 60,
        pixels_per_row: int = DEFAULT_PIXELS_PER_ROW,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("WaveformPanel")
        self.setFrameShape(QFrame.NoFrame)

        self._sample_rate = int(sample_rate_hz)
        self._hours = int(hours)
        self._minutes_per_row = int(minutes_per_row)
        self._row_seconds = self._minutes_per_row * 60
        self._row_samples = self._row_seconds * self._sample_rate
        self._n_rows = int(self._hours * 60 // self._minutes_per_row)
        self._pixels_per_row = int(pixels_per_row)

        # Capacidad total: hours × 60 × 60 × sample_rate
        capacity = self._n_rows * self._row_samples
        self._buffer = _HelicorderBuffer(capacity)

        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        header = QLabel(f"Helicorder · EHZ · {hours} h × {minutes_per_row} min/fila")
        header.setObjectName("SectionTitle")
        header.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(header)

        self._plot = pg.PlotWidget(background=COLOR_BACKGROUND)
        self._plot.setMouseEnabled(x=False, y=True)
        self._plot.setMenuEnabled(False)
        self._plot.showGrid(x=True, y=False, alpha=0.10)
        self._plot.getAxis("bottom").setPen(COLOR_PANEL_BORDER)
        self._plot.getAxis("left").setPen(COLOR_PANEL_BORDER)
        self._plot.getAxis("bottom").setTextPen(COLOR_TEXT_SECONDARY)
        self._plot.getAxis("left").setTextPen(COLOR_TEXT_SECONDARY)
        self._plot.setLabel("bottom", f"Minutos en la fila (0 → {minutes_per_row})")
        self._plot.setLabel("left", "Hora (más reciente abajo)")
        self._plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self._plot, stretch=1)

        # Una pareja (low, high) FillBetween por fila — eso da el aspecto
        # de "tira de tinta" típica del helicorder.
        self._fills: list[pg.FillBetweenItem] = []
        for row in range(self._n_rows):
            y_offset = float(self._n_rows - 1 - row)  # fila 0 arriba, última abajo
            x = np.linspace(0, self._minutes_per_row, self._pixels_per_row)
            low_curve = pg.PlotCurveItem(
                x=x, y=np.full_like(x, y_offset, dtype=np.float32)
            )
            high_curve = pg.PlotCurveItem(
                x=x, y=np.full_like(x, y_offset, dtype=np.float32)
            )
            fill = pg.FillBetweenItem(
                low_curve, high_curve, brush=pg.mkBrush(WAVEFORM_COLORS["Z"])
            )
            self._plot.addItem(fill)
            self._fills.append(fill)

        # Configurar el rango Y para que muestre todas las filas alineadas
        self._plot.setYRange(-0.6, self._n_rows - 0.4, padding=0.0)
        self._plot.setXRange(0, self._minutes_per_row, padding=0.0)

        # Etiquetas del eje Y: "00:00", "01:00", ...
        ticks = [
            (self._n_rows - 1 - i, f"{i:02d}:00") for i in range(self._n_rows)
        ]
        self._plot.getAxis("left").setTicks([ticks])

        # Amplitud máxima vista hasta ahora — para normalizar el dibujado.
        self._amp_norm: float = 1.0

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def ingest(self, samples: np.ndarray) -> None:
        """Recibe un nuevo bloque de muestras del canal Z."""

        self._buffer.ingest(samples)

    def refresh(self) -> None:
        """Recalcula y redibuja todas las filas a partir del búfer actual."""

        if self._buffer.total_written == 0:
            return

        flat = self._buffer.linearized()
        # Padding por la izquierda con ceros si aún no hay 24 h de datos
        if flat.size < self._n_rows * self._row_samples:
            pad = np.zeros(self._n_rows * self._row_samples - flat.size, dtype=np.float32)
            flat = np.concatenate([pad, flat])

        # Reshape a (n_rows, row_samples)
        rows = flat.reshape(self._n_rows, self._row_samples)

        # Normalización adaptativa: nos basamos en el percentil 99 del
        # día completo para no dejar que un solo evento sature la pantalla.
        amp = float(np.percentile(np.abs(rows), 99)) or 1e-9
        self._amp_norm = 0.4 / amp  # 0.4 deja un 20 % de margen entre filas

        for row_idx, fill in enumerate(self._fills):
            row = rows[row_idx]
            low, high = envelope_decimate(row, self._pixels_per_row)
            y_offset = float(self._n_rows - 1 - row_idx)
            x = np.linspace(0, self._minutes_per_row, self._pixels_per_row)
            fill.curves[0].setData(x, low * self._amp_norm + y_offset)
            fill.curves[1].setData(x, high * self._amp_norm + y_offset)

    def reset(self) -> None:
        """Limpia el búfer (al cambiar de estación)."""

        self._buffer = _HelicorderBuffer(self._buffer.capacity)
        for fill in self._fills:
            for curve in fill.curves:
                y = curve.yData
                if y is not None:
                    curve.setData(curve.xData, np.full_like(y, float(0)))
