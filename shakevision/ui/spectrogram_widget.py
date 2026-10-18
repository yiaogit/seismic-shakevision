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

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from shakevision.i18n import LocaleService, t
from shakevision.processing.spectrum import (
    SpectrumResult,
    rebin_log_frequency,
)
from shakevision.ui.signal_safety import subscribe
from shakevision.ui.theme import (
    COLOR_BACKGROUND,
)


# Rango dinámico por defecto del mapa de calor (dB)
DEFAULT_DB_MIN: float = -90.0
DEFAULT_DB_MAX: float = -10.0


class _FreqAxisItem(pg.AxisItem):
    """Eje Y de frecuencia con modo lineal o logarítmico.

    En modo log las coordenadas del ``ImageItem`` son ``log10(f)`` (el widget
    re-muestrea la matriz a filas log-espaciadas); aquí solo se generan ticks
    1/2/5×10ⁿ y se formatean como Hz.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._log_mode = False

    def set_log_mode(self, on: bool) -> None:
        self._log_mode = bool(on)
        self.update()

    def tickValues(self, minVal, maxVal, size):  # noqa: N802 (API pyqtgraph)
        if not self._log_mode:
            return super().tickValues(minVal, maxVal, size)
        if (not np.isfinite(minVal) or not np.isfinite(maxVal)
                or maxVal <= minVal):
            return []
        lo, hi = 10.0 ** float(minVal), 10.0 ** float(maxVal)
        vals: list[float] = []
        e0 = int(np.floor(np.log10(lo)))
        e1 = int(np.ceil(np.log10(hi)))
        for exp in range(e0, e1 + 1):
            for mult in (1.0, 2.0, 5.0):
                f = mult * (10.0 ** exp)
                if lo <= f <= hi:
                    vals.append(float(np.log10(f)))
        vals = sorted(set(vals))
        return [(1.0, vals)] if vals else []

    def tickStrings(self, values, scale, spacing):  # noqa: N802
        if not self._log_mode:
            return super().tickStrings(values, scale, spacing)
        out: list[str] = []
        for v in values:
            f = 10.0 ** float(v)
            out.append(f"{f:g}")
        return out


class SpectrogramPanel(QFrame):
    """Mapa de calor tiempo-frecuencia para el canal vertical."""

    #: El usuario cambió la ventana FFT (segundos). El dueño del
    #: SpectrumComputer debe recrearlo y volver a pintar.
    fft_window_changed = Signal(float)

    def __init__(self, parent: Optional[QWidget] = None,
                 absolute_time: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName("WaveformPanel")  # Reutiliza el estilo del panel de ondas
        self.setFrameShape(QFrame.NoFrame)
        # v0.9: 150 px para que la fila de controles (FFT / log) no deje el
        # mapa en una franja donde se corten las etiquetas del eje. En Replay
        # conviven 3 bloques; el splitter reparte el resto con las trazas.
        self.setMinimumHeight(150)

        # v0.8.0: en Replay (estático) el eje X es **hora UTC absoluta** —
        # coincide con el oscilograma; antes mostraba segundos relativos
        # NEGATIVOS (convención del modo en vivo), lo que confundía en histórico.
        self._absolute_time = bool(absolute_time)
        self._channel: str = ""
        self._log_freq: bool = False
        self._last_spectrum: Optional[SpectrumResult] = None
        self._last_t0_abs: Optional[float] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 18, 6)
        layout.setSpacing(6)

        # Cabecera + controles (i18n-aware)
        self._header = QLabel(t("spectrogram.title"))
        self._header.setObjectName("SectionTitle")
        self._header.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(6)
        header_row.addWidget(self._header)
        header_row.addStretch(1)

        self._fft_label = QLabel(t("spectrogram.fft_window"))
        self._fft_label.setObjectName("Caption")
        header_row.addWidget(self._fft_label)
        self._fft_combo = QComboBox()
        for seconds in (0.5, 1.0, 2.0, 4.0):
            self._fft_combo.addItem(f"{seconds:g} s", seconds)
        self._fft_combo.setCurrentIndex(1)     # 1 s por defecto
        self._fft_combo.setFixedHeight(22)
        self._fft_combo.currentIndexChanged.connect(
            self._on_fft_window_changed)
        # El QSS global de QComboBox impone ~30 px de alto; en esta cabecera
        # compacta lo bajamos a 22 para no comerse el mapa.
        self._fft_combo.setStyleSheet(
            "QComboBox { min-height: 0px; max-height: 22px;"
            " padding: 0px 20px 0px 8px; }")
        header_row.addWidget(self._fft_combo)

        self._log_btn = QPushButton(t("spectrogram.log_freq"))
        self._log_btn.setObjectName("ChipButton")
        self._log_btn.setCheckable(True)
        self._log_btn.setFixedHeight(22)
        self._log_btn.toggled.connect(self._on_log_toggled)
        header_row.addWidget(self._log_btn)
        layout.addLayout(header_row)

        # PlotWidget contenedor — v0.6 P11: theme-aware
        self._freq_axis = _FreqAxisItem(orientation="left")
        if self._absolute_time:
            from shakevision.ui.waveform_widget import _UTCAxisItem
            self._plot = pg.PlotWidget(
                background=COLOR_BACKGROUND,
                axisItems={"bottom": _UTCAxisItem(orientation="bottom"),
                           "left": self._freq_axis})
            # Sin esto pyqtgraph añade "(x1e+09)" al eje de epoch Unix.
            self._plot.getAxis("bottom").enableAutoSIPrefix(False)
        else:
            self._plot = pg.PlotWidget(
                background=COLOR_BACKGROUND,
                axisItems={"left": self._freq_axis})
        self._plot.setMouseEnabled(x=True, y=False)
        self._plot.setMenuEnabled(False)
        self._plot.showGrid(x=True, y=True, alpha=0.10)
        self._plot.setLabel("bottom", self._time_axis_label())
        self._plot.setLabel("left", self._axis_freq_label())
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
            # Etiquetas del colorbar más pequeñas: en Replay el panel mide
            # ~140 px y con 6-7 ticks el texto se solapaba.
            try:
                from PySide6.QtGui import QFont
                cb_axis = getattr(self._colorbar, "axis", None)
                if cb_axis is not None:
                    tick_font = QFont(cb_axis.tickFont())
                    tick_font.setPointSize(8)
                    cb_axis.setTickFont(tick_font)
                    # 45 px (default) recorta etiquetas como "-120"; 58 deja
                    # sitio a 3-4 cifras sin comerse el mapa.
                    cb_axis.setWidth(58)
                    self._sync_colorbar_ticks(
                        DEFAULT_DB_MIN, DEFAULT_DB_MAX)
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            self._colorbar = None

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def _time_axis_label(self) -> str:
        return t("spectrogram.axis_time_utc" if self._absolute_time
                 else "spectrogram.axis_time")

    def _axis_freq_label(self) -> str:
        return t("spectrogram.axis_freq_log" if self._log_freq
                 else "spectrogram.axis_freq")

    def _sync_colorbar_ticks(self, lo: float, hi: float) -> None:
        """Reduce el colorbar a 4 etiquetas: con 150 px, los 6-7 ticks
        automáticos se solapaban verticalmente en Replay."""

        if self._colorbar is None or hi <= lo:
            return
        try:
            values = [lo + (hi - lo) * i / 3.0 for i in range(4)]
            self._colorbar.axis.setTicks(
                [[(v, f"{v:.0f}") for v in values]])
        except Exception:  # noqa: BLE001
            pass

    def set_channel(self, channel: str) -> None:
        """Fija el canal mostrado en la cabecera (p. ej. ``BHZ``). Antes el
        canal estaba HARDCODEADO ("EHZ") en la cadena i18n, lo que era erróneo
        para estaciones de banda ancha (BH…)."""

        self._channel = (channel or "").strip()
        self._apply_header()

    def _apply_header(self) -> None:
        base = t("spectrogram.title")
        self._header.setText(f"{base} ({self._channel})" if self._channel
                             else base)

    # ── Ventana FFT ────────────────────────────────────────────────
    def fft_window_seconds(self) -> float:
        """Ventana FFT seleccionada por el usuario (segundos)."""

        return float(self._fft_combo.currentData() or 1.0)

    def set_fft_window_seconds(self, seconds: float) -> None:
        idx = self._fft_combo.findData(float(seconds))
        if idx >= 0:
            self._fft_combo.setCurrentIndex(idx)

    def _on_fft_window_changed(self, _idx: int) -> None:
        self.fft_window_changed.emit(self.fft_window_seconds())

    # ── Eje logarítmico ───────────────────────────────────────────
    def is_log_frequency(self) -> bool:
        return self._log_freq

    def set_log_frequency(self, on: bool) -> None:
        on = bool(on)
        self._log_freq = on
        self._log_btn.blockSignals(True)
        self._log_btn.setChecked(on)
        self._log_btn.blockSignals(False)
        self._freq_axis.set_log_mode(on)
        self._plot.setLabel("left", self._axis_freq_label())
        self._redraw_spectrum()

    def _on_log_toggled(self, on: bool) -> None:
        self.set_log_frequency(on)

    def _retranslate(self) -> None:
        """Re-aplica labels traducidos al cambiar idioma."""

        self._apply_header()
        self._fft_label.setText(t("spectrogram.fft_window"))
        self._log_btn.setText(t("spectrogram.log_freq"))
        self._plot.setLabel("bottom", self._time_axis_label())
        self._plot.setLabel("left", self._axis_freq_label())

    def update_from_spectrum(self, spectrum: SpectrumResult,
                             t0_abs: Optional[float] = None) -> None:
        """Refresca el mapa de calor con un nuevo ``SpectrumResult``.

        Si ``t0_abs`` (epoch UTC del inicio de la ventana) se da, el eje X pasa
        a hora absoluta: los tiempos relativos se desplazan para que el primer
        bin caiga en ``t0_abs`` (alineado con el oscilograma)."""

        if spectrum.power_db.size == 0:
            return
        self._last_spectrum = spectrum
        self._last_t0_abs = t0_abs
        self._redraw_spectrum()

    def _redraw_spectrum(self) -> None:
        """Pinta el último espectro con el eje/ventana actuales."""

        spec = self._last_spectrum
        if spec is None or spec.power_db.size == 0:
            return

        t_first = float(spec.times[0])
        offset = ((float(self._last_t0_abs) - t_first)
                  if self._last_t0_abs is not None else 0.0)
        x0 = t_first + offset
        x1 = (float(spec.times[-1]) + offset
              if spec.times.size > 1 else x0 + 1.0)

        power = spec.power_db
        if self._log_freq:
            log_f, power = rebin_log_frequency(
                spec.freqs, spec.power_db, n_bins=256)
            if log_f.size < 2:
                return
            y0 = float(np.log10(log_f[0]))
            y1 = float(np.log10(log_f[-1]))
        else:
            y0 = float(spec.freqs[0])
            y1 = float(spec.freqs[-1])

        self._image.setImage(
            power,
            autoLevels=False,
            autoDownsample=True,
        )
        # En Replay (estático) el rango fijo -90/-10 dB saturaba la imagen con
        # eventos grandes (M7.7 a 7.7°: cientos de miles de counts → >100 dB,
        # todo amarillo). Ajustar el rango al propio dato en cada refresh; el
        # usuario puede seguir moviendo la barra de color después.
        if self._absolute_time:
            finite = power[np.isfinite(power)]
            if finite.size:
                lo = float(np.percentile(finite, 2.0))
                hi = float(np.percentile(finite, 99.5))
                if hi - lo < 12.0:
                    hi = lo + 12.0
                self._image.setLevels((lo, hi))
                if self._colorbar is not None:
                    try:
                        self._colorbar.setLevels((lo, hi))
                        self._sync_colorbar_ticks(lo, hi)
                    except Exception:  # noqa: BLE001
                        pass
        self._image.setRect(x0, y0, x1 - x0, y1 - y0)

        # Fijar el rango visible para que coincida con el oscilograma
        self._plot.setXRange(x0, x1, padding=0.0)
        self._plot.setYRange(y0, y1, padding=0.0)

    def reset(self) -> None:
        """Limpia el mapa (se llama al cambiar de estación)."""

        self._last_spectrum = None
        self._last_t0_abs = None
        self._image.clear()

    def set_db_range(self, db_min: float, db_max: float) -> None:
        """Permite al usuario ajustar el rango dinámico mostrado."""

        if db_min >= db_max:
            return
        self._image.setLevels((db_min, db_max))
        if self._colorbar is not None:
            try:
                self._colorbar.setLevels((db_min, db_max))
                self._sync_colorbar_ticks(db_min, db_max)
            except Exception:  # noqa: BLE001
                pass
