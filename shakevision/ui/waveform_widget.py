"""
Panel de forma de onda (3 canales) con barra de herramientas de análisis.

v0.7.7 — reestructuración UI: las acciones de análisis viven AHORA en una
barra encima de las trazas (patrón SWARM/Snuffler), no en el panel lateral.
Incluye:
  * Congelar — detiene el scroll para inspeccionar el búfer.
  * m/s — quita la respuesta instrumental (la sensibilidad la obtiene el
    controlador; el panel solo emite ``units_requested``).
  * P / S — coloca pickers de fase arrastrables (al hacer clic sobre la
    traza Z, en modo congelado); el readout calcula S-P → distancia → ML.
  * Cursor en cruz + región arrastrable (pico / RMS / frecuencia dominante).

Una sola línea de readout (monoespaciada) concentra cursor, región y picks.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from shakevision.i18n import LocaleService, t
from shakevision.processing import measurements as _meas
from shakevision.processing.buffer import BufferSnapshot
from shakevision.services.response import (
    counts_to_velocity,
    scale_velocity_units,
)
from shakevision.ui.signal_safety import subscribe
from shakevision.ui.theme import (
    COLOR_BACKGROUND,
    WAVEFORM_COLORS,
)

_CHANNELS: list[str] = ["Z", "N", "E"]


class _UTCAxisItem(pg.AxisItem):
    """Eje X que formatea valores (segundos Unix) como **hora UTC**.

    Determinista e independiente de la versión de pyqtgraph (no usa
    ``DateAxisItem``, cuya zona horaria varía entre versiones). El nivel de
    detalle se adapta al espaciado de ticks: fecha para >1 día, HH:MM para
    >1 min, HH:MM:SS si no.
    """

    def tickStrings(self, values, scale, spacing):  # noqa: N802 (firma Qt)
        out: list[str] = []
        for v in values:
            try:
                dt = datetime.fromtimestamp(float(v), tz=timezone.utc)
            except (OSError, OverflowError, ValueError):
                out.append("")
                continue
            if spacing >= 86400:
                out.append(dt.strftime("%m-%d"))
            elif spacing >= 60:
                out.append(dt.strftime("%H:%M"))
            else:
                out.append(dt.strftime("%H:%M:%S"))
        return out


def _build_plot_widget(channel: str) -> pg.PlotWidget:
    plot = pg.PlotWidget(background=COLOR_BACKGROUND)
    plot.setMouseEnabled(x=True, y=False)
    plot.setMenuEnabled(False)
    plot.showGrid(x=True, y=True, alpha=0.15)
    plot.setLabel("left", f"EH{channel}")
    plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    from shakevision.ui.pg_theming import subscribe_pg_plot
    subscribe_pg_plot(plot)
    return plot


class WaveformPanel(QFrame):
    """Tres trazas apiladas (Z, N, E) + barra y readout de análisis."""

    #: El usuario pidió cambiar de unidades; el controlador obtiene la
    #: sensibilidad (red) y llama de vuelta a ``set_units``.
    units_requested = Signal(bool)
    #: La región (caja amarilla) cambió → recalcular PSD del tramo. v0.7.7.
    region_changed = Signal()

    def __init__(self, parent: QWidget | None = None,
                 show_detector_tools: bool = True,
                 static_mode: bool = False,
                 show_units_button: bool = True) -> None:
        super().__init__(parent)
        self.setObjectName("WaveformPanel")
        self.setFrameShape(QFrame.NoFrame)
        # v0.7.7: en Replay no hay detector STA/LTA en vivo, así que se
        # ocultan cft + ⚡ (auto-análisis). El resto del análisis (congelar,
        # cursor, región, picks, unidades) sí aplica a datos históricos.
        self._show_detector_tools = show_detector_tools
        # v0.7.7: modo "navegador estático" (Replay reescrito). En lugar de
        # hacer scroll en vivo, se carga TODA la traza de una vez y se navega
        # con zoom/pan del ratón. Las herramientas de análisis están SIEMPRE
        # activas (no hay "congelar"), el eje X es hora UTC absoluta, y el
        # botón ⟲ ajusta a toda la traza.
        self._static_mode = static_mode
        self._show_units_button = show_units_button
        # v0.7.7: cuando NO es None (p. ej. "m/s", "m", "m/s²"), las muestras
        # YA vienen en unidades físicas (deconvolución completa hecha fuera):
        # _display las pinta tal cual y _fmt_amp/eje usan esa unidad. Es
        # independiente del path escalar set_units (que sigue para el Live).
        self._amp_unit_override: Optional[str] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ── Cabecera: estación + barra de herramientas de análisis ──
        self._station_text: str = "—"
        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        self.station_header = QLabel(t("waveform.station_label", label="—"))
        self.station_header.setObjectName("SectionTitle")
        self.station_header.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header_row.addWidget(self.station_header)
        header_row.addStretch(1)
        # v0.7.7: lectura del cursor (tiempo + amplitud bajo el ratón). Estilo
        # SWARM/Snuffler: el valor del dato se muestra al pasar por encima.
        self._cursor_label = QLabel("")
        self._cursor_label.setObjectName("StatusValue")
        self._cursor_label.setStyleSheet("font-family: monospace; font-size: 11px;")
        self._cursor_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        header_row.addWidget(self._cursor_label)
        header_row.addSpacing(8)
        header_row.addWidget(self._build_toolbar())
        layout.addLayout(header_row)

        # ── Trazas ──
        self._plots: dict[str, pg.PlotWidget] = {}
        self._curves: dict[str, pg.PlotDataItem] = {}
        for channel in _CHANNELS:
            plot = _build_plot_widget(channel)
            curve = plot.plot(pen=pg.mkPen(WAVEFORM_COLORS[channel], width=1.2))
            self._plots[channel] = plot
            self._curves[channel] = curve
            layout.addWidget(plot, stretch=1)

        for channel in _CHANNELS[1:]:
            self._plots[channel].setXLink(self._plots[_CHANNELS[0]])
        if self._static_mode:
            # Eje X = hora UTC absoluta en la traza inferior (la que muestra
            # valores). Hay que ponerlo ANTES de setLabel/showValues abajo.
            self._plots[_CHANNELS[-1]].setAxisItems(
                {"bottom": _UTCAxisItem(orientation="bottom")})
            # Desactivar el prefijo SI automático: los valores son segundos
            # Unix (~1.7e9), y pyqtgraph mostraba un "(x1e+09)" sin sentido.
            self._plots[_CHANNELS[-1]].getAxis("bottom").enableAutoSIPrefix(False)
        self._plots[_CHANNELS[-1]].setLabel("bottom", self._axis_time_label())
        for channel in _CHANNELS[:-1]:
            self._plots[channel].getAxis("bottom").setStyle(showValues=False)
        for plot in self._plots.values():
            plot.setYRange(-2.0, 2.0, padding=0.0)

        # ── Etiquetas del eje izquierdo por canal ──
        # v0.7.7: configurables (antes "EH{ch}" fijo). Replay las pone según
        # la banda real (BHZ/BHN/BHE) y, al rotar, a Z/R/T.
        self._chan_labels: dict[str, str] = {"Z": "EHZ", "N": "EHN", "E": "EHE"}

        # ── Estado del modo análisis ──
        self._frozen = False
        self._units = "counts"
        self._sensitivity: Optional[float] = None
        self._last_snapshot: Optional[BufferSnapshot] = None
        self._sample_rate_hz = 100.0
        # v0.7.7: cada pick es una lista de 3 líneas (una por traza Z/N/E),
        # sincronizadas — así S se puede situar mirando las horizontales.
        self._picks: dict[str, list[pg.InfiniteLine]] = {}
        self._syncing = False
        self._trigger_lines: list[pg.InfiniteLine] = []
        # v0.7.7: marcadores de llegada TEÓRICA (TauP) en modo estático —
        # lista de (canal, línea) para poder limpiarlos.
        self._phase_markers: list[tuple[str, pg.InfiniteLine]] = []
        self._cft_over: Optional[bool] = None
        self._build_analysis_items()

        # ── Readout (oculto fuera del modo análisis) ──
        self._readout = QLabel("")
        self._readout.setObjectName("StatusValue")
        self._readout.setWordWrap(True)
        self._readout.setVisible(False)
        layout.addWidget(self._readout)

        # v0.7.7 fix: aplicar textos/tooltips iniciales (el botón Congelar se
        # quedaba en blanco hasta el primer cambio de idioma).
        self._retranslate()
        subscribe(self, LocaleService.language_changed_signal(),
                  self._retranslate)

    # ------------------------------------------------------------------
    # Barra de herramientas + items del modo análisis
    # ------------------------------------------------------------------
    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)

        def _btn(text, checkable=False, tip="") -> QPushButton:
            b = QPushButton(text)
            b.setObjectName("ToolbarButton")
            b.setCheckable(checkable)
            b.setToolTip(tip)
            b.setFixedHeight(24)
            row.addWidget(b)
            return b

        self._freeze_btn = _btn("", checkable=True)
        self._freeze_btn.toggled.connect(self.set_frozen)
        self._units_btn = _btn("m/s", checkable=True)
        self._units_btn.toggled.connect(self.units_requested.emit)
        self._pick_p_btn = _btn("P")
        self._pick_p_btn.clicked.connect(lambda: self._add_pick("P"))
        self._pick_s_btn = _btn("S")
        self._pick_s_btn.clicked.connect(lambda: self._add_pick("S"))
        self._clear_btn = _btn("✕")
        self._clear_btn.clicked.connect(self._clear_picks)
        self._reset_btn = _btn("⟲")
        self._reset_btn.clicked.connect(self._reset_zoom)

        # v0.7.7: puente detector → análisis. "Auto" = auto-congelar al
        # disparar el STA/LTA; cft = lectura en vivo del ratio.
        self._auto_btn = _btn("", checkable=True)
        self._cft_label = QLabel("cft —")
        self._cft_label.setObjectName("StatusValue")
        self._cft_label.setStyleSheet("font-family: monospace; font-size: 11px;")
        row.addWidget(self._cft_label)
        if not self._show_detector_tools:
            self._auto_btn.setVisible(False)
            self._cft_label.setVisible(False)
        if self._static_mode:
            # En modo estático no existe "congelar" (la traza ya está quieta):
            # las herramientas de análisis están siempre activas.
            self._freeze_btn.setVisible(False)
        if not self._show_units_button:
            # Replay usa su propio selector de salida (counts/VEL/DISP/ACC).
            self._units_btn.setVisible(False)
        return bar

    def _build_analysis_items(self) -> None:
        # v0.7.7: la región de selección (caja amarilla) y el crosshair se
        # crean en LAS TRES trazas, sincronizados — antes solo en Z, por eso
        # la caja "solo afectaba a BHZ" visualmente. El crosshair además ahora
        # se engancha al dato (snap) y muestra tiempo+amplitud (cursor_label).
        self._regions: dict[str, pg.LinearRegionItem] = {}
        self._vlines: dict[str, pg.InfiniteLine] = {}
        self._hlines: dict[str, pg.InfiniteLine] = {}
        self._mouse_proxies: list = []
        self._syncing_region = False
        pen = pg.mkPen((150, 150, 150), width=1, style=Qt.DashLine)

        for ch in _CHANNELS:
            plot = self._plots[ch]
            region = pg.LinearRegionItem(
                values=(-5.0, -1.0),
                brush=pg.mkBrush(120, 160, 255, 40),
                hoverBrush=pg.mkBrush(120, 160, 255, 70))
            region.setZValue(10)
            region.setVisible(False)
            plot.addItem(region)
            # sigRegionChanged emite el propio region como argumento: lo
            # absorbemos con *_a para que ``src_ch`` conserve su valor por
            # defecto (si no, src_ch = el region y KeyError → no se actualiza
            # la lectura: ese era el bug de "el cuadro amarillo no muestra
            # datos").
            region.sigRegionChanged.connect(
                lambda *_a, src_ch=ch: self._on_region_changed(src_ch))
            self._regions[ch] = region

            vline = pg.InfiniteLine(angle=90, movable=False, pen=pen)
            hline = pg.InfiniteLine(angle=0, movable=False, pen=pen)
            vline.setVisible(False)
            hline.setVisible(False)
            plot.addItem(vline, ignoreBounds=True)
            plot.addItem(hline, ignoreBounds=True)
            self._vlines[ch] = vline
            self._hlines[ch] = hline

            self._mouse_proxies.append(pg.SignalProxy(
                plot.scene().sigMouseMoved, rateLimit=60,
                slot=lambda evt, c=ch: self._on_mouse_moved(evt, c)))

    def _on_region_changed(self, src_ch: str) -> None:
        """Sincroniza las 3 cajas de región a la del que se arrastró."""

        if self._syncing_region:
            return
        self._syncing_region = True
        try:
            x0, x1 = self._regions[src_ch].getRegion()
            for ch, region in self._regions.items():
                if ch != src_ch:
                    region.setRegion((x0, x1))
        finally:
            # Pase lo que pase, NO dejar la bandera atascada (si no, ninguna
            # selección posterior se sincronizaría ni actualizaría la lectura).
            self._syncing_region = False
        self._update_readout()

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def set_station_label(self, label: str) -> None:
        self._station_text = label
        self.station_header.setText(t("waveform.station_label", label=label))

    def set_frozen(self, frozen: bool) -> None:
        # En modo estático las herramientas de análisis están SIEMPRE activas:
        # ignoramos cualquier intento de "descongelar".
        if self._static_mode:
            frozen = True
        self._frozen = bool(frozen)
        if self._freeze_btn.isChecked() != self._frozen:
            self._freeze_btn.setChecked(self._frozen)
        for region in self._regions.values():
            region.setVisible(self._frozen)
        self._readout.setVisible(self._frozen)
        for lines in self._picks.values():
            for ln in lines:
                ln.setVisible(self._frozen)
        if self._frozen:
            self._update_readout()
        else:
            self._hide_crosshair()
            self._cursor_label.clear()
            self._readout.clear()
            self._clear_trigger_marker()

    def _hide_crosshair(self) -> None:
        for ln in self._vlines.values():
            ln.setVisible(False)
        for ln in self._hlines.values():
            ln.setVisible(False)

    def set_units(self, use_velocity: bool,
                  sensitivity_counts_per_m_s: Optional[float] = None) -> None:
        if use_velocity and sensitivity_counts_per_m_s:
            self._units = "vel"
            self._sensitivity = float(sensitivity_counts_per_m_s)
        else:
            self._units = "counts"
            if not use_velocity and self._units_btn.isChecked():
                self._units_btn.setChecked(False)
        self._apply_axis_units()
        if self._last_snapshot is not None:
            self._redraw(self._last_snapshot)
        if self._frozen:
            self._update_readout()

    def is_frozen(self) -> bool:
        return self._frozen

    def selected_segment(self, channel: str = "Z"):
        """Muestras (en unidades mostradas) del tramo seleccionado + fs.

        Devuelve ``(samples, fs)`` o ``(None, fs)`` si no hay selección/datos.
        Lo usa el panel PSD para calcular el espectro del tramo amarillo.
        """

        fs = float(self._sample_rate_hz)
        snap = self._last_snapshot
        if snap is None or not snap.times.size:
            return None, fs
        x0, x1 = self._regions[_CHANNELS[0]].getRegion()
        mask = ((snap.times >= min(x0, x1)) & (snap.times <= max(x0, x1)))
        s = snap.samples.get(channel)
        if s is None or s.size == 0 or not mask.any():
            return None, fs
        return self._display(s[mask]), fs

    def get_picks(self) -> dict[str, float]:
        """Devuelve ``{fase: tiempo}`` de los picks manuales colocados.

        En modo estático el tiempo es Unix absoluto (eje X = UTC); en vivo es
        relativo. Lo usa Replay para exportar QuakeML.
        """

        return {ph: float(lines[0].value())
                for ph, lines in self._picks.items() if lines}

    # ------------------------------------------------------------------
    # Datos en vivo
    # ------------------------------------------------------------------
    def update_from_snapshot(self, snapshot: BufferSnapshot) -> None:
        if snapshot.times.size >= 2:
            dt = float(snapshot.times[1] - snapshot.times[0])
            if dt > 0:
                self._sample_rate_hz = 1.0 / dt
        # v0.7.7 fix: en modo congelado NO actualizamos la instantánea de
        # medida — si no, el readout mediría los datos nuevos que siguen
        # llegando por debajo, no la traza congelada que ve el usuario.
        if self._frozen:
            return
        self._last_snapshot = snapshot
        self._redraw(snapshot)

    def _redraw(self, snapshot: BufferSnapshot) -> None:
        times = snapshot.times
        for channel in _CHANNELS:
            samples = snapshot.samples.get(channel)
            if samples is None or samples.size == 0:
                continue
            self._curves[channel].setData(times, self._display(samples))
        # En modo estático NO refijamos el rango X en cada redibujado (p. ej.
        # al cambiar de unidades): así se conserva el zoom/pan del usuario.
        # El ajuste a toda la traza se hace explícitamente con fit_all().
        if times.size and not self._static_mode:
            self._plots[_CHANNELS[0]].setXRange(
                float(times[0]), float(times[-1]), padding=0.0)

    def load_static(self, z, n, e, start_ts: float,
                    sample_rate_hz: float) -> None:
        """Carga TODA la traza histórica de una vez (navegador estático).

        ``z/n/e`` son arrays (o ``None``); ``start_ts`` es el instante Unix de
        la primera muestra. El eje X resultante es tiempo Unix absoluto, que
        ``_UTCAxisItem`` formatea como hora UTC. A diferencia del modo en vivo,
        esto ignora el guard de "congelado" porque la traza está quieta y el
        análisis (región/cursor/picks/medidas) debe estar disponible ya.
        """

        sr = float(sample_rate_hz) or 100.0
        self._sample_rate_hz = sr
        n_samples = max(
            (len(a) for a in (z, n, e) if a is not None), default=0)
        if n_samples == 0:
            return
        times = float(start_ts) + np.arange(n_samples, dtype=np.float64) / sr

        def _fit(a) -> np.ndarray:
            if a is None or len(a) == 0:
                return np.zeros(n_samples, dtype=np.float32)
            a = np.asarray(a, dtype=np.float32)
            if a.size < n_samples:
                out = np.zeros(n_samples, dtype=np.float32)
                out[: a.size] = a
                return out
            return a[:n_samples]

        # ¿Es la MISMA ventana temporal que ya estaba cargada? (re-render por
        # cambio de filtro / rotación / salida → mismos times). En ese caso
        # CONSERVAMOS el zoom y la selección del usuario; solo en una carga
        # nueva (otra descarga) reseteamos la vista y la región por defecto.
        prev = self._last_snapshot
        same_window = (
            prev is not None and prev.times.size == times.size
            and abs(float(prev.times[0]) - float(times[0])) < 1e-6
            and abs(float(prev.times[-1]) - float(times[-1])) < 1e-6)

        snap = BufferSnapshot(
            times=times,
            samples={"Z": _fit(z), "N": _fit(n), "E": _fit(e)},
            latest_timestamp_unix=float(times[-1]),
        )
        self._last_snapshot = snap
        self._frozen = True               # análisis siempre activo en estático
        self._clear_phase_markers()       # llegadas teóricas de la carga previa
        self._redraw(snap)
        self._readout.setVisible(True)
        if same_window:
            # Mantener zoom + región tal como los dejó el usuario.
            self._update_readout()
            return
        # Carga nueva: ajustar a toda la traza + región inicial (las 3).
        self.fit_all()
        span = float(times[-1] - times[0]) or 1.0
        self._syncing_region = True
        for region in self._regions.values():
            region.setRegion((times[0] + 0.05 * span, times[0] + 0.15 * span))
            region.setVisible(True)
        self._syncing_region = False
        self._update_readout()

    def set_phase_markers(self, arrivals: list[tuple[str, float, str]]) -> None:
        """Dibuja líneas verticales de llegada TEÓRICA (TauP) en las 3 trazas.

        ``arrivals`` es una lista de ``(etiqueta, tiempo_unix, color_hex)``.
        Sustituye cualquier marcador previo. Estilo punteado para
        distinguirlas de los picks manuales (línea continua).
        """

        self._clear_phase_markers()
        for label, x, color in arrivals:
            for i, ch in enumerate(_CHANNELS):
                ln = pg.InfiniteLine(
                    pos=float(x), angle=90, movable=False,
                    pen=pg.mkPen(color, width=1.2, style=Qt.DashLine),
                    label=(label if i == 0 else None),
                    labelOpts={"position": 0.85, "color": color})
                ln.setZValue(12)
                # ignoreBounds: que NO afecten al auto-rango (si una llegada
                # cae fuera de la traza no debe estirar la vista).
                self._plots[ch].addItem(ln, ignoreBounds=True)
                self._phase_markers.append((ch, ln))

    def _clear_phase_markers(self) -> None:
        for ch, ln in self._phase_markers:
            self._plots[ch].removeItem(ln)
        self._phase_markers = []

    def fit_all(self) -> None:
        """Ajusta la vista a TODA la traza (X completo + autoescala Y)."""

        snap = self._last_snapshot
        if snap is None or not snap.times.size:
            return
        self._plots[_CHANNELS[0]].setXRange(
            float(snap.times[0]), float(snap.times[-1]), padding=0.0)
        for plot in self._plots.values():
            plot.enableAutoRange(axis="y")

    def update_channel(self, channel: str, samples: np.ndarray) -> None:
        curve = self._curves.get(channel)
        if curve is not None:
            curve.setData(self._display(samples))

    def reset(self) -> None:
        """Limpia TODO el estado de visualización y análisis (al desconectar):
        trazas, picks, marcador de trigger, modo congelado, unidades y cft."""

        self._last_snapshot = None
        self.set_frozen(False)            # salir del modo análisis
        self.set_units(False)             # volver a counts (sensibilidad obsoleta)
        for curve in self._curves.values():
            curve.clear()
        self._clear_picks()
        self._clear_trigger_marker()
        self._clear_phase_markers()
        self._hide_crosshair()
        self._cursor_label.clear()
        self._amp_unit_override = None
        self._readout.clear()
        self._cft_over = None
        self._cft_label.setText("cft —")
        self._cft_label.setStyleSheet("font-family: monospace; font-size: 11px;")

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------
    def set_amp_unit_override(self, unit: Optional[str]) -> None:
        """Activa (unit "m/s"/"m"/"m/s²") o desactiva (None) el modo de unidades
        físicas externas. Las muestras ya deben venir convertidas (deconvolución
        completa hecha fuera). Independiente del path escalar set_units."""

        self._amp_unit_override = unit
        self._apply_axis_units()
        if self._last_snapshot is not None:
            self._redraw(self._last_snapshot)
        if self._frozen:
            self._update_readout()

    def _is_velocity(self) -> bool:
        """¿Las trazas representan velocidad? (escalar m/s o deconv "m/s")."""

        return self._units == "vel" or self._amp_unit_override == "m/s"

    def _display(self, samples: np.ndarray) -> np.ndarray:
        if self._amp_unit_override is not None:
            return samples                       # ya en unidades físicas
        if self._units == "vel" and self._sensitivity:
            return counts_to_velocity(samples, self._sensitivity)
        return samples

    def set_channel_labels(self, z_label: str, n_label: str,
                           e_label: str) -> None:
        """Fija las etiquetas del eje izquierdo (p. ej. banda real BHZ/BHN/BHE
        o, tras rotar, Z/R/T). Reaplica el sufijo de unidades vigente."""

        self._chan_labels = {"Z": z_label, "N": n_label, "E": e_label}
        self._apply_axis_units()

    def _apply_axis_units(self) -> None:
        if self._amp_unit_override is not None:
            suffix = f" ({self._amp_unit_override})"
        elif self._units == "vel":
            suffix = " (m/s)"
        else:
            suffix = ""
        for ch in _CHANNELS:
            self._plots[ch].setLabel("left", f"{self._chan_labels[ch]}{suffix}")

    @staticmethod
    def _fmt_si(value: float, unit: str) -> str:
        """Formatea ``value`` con prefijo métrico (n/µ/m) para ``unit``."""

        v = abs(value)
        if v == 0.0:
            return f"0 {unit}"
        if v < 1e-6:
            return f"{value * 1e9:.3g} n{unit}"
        if v < 1e-3:
            return f"{value * 1e6:.3g} µ{unit}"
        if v < 1.0:
            return f"{value * 1e3:.3g} m{unit}"
        return f"{value:.3g} {unit}"

    def _fmt_amp(self, value_display: float) -> str:
        if self._amp_unit_override is not None:
            return self._fmt_si(value_display, self._amp_unit_override)
        if self._units == "vel":
            v, u = scale_velocity_units(value_display)
            return f"{v:.3g} {u}"
        # counts: enteros con separador de miles si son grandes (BHZ ~1e4),
        # 3 cifras significativas si son pequeños (Demo ~±1).
        if abs(value_display) >= 100:
            return f"{value_display:,.0f} counts"
        return f"{value_display:.3g} counts"

    def _on_mouse_moved(self, evt, ch: str) -> None:
        """Crosshair enganchado al dato (snap) + lectura tiempo/amplitud.

        ``ch`` es la traza sobre la que se mueve el ratón. La línea vertical se
        sincroniza en las 3 trazas (mismo X); la horizontal solo en la activa.
        """

        if not self._frozen:
            return
        plot = self._plots[ch]
        pos = evt[0]
        if not plot.sceneBoundingRect().contains(pos):
            self._hide_crosshair()
            self._cursor_label.clear()
            return
        pt = plot.getViewBox().mapSceneToView(pos)

        # Snap: enganchar X a la muestra más cercana y leer su amplitud real.
        snap = self._last_snapshot
        x = pt.x()
        amp_txt = ""
        if snap is not None and snap.times.size:
            idx = int(np.searchsorted(snap.times, x))
            idx = max(0, min(snap.times.size - 1, idx))
            # Afinar al vecino más cercano (searchsorted da el de la derecha).
            if 0 < idx < snap.times.size and (
                    abs(snap.times[idx - 1] - x) < abs(snap.times[idx] - x)):
                idx -= 1
            x = float(snap.times[idx])
            samp = snap.samples.get(ch)
            if samp is not None and idx < samp.size:
                amp_txt = self._fmt_amp(self._display(samp[idx:idx + 1])[0])

        # Vertical sincronizada en las 3; horizontal solo en la activa.
        for c, ln in self._vlines.items():
            ln.setPos(x)
            ln.setVisible(True)
        for c, ln in self._hlines.items():
            if c == ch:
                ln.setPos(pt.y())
                ln.setVisible(True)
            else:
                ln.setVisible(False)

        self._cursor_label.setText(
            f"{self._fmt_cursor_time(x)}   {self._chan_labels[ch]}: {amp_txt}")

    def _fmt_cursor_time(self, x: float) -> str:
        """Tiempo del cursor: hora UTC (estático) o segundos (en vivo)."""

        if self._static_mode:
            try:
                return datetime.fromtimestamp(
                    x, tz=timezone.utc).strftime("%H:%M:%S.%f")[:-3] + "Z"
            except (OSError, OverflowError, ValueError):
                return ""
        return f"{x:.3f} s"

    def _add_pick(self, phase: str) -> None:
        """Coloca (o recoloca) un picker en el centro de la vista actual.

        Auto-congela si hace falta; el picker es arrastrable, así que el
        usuario lo lleva a la llegada exacta. Un clic, sin segundo clic
        sobre la traza (mucho más descubrible y robusto)."""

        if not self._frozen:
            self.set_frozen(True)
        top = self._plots[_CHANNELS[0]]
        (x0, x1) = top.getViewBox().viewRange()[0]
        self._place_pick(phase, float((x0 + x1) / 2.0))

    def _place_pick(self, phase: str, x: float) -> None:
        color = "#3b9aff" if phase == "P" else "#ff8c42"
        if phase in self._picks:
            for ln in self._picks[phase]:
                ln.setPos(x)
        else:
            lines: list[pg.InfiniteLine] = []
            for i, ch in enumerate(_CHANNELS):
                ln = pg.InfiniteLine(
                    pos=x, angle=90, movable=True,
                    pen=pg.mkPen(color, width=1.4),
                    hoverPen=pg.mkPen(color, width=2.5),
                    label=(phase if i == 0 else None),
                    labelOpts={"position": 0.9, "color": color})
                # Por encima de la región de selección (z=10) para que el
                # picker se arrastre aunque caiga dentro de ella.
                ln.setZValue(20)
                ln.sigPositionChanged.connect(
                    lambda _=None, ph=phase, src=ln: self._sync_pick(ph, src))
                self._plots[ch].addItem(ln)
                lines.append(ln)
            self._picks[phase] = lines
        self._update_readout()

    def _sync_pick(self, phase: str, src: pg.InfiniteLine) -> None:
        """Mantiene las 3 líneas del mismo pick a la misma X al arrastrar."""

        if self._syncing:
            return
        self._syncing = True
        x = src.value()
        for ln in self._picks.get(phase, []):
            if ln is not src:
                ln.setPos(x)
        self._syncing = False
        self._update_readout()

    def _clear_picks(self) -> None:
        for lines in self._picks.values():
            for ln, ch in zip(lines, _CHANNELS):
                self._plots[ch].removeItem(ln)
        self._picks.clear()
        self._update_readout()

    # ------------------------------------------------------------------
    # Puente detector STA/LTA → análisis (v0.7.7)
    # ------------------------------------------------------------------
    def set_cft(self, cft: float, threshold: float) -> None:
        """Lectura en vivo del ratio STA/LTA (cft) en la barra; rojo si ≥
        umbral. Ayuda a ajustar el umbral sin adivinar.

        Además, si ⚡ (auto-análisis) está activo y el cft supera el umbral
        (señal fuerte en pantalla), congela de inmediato para analizar — así
        ⚡ responde al instante en vez de esperar el "instante de disparo"
        exacto (que podía tardar hasta el próximo evento)."""

        over = cft >= threshold
        self._cft_label.setText(f"cft {cft:.1f}")
        if over is not self._cft_over:
            self._cft_over = over
            color = "#ff5a52" if over else None
            css = "font-family: monospace; font-size: 11px;"
            self._cft_label.setStyleSheet(
                css + (f" color: {color};" if color else ""))
        if over and self._auto_btn.isChecked() and not self._frozen:
            self._auto_freeze(cft)

    def on_trigger(self, cft: float) -> None:
        """El detector disparó (transición armado→disparado). Congela si ⚡
        está activo (la mayoría de las veces ``set_cft`` ya lo hizo)."""

        if not self._auto_btn.isChecked() or self._frozen:
            return
        self._auto_freeze(cft)

    def _auto_freeze(self, cft: float) -> None:
        """Congela + marca el evento para analizarlo (disparado por ⚡)."""

        self.set_frozen(True)
        self._place_trigger_marker()
        self._readout.setText(t("analysis.trigger_readout", cft=f"{cft:.1f}"))

    def _place_trigger_marker(self) -> None:
        self._clear_trigger_marker()
        x = 0.0
        if self._last_snapshot is not None and self._last_snapshot.times.size:
            x = float(self._last_snapshot.times[-1])
        for i, ch in enumerate(_CHANNELS):
            ln = pg.InfiniteLine(
                pos=x, angle=90, movable=False,
                pen=pg.mkPen("#ff5a52", width=1.5, style=Qt.DashLine),
                label=("T" if i == 0 else None),
                labelOpts={"position": 0.06, "color": "#ff5a52"})
            ln.setZValue(15)
            self._plots[ch].addItem(ln)
            self._trigger_lines.append(ln)

    def _clear_trigger_marker(self) -> None:
        for ln, ch in zip(self._trigger_lines, _CHANNELS):
            self._plots[ch].removeItem(ln)
        self._trigger_lines = []

    def _reset_zoom(self) -> None:
        if self._static_mode:
            self.fit_all()
            return
        if self._last_snapshot is not None and self._last_snapshot.times.size:
            tm = self._last_snapshot.times
            self._plots[_CHANNELS[0]].setXRange(
                float(tm[0]), float(tm[-1]), padding=0.0)

    def _update_readout(self, *args) -> None:
        if not self._frozen:
            return
        parts: list[str] = []
        snap = self._last_snapshot

        # Región: pico = MÁXIMO de las 3 componentes (la amplitud útil suele
        # estar en las horizontales, no solo en Z); RMS y f₀ del canal más
        # energético del tramo.
        if snap is not None and snap.times.size:
            x0, x1 = self._regions[_CHANNELS[0]].getRegion()
            mask = ((snap.times >= min(x0, x1))
                    & (snap.times <= max(x0, x1)))
            if mask.any():
                best_ch, best_peak, best_seg = None, -1.0, None
                for ch in _CHANNELS:
                    s = snap.samples.get(ch)
                    if s is None or s.size == 0:
                        continue
                    seg = self._display(s[mask])
                    if seg.size < 2:
                        continue
                    pk = _meas.peak_amplitude(seg)
                    if pk > best_peak:
                        best_ch, best_peak, best_seg = ch, pk, seg
                if best_seg is not None:
                    parts.append(t(
                        "analysis.readout",
                        dur=f"{abs(x1 - x0):.2f}",
                        peak=f"{self._fmt_amp(best_peak)} ({best_ch})",
                        rms=self._fmt_amp(_meas.rms(best_seg)),
                        fdom=f"{_meas.dominant_frequency(best_seg, self._sample_rate_hz):.2f}",
                    ))

        # Picks: S-P → distancia → ML (pico de las HORIZONTALES, según la
        # definición clásica de ML; Z subestima la amplitud de la onda S).
        if "P" in self._picks and "S" in self._picks:
            tp = self._picks["P"][0].value()
            ts = self._picks["S"][0].value()
            sp = abs(ts - tp)
            dist = _meas.sp_to_distance_km(sp)
            seg_part = f"S-P {sp:.2f}s ≈ {dist:.0f} km"
            if self._is_velocity() and snap is not None:
                peak_h = 0.0
                for ch in ("N", "E"):
                    s = snap.samples.get(ch)
                    if s is not None and s.size:
                        peak_h = max(
                            peak_h, _meas.peak_amplitude(self._display(s)))
                ml = _meas.local_magnitude(peak_h, dist)
                if ml:
                    seg_part += f" · ML~{ml:.1f}"
            parts.append(seg_part)

        self._readout.setText("   ·   ".join(parts)
                              if parts else t("analysis.select_hint"))
        # Avisar a quien escuche (panel PSD) que el tramo cambió.
        self.region_changed.emit()

    def _axis_time_label(self) -> str:
        # En modo estático el eje es hora UTC absoluta (no segundos relativos).
        return t("waveform.axis_time_utc") if self._static_mode \
            else t("waveform.axis_time")

    def _retranslate(self) -> None:
        self.station_header.setText(
            t("waveform.station_label", label=self._station_text))
        self._plots[_CHANNELS[-1]].setLabel("bottom", self._axis_time_label())
        self._freeze_btn.setText(t("controls.analysis.freeze"))
        self._freeze_btn.setToolTip(t("analysis.tip_freeze"))
        self._units_btn.setToolTip(t("analysis.tip_units"))
        self._pick_p_btn.setToolTip(t("analysis.tip_pick_p"))
        self._pick_s_btn.setToolTip(t("analysis.tip_pick_s"))
        self._clear_btn.setToolTip(t("analysis.tip_clear"))
        self._reset_btn.setToolTip(t("analysis.tip_reset"))
        self._auto_btn.setText(t("controls.analysis.auto"))
        self._auto_btn.setToolTip(t("analysis.tip_auto"))
        if self._frozen:
            self._update_readout()
