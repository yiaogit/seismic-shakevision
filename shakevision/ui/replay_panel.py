"""
Panel de **revisión histórica** (Pro tab #4).

v0.7.7 — reescrito de "reproductor de vídeo" a **navegador de forma de onda
estático** (paradigma SWARM / Snuffler / ObsPyck). Antes descargaba una
ventana y la "reproducía" a N×; ahora:

  1. La estación sigue a la selección de la barra lateral (N.S.L.C. de solo
     lectura), no se teclea.
  2. Se elige una ventana temporal (start datetime UTC + duración).
  3. "Descargar" → ``DataselectClient`` en un hilo.
  4. Al terminar, TODA la traza se dibuja de una vez (eje X = hora UTC) y se
     navega con **zoom/pan** del ratón. Las herramientas de análisis
     (región / cursor / picks P-S / unidades / medidas) están siempre activas.

Ya NO hay reproducir / pausar / detener / velocidad / barra de progreso.

Dependencias UI reutilizadas: WaveformPanel (static_mode), SpectrogramPanel,
LoadingOverlay (mismos widgets que el Live tab).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSpinBox,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import QDateTime

from shakevision.config import AppConfig, seedlink_location_for
from shakevision.i18n import LocaleService, t
from shakevision.processing.filters import WaveformProcessor
from shakevision.processing.spectrum import SpectrumComputer
from shakevision.services.dataselect import (
    DataselectClient,
    DataselectError,
    NoDataAvailable,
)
from shakevision.sources.replay import _stream_to_channels
from shakevision.services.response import ResponseService
from shakevision.ui.combo_utils import fit_combo
from shakevision.ui.loading_overlay import LoadingOverlay
from shakevision.ui.spectrogram_widget import SpectrogramPanel
from shakevision.ui.spectrum_panel import SpectrumPanel
from shakevision.ui.signal_safety import subscribe
from shakevision.ui.waveform_widget import WaveformPanel

logger = logging.getLogger(__name__)

# Bandas instrumentales SEED ofrecidas en Replay (código corto). La
# descripción de cada una se traduce vía ``replay.band.<code>``.
_BANDS: tuple[str, ...] = ("BH", "HH", "LH", "EH", "SH")


# ============================================================
# Worker de descarga (vive en QThread)
# ============================================================
@dataclass
class _DownloadRequest:
    network: str
    station: str
    location: str
    channel: str
    starttime: datetime
    endtime: datetime


class _DownloadWorker(QObject):
    """Descarga MiniSEED desde IRIS dataselect en un hilo trabajador.

    Emite ``done(stream)`` cuando el Stream está listo o
    ``failed(msg)`` con un mensaje legible si falló.
    """

    done = Signal(object)        # obspy.Stream
    failed = Signal(str)         # mensaje i18n-listo

    def __init__(self, req: _DownloadRequest) -> None:
        super().__init__()
        self._req = req
        self._client = DataselectClient()

    @Slot()
    def run(self) -> None:
        try:
            stream = self._client.fetch_stream(
                network=self._req.network,
                station=self._req.station,
                location=self._req.location,
                channel=self._req.channel,
                starttime=self._req.starttime,
                endtime=self._req.endtime,
            )
            if stream is None or len(stream) == 0:
                self.failed.emit(t("replay.error.no_traces"))
                return
            self.done.emit(stream)
        except NoDataAvailable as exc:
            logger.info("Replay: sin datos para la consulta (%s)", exc)
            self.failed.emit(t("replay.error.no_data"))
        except DataselectError as exc:
            logger.warning("Replay: dataselect error: %s", exc)
            self.failed.emit(t("replay.error.network", detail=str(exc)))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Replay: fallo inesperado en descarga")
            self.failed.emit(t("replay.error.unexpected", detail=str(exc)))


# ============================================================
# Panel
# ============================================================
class ReplayPanel(QWidget):
    """Tab de reproducción histórica."""

    #: v0.7.7: sensibilidad (counts/(m/s)) obtenida en hilo de fondo para el
    #: botón m/s del análisis; ``None`` si no disponible.
    _sensitivity_ready = Signal(object)
    #: v0.7.7: llegadas teóricas TauP calculadas en hilo de fondo —
    #: lista de ``(etiqueta, tiempo_unix, color)`` o ``[]``.
    _arrivals_ready = Signal(object)
    #: v0.7.7: resultado de deconvolución completa — ``(output, (z,n,e)|None)``.
    _deconv_ready = Signal(object)
    #: v0.7.7 (UX): ventana sugerida por TauP ``(start_ts, duration_s)`` o None.
    _window_ready = Signal(object)

    def __init__(self, config: AppConfig, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._config = config
        self._download_thread: Optional[QThread] = None
        self._download_worker: Optional[_DownloadWorker] = None
        self._loaded: bool = False
        # Picks P/S guardados a re-dibujar tras la descarga (reabrir desde el
        # catálogo "Mi colección"); ``{fase: tiempo_unix}`` o None.
        self._pending_user_picks: Optional[dict] = None
        # Arrays CRUDOS cargados (z, n, e, start_ts, sr); None si vacío.
        self._loaded_arrays = None
        # Arrays MOSTRADOS (filtrados/rotados) — lo que se exporta a CSV.
        self._display_arrays = None
        # Filtro vigente (se actualiza desde la barra lateral vía
        # on_filter_changed); arranca con el de la config.
        self._filt = config.filt
        self._export_buttons: list[QPushButton] = []
        # Rotación ZNE→ZRT (necesita evento + coords de estación).
        self._rotated: bool = False
        self._station_coords = None          # (lat, lon) | None
        self._event_dist_deg = None          # distancia epicentral (grados)
        self._last_arrivals: list = []       # para re-superponer tras re-render
        # Contexto de evento (cuando se entra desde un sismo del globo):
        # dict con lat/lon/depth_km/origin_ts, o None. Habilita TauP.
        self._event: Optional[dict] = None
        self._event_name: str = ""           # texto del sismo a revisar
        # ¿La estación la fijó la revisión de evento (independiente del combo)?
        self._event_station_mode: bool = False
        # True mientras fijamos la fecha de forma PROGRAMÁTICA (prefill /
        # catálogo / sugerir-ventana): evita que ``dateTimeChanged`` borre el
        # contexto de evento. Solo los cambios MANUALES del usuario lo borran.
        self._dt_programmatic: bool = False
        # v0.7.7: servicio de respuesta instrumental (lazy) para el botón m/s.
        self._response_service = None
        # Salida física: "counts" | "VEL" | "DISP" | "ACC". Para ≠counts se
        # hace deconvolución completa del Stream (cache por output).
        self._stream = None
        self._output: str = "counts"
        self._deconv_cache: dict = {}
        self._deconv_pending = None
        self._sensitivity_ready.connect(self._apply_sensitivity)
        self._arrivals_ready.connect(self._apply_arrivals)
        self._deconv_ready.connect(self._on_deconv_ready)
        self._window_ready.connect(self._apply_suggested_window)

        self._build_ui()

        subscribe(self, LocaleService.language_changed_signal(),
                  self._retranslate)  # v0.7.7 (B1)

    # ------------------------------------------------------------------
    # Construcción de UI
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # ─── Banner del evento en revisión (oculto si no hay evento) ───
        self._event_banner = QLabel("")
        self._event_banner.setObjectName("EventBanner")
        self._event_banner.setWordWrap(True)
        self._event_banner.setVisible(False)
        root.addWidget(self._event_banner)

        # ─── Formulario superior ───
        form = QGridLayout()
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(6)

        # ─── Estación (SOLO LECTURA) ─────────────────────────────────
        # v0.7.7: la estación NO se teclea aquí. Sigue automáticamente a la
        # que el usuario tiene seleccionada en la barra lateral (ProWindow
        # conecta ``control_panel.station_changed`` → ``set_station``). Esto
        # evita el desajuste anterior, en el que la barra mostraba IU.GUMO
        # pero Replay descargaba IU.ANMO por defecto.
        self._net, self._sta, self._loc, self._cha = "IU", "ANMO", "00", "BH?"

        # v0.8.0: selector de estación PROPIO de Replay (desacoplado del combo
        # en vivo). Es un DESPLEGABLE de estaciones conocidas (no se teclea):
        # el combo en vivo, favoritos y el evento revisado alimentan sus
        # opciones. Cambiarlo a mano = búsqueda histórica de OTRA estación.
        self._lbl_station = QLabel()
        form.addWidget(self._lbl_station, 0, 0)
        self.station_combo = QComboBox()
        self.station_combo.setObjectName("StationValue")
        self.station_combo.setMinimumWidth(180)
        self.station_combo.currentIndexChanged.connect(
            self._on_replay_station_changed)
        form.addWidget(self.station_combo, 0, 1, 1, 2)

        # Selector de BANDA (BH/HH/LH/EH/SH). El código de estación lo fija la
        # selección de la barra lateral; aquí el usuario solo elige la banda
        # instrumental (un mismo sitio tiene varias). Cada opción lleva una
        # descripción de la función del sensor. ``userData`` = código corto.
        self._lbl_band = QLabel()
        form.addWidget(self._lbl_band, 0, 3)
        self.band_combo = QComboBox()
        for band in _BANDS:
            self.band_combo.addItem(band, userData=band)
        # Caja + popup dimensionados a la descripción más larga entre idiomas.
        fit_combo(self.band_combo,
                  i18n_keys=[f"replay.band.{b.lower()}" for b in _BANDS])
        self.band_combo.currentIndexChanged.connect(self._on_band_changed)
        form.addWidget(self.band_combo, 0, 4, 1, 2)

        self._lbl_station_hint = QLabel()
        self._lbl_station_hint.setObjectName("Caption")
        self._lbl_station_hint.setWordWrap(True)
        form.addWidget(self._lbl_station_hint, 0, 6, 1, 2)

        # Start datetime (UTC)
        # IMPORTANTE: QDateTimeEdit con `setCalendarPopup(True)` muestra
        # el calendario al pulsar la flecha, pero EL CAMPO mismo permite
        # editar horas/minutos/segundos por sección. Para que el usuario
        # vea que es editable a nivel segundo, abrimos el control en la
        # sección "minuto" + KeyboardTracking para que las flechas ↑↓
        # actúen sobre la sección bajo el cursor.
        self._lbl_start = QLabel()
        form.addWidget(self._lbl_start, 1, 0)
        self.start_dt = QDateTimeEdit()
        # El campo ES UTC (coincide con la etiqueta 'UTC' y con la política de
        # superficies profesionales). Antes era LocalTime y se convertía con
        # .toUTC() al leer: el INSTANTE de consulta no cambia (ese .toUTC() pasa
        # a ser no-op), pero ahora la ENTRADA MANUAL y la visualización están en
        # UTC de verdad, sin el desfase silencioso de la zona local.
        self.start_dt.setTimeSpec(Qt.TimeSpec.UTC)
        self.start_dt.setDisplayFormat("yyyy-MM-dd  HH:mm:ss  'UTC'")
        self.start_dt.setCalendarPopup(True)
        self.start_dt.setKeyboardTracking(True)
        self.start_dt.setDateTime(
            QDateTime.currentDateTimeUtc().addSecs(-3600)
        )
        # Empezar con el cursor en la sección "minutos" (más útil para
        # ajustar precisión que en el año).
        self.start_dt.setCurrentSection(QDateTimeEdit.MinuteSection)
        # Acotar el rango: nada de fechas futuras (sin datos) ni pre-1900.
        # (No cambiamos el TimeSpec del campo para no alterar la lectura
        # existente vía .toUTC() — solo los límites.)
        from shakevision.ui.date_picker import CATALOG_FLOOR, cap_to_now
        self.start_dt.setMinimumDate(CATALOG_FLOOR)
        cap_to_now(self.start_dt)
        # Cambio MANUAL de fecha → búsqueda histórica independiente (quita el
        # banner "revisando evento"). Los cambios programáticos van protegidos.
        self.start_dt.dateTimeChanged.connect(self._on_start_dt_changed)
        form.addWidget(self.start_dt, 1, 1, 1, 3)

        # Duration con presets rápidos (30s / 1m / 2m / 5m / 30m)
        # ──────────────────────────────────────────────────────────────
        # 120 s es el default sensato: cubre P+S+coda de un sismo
        # regional sin esperar a descargar 5 minutos de ruido.
        # Los botones cambian el spinbox directamente para que el
        # usuario también pueda ajustar a un valor arbitrario.
        self._lbl_dur = QLabel()
        form.addWidget(self._lbl_dur, 1, 4)
        self.dur_spin = QSpinBox()
        self.dur_spin.setRange(10, 6 * 3600)
        self.dur_spin.setValue(120)
        self.dur_spin.setSuffix(" s")
        self.dur_spin.setMinimumWidth(110)
        form.addWidget(self.dur_spin, 1, 5)

        # Salida física: counts / VEL / DISP / ACC (deconvolución completa).
        self._lbl_output = QLabel()
        form.addWidget(self._lbl_output, 1, 6)
        self.output_combo = QComboBox()
        for code in ("counts", "VEL", "DISP", "ACC"):
            self.output_combo.addItem(code, userData=code)
        fit_combo(self.output_combo, i18n_keys=[
            "replay.out_counts", "replay.out_vel",
            "replay.out_disp", "replay.out_acc"])
        self.output_combo.currentIndexChanged.connect(self._on_output_changed)
        form.addWidget(self.output_combo, 1, 7)

        root.addLayout(form)

        # ─── Fila de "presets de duración" ───────────────────────────
        # Atajos típicos para reconstruir un evento. Pulsar el botón
        # solo cambia el valor del spinbox; el usuario aún tiene que
        # pulsar "Descargar" para confirmar.
        preset_row = QHBoxLayout()
        preset_row.setSpacing(4)
        self._lbl_dur_preset = QLabel()
        preset_row.addWidget(self._lbl_dur_preset)
        self._duration_preset_buttons: list[QPushButton] = []
        for label, seconds in (
            ("30 s", 30), ("1 min", 60), ("2 min", 120),
            ("5 min", 300), ("10 min", 600), ("30 min", 1800),
            ("1 h", 3600),
        ):
            btn = QPushButton(label)
            # Ancho mínimo cómodo (antes setMaximumWidth(70) recortaba
            # "10 min"/"30 min"). Dejamos que el botón crezca al contenido.
            btn.setMinimumWidth(56)
            btn.setProperty("seconds", seconds)
            btn.clicked.connect(self._on_duration_preset_clicked)
            preset_row.addWidget(btn)
            self._duration_preset_buttons.append(btn)
        preset_row.addStretch(1)
        root.addLayout(preset_row)

        # ─── Filtro INDEPENDIENTE de Replay (v0.8.0) ─────────────────
        # El modo histórico ya NO sigue el filtro de la barra lateral; tiene su
        # propio paso de banda (se inicializa desde config.filt).
        filt_row = QHBoxLayout()
        filt_row.setSpacing(6)
        self.filt_check = QCheckBox()
        self.filt_check.setChecked(bool(getattr(self._filt, "enabled", True)))
        self.filt_check.toggled.connect(self._on_replay_filter_changed)
        filt_row.addWidget(self.filt_check)
        self._lbl_filt_low = QLabel()
        filt_row.addWidget(self._lbl_filt_low)
        self.filt_low = QDoubleSpinBox()
        self.filt_low.setRange(0.01, 50.0)
        self.filt_low.setDecimals(2)
        self.filt_low.setSingleStep(0.1)
        self.filt_low.setSuffix(" Hz")
        self.filt_low.setMinimumWidth(96)
        self.filt_low.setValue(float(getattr(self._filt, "lowcut_hz", 0.5)))
        self.filt_low.valueChanged.connect(self._on_replay_filter_changed)
        filt_row.addWidget(self.filt_low)
        self._lbl_filt_high = QLabel()
        filt_row.addWidget(self._lbl_filt_high)
        self.filt_high = QDoubleSpinBox()
        self.filt_high.setRange(0.02, 50.0)
        self.filt_high.setDecimals(2)
        self.filt_high.setSingleStep(0.5)
        self.filt_high.setSuffix(" Hz")
        self.filt_high.setMinimumWidth(96)
        self.filt_high.setValue(float(getattr(self._filt, "highcut_hz", 10.0)))
        self.filt_high.valueChanged.connect(self._on_replay_filter_changed)
        filt_row.addWidget(self.filt_high)
        filt_row.addStretch(1)
        root.addLayout(filt_row)

        # ─── Botonera (solo Descargar; sin reproducir/pausar/detener) ───
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self.download_btn = QPushButton()
        self.download_btn.clicked.connect(self._on_download_clicked)
        btn_row.addWidget(self.download_btn)

        # Limpiar la traza histórica cargada (independiente de la conexión en
        # vivo). Antes "limpiar" estaba atado al botón Detener del stream; ahora
        # Replay tiene su propio botón. Deshabilitado hasta que haya algo cargado.
        self.clear_btn = QPushButton()
        self.clear_btn.clicked.connect(self._on_clear_clicked)
        self.clear_btn.setEnabled(False)
        btn_row.addWidget(self.clear_btn)

        # Rotación ZNE→ZRT (checkable). Solo se habilita cuando hay contexto
        # de evento + coordenadas de estación (para el back-azimuth).
        self.rotate_btn = QPushButton()
        self.rotate_btn.setCheckable(True)
        self.rotate_btn.setEnabled(False)
        self.rotate_btn.toggled.connect(self._on_rotate_toggled)
        btn_row.addWidget(self.rotate_btn)

        # Exportar: un único botón con menú (PNG / CSV / QuakeML / catálogo)
        # para no saturar la barra. Deshabilitado hasta que haya traza.
        self.export_btn = QToolButton()
        self.export_btn.setPopupMode(QToolButton.InstantPopup)
        self.export_btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self._export_menu = QMenu(self.export_btn)
        self._act_png = self._export_menu.addAction("", self._on_export_png)
        self._act_csv = self._export_menu.addAction("", self._on_export_csv)
        self._act_quakeml = self._export_menu.addAction(
            "", self._on_export_quakeml)
        self._act_catalog = self._export_menu.addAction(
            "", self._on_save_catalog)
        self.export_btn.setMenu(self._export_menu)
        self.export_btn.setEnabled(False)
        self._export_buttons = [self.export_btn]
        btn_row.addWidget(self.export_btn)

        # Mostrar/ocultar paneles inferiores: con 3 gráficas apretadas, el
        # usuario elige cuáles ver (la de ondas siempre está). Al ocultar una,
        # las demás ganan alto.
        self.toggle_spec_btn = QPushButton()
        self.toggle_spec_btn.setCheckable(True)
        self.toggle_spec_btn.setChecked(True)
        self.toggle_spec_btn.toggled.connect(self._on_toggle_spectrogram)
        btn_row.addWidget(self.toggle_spec_btn)
        self.toggle_psd_btn = QPushButton()
        self.toggle_psd_btn.setCheckable(True)
        self.toggle_psd_btn.setChecked(True)
        self.toggle_psd_btn.toggled.connect(self._on_toggle_psd)
        btn_row.addWidget(self.toggle_psd_btn)

        btn_row.addStretch(1)

        self.status_label = QLabel("")
        self.status_label.setObjectName("StatusValue")
        btn_row.addWidget(self.status_label)

        root.addLayout(btn_row)

        # ─── Visualización: waveform (estático) + spectrogram ───
        splitter = QSplitter(Qt.Vertical, parent=self)
        # v0.7.7: navegador estático — la traza se carga entera y se navega
        # con zoom/pan; análisis (región/cursor/picks/unidades) siempre activo,
        # eje X = hora UTC. Sin herramientas del detector STA/LTA en vivo.
        self.waveform_panel = WaveformPanel(
            parent=splitter, show_detector_tools=False, static_mode=True)
        self.waveform_panel.units_requested.connect(self._on_units_requested)
        # v0.7.7: PSD del tramo seleccionado (caja amarilla) → 2.º bloque.
        self.waveform_panel.region_changed.connect(self._update_psd)
        # absolute_time=True: en Replay el espectrograma usa hora UTC absoluta
        # (igual que el oscilograma), no segundos relativos.
        self.spectrogram_panel = SpectrogramPanel(
            parent=splitter, absolute_time=True)
        self.spectrum_panel = SpectrumPanel(parent=splitter)
        splitter.addWidget(self.waveform_panel)
        splitter.addWidget(self.spectrogram_panel)
        splitter.addWidget(self.spectrum_panel)
        splitter.setStretchFactor(0, 52)
        splitter.setStretchFactor(1, 24)
        splitter.setStretchFactor(2, 24)
        root.addWidget(splitter, stretch=1)

        # Overlay para fase de descarga
        self._overlay = LoadingOverlay(self)
        self._overlay.hide_overlay()

        self._retranslate()

    # ------------------------------------------------------------------
    # i18n
    # ------------------------------------------------------------------
    def _retranslate(self) -> None:
        self._lbl_station.setText(t("replay.field.station"))
        self._update_station_hint()
        self._lbl_start.setText(t("replay.field.start"))
        self._lbl_dur.setText(t("replay.field.duration"))
        self.filt_check.setText(t("replay.filter_enable"))
        self._lbl_filt_low.setText(t("replay.filter_low"))
        self._lbl_filt_high.setText(t("replay.filter_high"))
        self.download_btn.setText(t("replay.button.download"))
        self.clear_btn.setText(t("replay.button.clear"))
        self.rotate_btn.setText(t("replay.button.rotate"))
        self.rotate_btn.setToolTip(t("replay.rotate_tooltip"))
        self.toggle_spec_btn.setText(t("replay.toggle_spectrogram"))
        self.toggle_psd_btn.setText(t("replay.toggle_psd"))
        self.export_btn.setText(t("replay.button.export"))
        try:
            from shakevision.ui.icons import get_icon
            from shakevision.ui.theme_manager import ThemeManager as _TM
            self.export_btn.setIcon(get_icon("export", theme=_TM.current_theme()))
        except Exception:  # noqa: BLE001
            pass
        self._act_png.setText(t("replay.button.export_png"))
        self._act_csv.setText(t("replay.button.export_csv"))
        self._act_quakeml.setText(t("replay.button.export_quakeml"))
        self._act_catalog.setText(t("replay.button.save_catalog"))
        self._lbl_band.setText(t("replay.field.band"))
        self._apply_band_texts()
        self._lbl_output.setText(t("replay.field.output"))
        self._apply_output_texts()
        self._lbl_dur_preset.setText(t("replay.field.duration_preset"))
        self._update_station_display()

    def _apply_output_texts(self) -> None:
        labels = {
            "counts": t("replay.out_counts"), "VEL": t("replay.out_vel"),
            "DISP": t("replay.out_disp"), "ACC": t("replay.out_acc"),
        }
        self.output_combo.blockSignals(True)
        for i in range(self.output_combo.count()):
            code = self.output_combo.itemData(i)
            self.output_combo.setItemText(i, labels.get(code, str(code)))
        self.output_combo.blockSignals(False)

    def _apply_band_texts(self) -> None:
        """Texto descriptivo de cada banda (con la función del sensor) +
        tooltip explicativo. Conserva ``userData`` (código) y la selección."""

        self.band_combo.blockSignals(True)
        for i in range(self.band_combo.count()):
            code = self.band_combo.itemData(i)
            self.band_combo.setItemText(i, t(f"replay.band.{str(code).lower()}"))
            self.band_combo.setItemData(i, t("replay.band.tooltip"),
                                        Qt.ToolTipRole)
        self.band_combo.setToolTip(t("replay.band.tooltip"))
        self.band_combo.blockSignals(False)

    # ------------------------------------------------------------------
    # Estación (sigue a la selección de la barra lateral) — v0.7.7
    # ------------------------------------------------------------------
    def _update_station_display(self) -> None:
        """Asegura que el combo muestra la estación actual (_net/_sta),
        añadiéndola si faltaba. Selección PROGRAMÁTICA (no dispara el handler)."""

        idx = self.add_available_station(
            self._net, self._sta, self._loc, (self._cha or "BH")[:2])
        if idx >= 0:
            self._select_station_index(idx)

    def _update_station_hint(self) -> None:
        """Aclara de dónde viene la estación: sigue al combo (modo normal) o es
        la del evento en revisión (independiente del台站 en vivo de la barra)."""

        key = ("replay.field.station_event" if self._event_station_mode
               else "replay.field.station_hint")
        self._lbl_station_hint.setText(t(key))

    def load_catalog_event(self, detail: dict) -> None:
        """Reabre en Replay una revisión guardada en el catálogo "Mi colección".

        ``detail`` (de ``CatalogStore.get_event``):
        ``{net, sta, loc, band, picks:{fase:ts}, origin|None, desc}``. Fija la
        estación + una ventana que cubre los picks guardados, descarga, y vuelve
        a dibujar los picks P/S originales encima. NO calcula TauP (los picks
        guardados son la referencia que el usuario quiere recuperar).
        """

        picks = {k: float(v) for k, v in (detail.get("picks") or {}).items()}
        if not picks:
            self.status_label.setText(t("replay.catalog_no_picks"))
            return

        # Estación (directa, sin tocar el combo de la barra ni la conexión).
        self._net = (detail.get("net") or "").upper()
        self._sta = (detail.get("sta") or "").upper()
        loc = (detail.get("loc") or "").strip()
        if loc in ("", "*", "--"):
            loc = seedlink_location_for(self._net)
        self._loc = loc
        b = (detail.get("band") or "BH").upper()[:2]
        self._cha = f"{b}?"
        self._set_band_combo(b)

        # Sin contexto de evento → sin TauP; los picks guardados mandan.
        self._event = None
        self._event_station_mode = True
        self._event_name = detail.get("desc") or f"{self._net}.{self._sta}"
        self._station_coords = None
        self._event_dist_deg = None
        self._update_station_display()
        self._update_station_hint()
        self._update_event_banner()

        # Ventana que cubre los picks (con margen) — mínimo 120 s.
        t_min, t_max = min(picks.values()), max(picks.values())
        span = t_max - t_min
        dur = int(max(120, span + 120))
        self._set_start_dt(
            QDateTime.fromSecsSinceEpoch(
                int(t_min - 60), Qt.OffsetFromUTC, 0))
        self.dur_spin.setValue(dur)

        # Stash + descargar; los picks se re-dibujan en _on_download_done.
        self._pending_user_picks = picks
        self._on_download_clicked()

    def _restore_saved_picks(self, picks: dict) -> None:
        """Dibuja los picks P/S guardados como marcadores sobre la traza."""

        colors = {"P": "#43d17a", "S": "#ff5ad6"}
        markers = [
            (phase, float(ts), colors.get(phase, "#9aa0a6"))
            for phase, ts in sorted(picks.items(), key=lambda kv: kv[1])
        ]
        self._last_arrivals = markers
        try:
            self.waveform_panel.set_phase_markers(markers)
        except (RuntimeError, AttributeError):
            pass
        dist_txt = f"{len(markers)}"
        self.status_label.setText(t("replay.catalog_restored", n=dist_txt))

    # ── Selector de estación PROPIO de Replay (v0.8.0 desacople) ──────
    @staticmethod
    def _station_entry(net: str, sta: str, loc: str = "",
                       band: str = "BH", label: str = "") -> dict:
        net = (net or "").upper()
        sta = (sta or "").upper()
        return {
            "net": net, "sta": sta, "loc": loc or "",
            "band": (band or "BH").upper()[:2],
            "label": label or f"{net}.{sta}",
        }

    def add_available_station(self, net: str, sta: str, loc: str = "",
                              band: str = "BH", label: str = "",
                              select: bool = False) -> int:
        """Añade una estación como OPCIÓN del combo de Replay (dedup por N.S).
        Devuelve su índice, o -1 si net/sta vacíos. ``select`` la selecciona de
        forma PROGRAMÁTICA (sin disparar el handler de cambio)."""

        entry = self._station_entry(net, sta, loc, band, label)
        if not entry["net"] or not entry["sta"]:
            return -1
        for i in range(self.station_combo.count()):
            d = self.station_combo.itemData(i)
            if d and d["net"] == entry["net"] and d["sta"] == entry["sta"]:
                if select:
                    self._select_station_index(i)
                return i
        # blockSignals: añadir el PRIMER ítem cambia el índice -1→0 y dispararía
        # el handler de cambio espuriamente; la selección genuina del usuario
        # (clic en el desplegable) no pasa por aquí y sí dispara.
        self.station_combo.blockSignals(True)
        self.station_combo.addItem(entry["label"], userData=entry)
        self.station_combo.blockSignals(False)
        fit_combo(self.station_combo)  # etiquetas de estación (sin idioma)
        idx = self.station_combo.count() - 1
        if select:
            self._select_station_index(idx)
        return idx

    def add_available_preset(self, preset, select: bool = False) -> int:
        """Añade una estación desde un ``StationPreset`` (combo en vivo)."""

        from shakevision.config import StationPreset
        if not isinstance(preset, StationPreset):
            return -1
        band = (preset.channel or "BH?")[:2]
        return self.add_available_station(
            preset.network, preset.station, preset.location, band,
            preset.label, select=select)

    def _select_station_index(self, idx: int) -> None:
        self.station_combo.blockSignals(True)
        self.station_combo.setCurrentIndex(idx)
        self.station_combo.blockSignals(False)

    def _apply_station_entry(self, entry: dict) -> None:
        """Vuelca una entrada del combo a _net/_sta/_loc/_cha + banda."""

        self._net = entry["net"]
        self._sta = entry["sta"]
        loc = (entry["loc"] or "").strip()
        if loc in ("", "*", "--"):
            loc = seedlink_location_for(self._net)
        self._loc = loc
        self._cha = f"{entry['band']}?"
        self._set_band_combo(entry["band"])

    def _on_replay_station_changed(self, _idx: int) -> None:
        """Cambio MANUAL de estación en Replay → búsqueda histórica de OTRA
        estación; invalida el contexto de evento (banner/TauP)."""

        entry = self.station_combo.currentData()
        if not entry:
            return
        self._apply_station_entry(entry)
        self._event = None
        self._event_name = ""
        self._event_station_mode = False
        self._event_dist_deg = None
        self._set_load_cta(False)
        self._update_event_banner()
        self._update_station_hint()

    def set_station(self, preset) -> None:
        """v0.8.0: la estación del combo EN VIVO se añade a Replay como OPCIÓN.
        Solo se SELECCIONA si Replay aún no tenía ninguna (default inicial);
        cambios posteriores del combo en vivo NO secuestran la selección de
        Replay — Replay es independiente del modo en vivo."""

        was_empty = self.station_combo.count() == 0
        idx = self.add_available_preset(preset, select=was_empty)
        if was_empty and idx >= 0:
            self._apply_station_entry(self.station_combo.itemData(idx))
            self._update_station_hint()

    def select_history_station(self, net: str, sta: str, loc: str = "",
                               band: str = "BH", label: str = "") -> None:
        """Pone Replay en esta estación para análisis histórico (la añade +
        selecciona + aplica). Es el destino del "看历史" del diálogo de estación;
        invalida el contexto de evento (búsqueda histórica independiente)."""

        idx = self.add_available_station(net, sta, loc, band, label, select=True)
        if idx < 0:
            return
        self._apply_station_entry(self.station_combo.itemData(idx))
        self._event = None
        self._event_name = ""
        self._event_station_mode = False
        self._event_dist_deg = None
        self._set_load_cta(False)
        self._update_event_banner()
        self._update_station_hint()

    def _on_band_changed(self, _idx: int) -> None:
        """El usuario eligió otra banda instrumental (BH/HH/LH/…)."""

        band = self.band_combo.currentData() or "BH"
        self._cha = f"{band}?"
        self._update_station_display()

    def _set_band_combo(self, band: str) -> None:
        """Sincroniza el combo de banda sin disparar ``_on_band_changed``."""

        band = (band or "BH").upper()
        idx = self.band_combo.findData(band)
        self.band_combo.blockSignals(True)
        if idx < 0:
            self.band_combo.addItem(band, userData=band)
            idx = self.band_combo.findData(band)
        self.band_combo.setCurrentIndex(idx)
        self.band_combo.blockSignals(False)

    # ------------------------------------------------------------------
    # Entrada dirigida por evento (clic en un sismo del globo) — v0.7.7
    # ------------------------------------------------------------------
    def prefill_from_event_context(
        self, lat: float, lon: float, depth_km: float,
        origin: datetime, duration_s: int = 600, event_name: str = "",
    ) -> None:
        """Prepara una ventana alrededor del origen de un sismo del globo.

        MANTIENE la estación actualmente seleccionada (no la cambia): solo
        fija la ventana temporal (origen − 30 s) y guarda las coordenadas del
        evento para calcular las llegadas teóricas (TauP) tras la descarga.
        """

        # Limpiar la traza/caché anterior: al elegir OTRO evento (o tiempo) se
        # parte de cero — antes la traza vieja seguía hasta volver a Cargar.
        self._clear_display()
        origin_utc = origin.replace(tzinfo=timezone.utc) if origin.tzinfo is None \
            else origin.astimezone(timezone.utc)
        self._event = {
            "lat": float(lat), "lon": float(lon),
            "depth_km": max(0.0, float(depth_km)),
            "origin_ts": origin_utc.timestamp(),
        }
        self._set_start_dt(
            QDateTime.fromSecsSinceEpoch(
                int(origin_utc.timestamp() - 30), Qt.OffsetFromUTC, 0))
        self.dur_spin.setValue(int(duration_s))
        if event_name:
            self._event_name = event_name
        self._update_event_banner()
        # UX P0.2: guiar al usuario a pulsar "Cargar" (figura vacía si no).
        self._set_load_cta(True)
        self.status_label.setText(t("replay.click_load_hint"))

    def set_event_review(
        self, lat: float, lon: float, depth_km: float, origin: datetime,
        event_name: str, net: str, sta: str,
        loc: str = "", band: str = "BH", duration_s: int = 600,
    ) -> None:
        """Revisar un evento con una estación EXPLÍCITA (la cercana elegida en
        el centro de eventos).

        A diferencia de ``set_station`` (que sigue el combo de la barra
        lateral), aquí fijamos la estación directamente para ESTE evento, sin
        tocar el combo ni la conexión en vivo (Replay descarga del archivo
        IRIS; no necesita SeedLink). Muestra el nombre del evento en el banner.
        """

        self._net = (net or "").upper()
        self._sta = (sta or "").upper()
        loc = (loc or "").strip()
        if loc in ("", "*", "--"):
            loc = seedlink_location_for(net)
        self._loc = loc
        b = (band or "BH").upper()[:2]
        self._cha = f"{b}?"
        self._set_band_combo(b)
        self._event_station_mode = True
        self._update_station_display()
        self._update_station_hint()
        self._station_coords = None
        self._event_dist_deg = None
        # Mismo contexto de evento que prefill (habilita TauP tras descargar) +
        # nombre del evento para el banner.
        self.prefill_from_event_context(
            lat, lon, depth_km, origin, duration_s, event_name=event_name)
        # UX P0.1: ajustar la ventana automáticamente para que cubra P→S
        # (en segundo plano). El resalte del botón Cargar lo pone prefill.
        self._suggest_window_async()

    def _set_load_cta(self, on: bool) -> None:
        """Resalta el botón Cargar como llamada a la acción (evento prefijado)."""

        self.download_btn.setStyleSheet(
            "font-weight: bold;" if on else "")

    def _suggest_window_async(self) -> None:
        """Calcula en segundo plano una ventana que cubra P (y S) y la aplica.

        Pre-obtiene coords de estación + tiempos TauP ANTES de descargar, así
        un teleseísmo no se abre con una ventana que no contiene la señal.
        """

        ev = self._event
        if not ev:
            return
        # Feedback: la sugerencia hace una llamada de red (StationXML) que en
        # conexiones lentas tarda; avisar para que no parezca colgado.
        self.status_label.setText(t("replay.window_computing"))
        net, sta = self._net.strip().upper(), self._sta.strip().upper()
        loc = self._loc.strip() or "--"
        cha = (self._cha[:2] or "BH") + "Z"
        import threading

        def _work() -> None:
            win = None
            try:
                if self._response_service is None:
                    self._response_service = ResponseService()
                coords = self._response_service.coordinates_for(net, sta, loc, cha)
                if coords:
                    self._station_coords = coords
                    from obspy.geodetics import locations2degrees
                    from obspy.taup import TauPyModel
                    dist = locations2degrees(
                        ev["lat"], ev["lon"], coords[0], coords[1])
                    self._event_dist_deg = float(dist)
                    arr = TauPyModel(model="iasp91").get_travel_times(
                        source_depth_in_km=ev["depth_km"],
                        distance_in_degree=dist, phase_list=["P", "p", "S", "s"])
                    p = next((a for a in arr if a.name in ("P", "p")), None)
                    s = next((a for a in arr if a.name in ("S", "s")), None)
                    if p is not None:
                        start = ev["origin_ts"] + float(p.time) - 60.0
                        if s is not None:
                            end = ev["origin_ts"] + float(s.time) + 120.0
                        else:
                            end = ev["origin_ts"] + float(p.time) + 300.0
                        # Acotar a 30 min: ventanas enormes (teleseísmos) hacen
                        # descargas lentas; el usuario puede ampliar a mano.
                        dur = max(60, min(int(end - start), 1800))
                        win = (start, dur)
            except Exception:  # noqa: BLE001
                logger.debug("Replay: sugerencia de ventana falló", exc_info=True)
            self._window_ready.emit(win)

        threading.Thread(
            target=_work, name="replay-window", daemon=True).start()

    def _apply_suggested_window(self, win) -> None:
        if not win:
            # No se pudo (sin metadata/red): no dejar el estado "calculando…".
            self.status_label.setText(t("replay.click_load_hint"))
            return
        start, dur = win
        self._set_start_dt(
            QDateTime.fromSecsSinceEpoch(int(start), Qt.OffsetFromUTC, 0))
        self.dur_spin.setValue(int(dur))
        dist = self._event_dist_deg
        self.status_label.setText(
            t("replay.window_autoset",
              dist=f"{dist:.1f}" if dist is not None else "—"))

    def _set_start_dt(self, qdt) -> None:
        """Fija la fecha de inicio de forma PROGRAMÁTICA (sin que se interprete
        como un cambio manual del usuario que limpiaría el contexto de evento)."""

        self._dt_programmatic = True
        try:
            self.start_dt.setDateTime(qdt)
        finally:
            self._dt_programmatic = False

    def _on_start_dt_changed(self, *_a) -> None:
        """El usuario cambió la fecha A MANO → modo búsqueda histórica
        independiente: deja de "revisar" ese evento (quita banner + TauP). Los
        cambios programáticos (prefill/catálogo/sugerir-ventana) van protegidos
        por ``_dt_programmatic`` y no entran aquí."""

        if self._dt_programmatic:
            return
        if (self._event is None and not self._event_name
                and not self._event_station_mode):
            return
        self._event = None
        self._event_name = ""
        self._event_station_mode = False
        self._event_dist_deg = None
        self._update_event_banner()
        try:
            self._update_station_display()
            self._update_station_hint()
        except (RuntimeError, AttributeError):
            pass

    def _update_event_banner(self) -> None:
        if self._event is not None and self._event_name:
            self._event_banner.setText(
                t("replay.event_banner",
                  name=self._event_name, station=f"{self._net}.{self._sta}"))
            self._event_banner.setVisible(True)
        else:
            self._event_banner.clear()
            self._event_banner.setVisible(False)

    # ------------------------------------------------------------------
    # Botones
    # ------------------------------------------------------------------
    def _on_download_clicked(self) -> None:
        """Lanza la descarga en un QThread y muestra el overlay."""

        # Limpiar la traza anterior si la había
        self._clear_display()

        net = self._net.strip().upper()
        sta = self._sta.strip().upper()
        loc = self._loc.strip()
        cha = self._cha.strip().upper()
        if not (net and sta and cha):
            self.status_label.setText(t("replay.error.missing_fields"))
            return

        qstart = self.start_dt.dateTime().toUTC()
        py_start = qstart.toPython().replace(tzinfo=timezone.utc)
        py_end = py_start + timedelta(seconds=int(self.dur_spin.value()))

        req = _DownloadRequest(
            network=net, station=sta, location=loc, channel=cha,
            starttime=py_start, endtime=py_end,
        )

        self._overlay.show_loading(
            t("replay.downloading"),
            subtitle=f"{net}.{sta}.{loc or '--'}.{cha}",
        )
        self.download_btn.setEnabled(False)

        self._download_thread = QThread()
        self._download_worker = _DownloadWorker(req)
        self._download_worker.moveToThread(self._download_thread)
        self._download_thread.started.connect(self._download_worker.run)
        self._download_worker.done.connect(self._on_download_done)
        self._download_worker.failed.connect(self._on_download_failed)
        # Cleanup
        self._download_worker.done.connect(self._download_thread.quit)
        self._download_worker.failed.connect(self._download_thread.quit)
        self._download_thread.finished.connect(self._cleanup_download_thread)
        self._download_thread.start()

    @Slot(object)
    def _on_download_done(self, stream) -> None:
        """Dibuja TODA la traza descargada de una vez (navegador estático)."""

        self._overlay.hide_overlay()
        self.download_btn.setEnabled(True)
        self._set_load_cta(False)   # ya cargado: quitar el resalte del botón

        # Stream → arrays Z/N/E alineados + start_ts + sample_rate + duración.
        try:
            z, n, e, start_ts, sr, duration = _stream_to_channels(stream)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Replay: no se pudo procesar el Stream")
            self.status_label.setText(t("replay.error.unexpected", detail=str(exc)))
            return

        if duration <= 0 or all(a is None for a in (z, n, e)):
            self.status_label.setText(t("replay.error.no_traces"))
            return

        label = (
            f"{self._net}.{self._sta} "
            f"@ {self.start_dt.dateTime().toString('yyyy-MM-dd HH:mm')} UTC"
        )
        self.waveform_panel.set_station_label(label)
        # Guardar arrays CRUDOS (sin filtrar, sin rotar) → permite re-filtrar
        # y rotar sin volver a descargar. Guardar el Stream para deconvolución.
        self._loaded_arrays = (z, n, e, float(start_ts), float(sr))
        self._stream = stream
        self._deconv_cache = {}
        self._output = "counts"
        self.output_combo.blockSignals(True)
        self.output_combo.setCurrentIndex(0)
        self.output_combo.blockSignals(False)
        self._rotated = False
        self.rotate_btn.blockSignals(True)
        self.rotate_btn.setChecked(False)
        self.rotate_btn.setEnabled(False)   # hasta tener coords (TauP)
        self.rotate_btn.blockSignals(False)
        self._render()                       # filtra + dibuja + espectrograma
        for b in self._export_buttons:
            b.setEnabled(True)
        self.clear_btn.setEnabled(True)

        self._loaded = True
        self.status_label.setText(
            t("replay.ready", duration=_format_mm_ss(duration)))

        # Reabrir desde el catálogo: re-dibujar los picks P/S guardados (tienen
        # prioridad sobre TauP — son la revisión que el usuario quiere recuperar).
        if self._pending_user_picks:
            self._restore_saved_picks(self._pending_user_picks)
            self._pending_user_picks = None
        # Si se entró desde un sismo del globo, calcular las llegadas
        # teóricas (TauP) en segundo plano y superponerlas.
        elif self._event is not None:
            self._compute_arrivals_async()

    # ------------------------------------------------------------------
    # Render: filtra (banda actual) → [rota] → dibuja + espectrograma. v0.7.7
    # Trabaja sobre los arrays CRUDOS, así que re-filtrar/rotar no re-descarga.
    # ------------------------------------------------------------------
    #: Unidad mostrada para cada salida deconvolucionada.
    _OUTPUT_UNIT = {"VEL": "m/s", "DISP": "m", "ACC": "m/s²"}

    def _render(self) -> None:
        if not self._loaded_arrays:
            return
        z, n, e, start_ts, sr = self._loaded_arrays
        band = (self._cha[:2] or "BH").upper()
        sr_int = max(1, int(round(float(sr))))

        # Base = arrays CRUDOS (counts) o físicos (deconvolución completa).
        unit_override = None
        if self._output != "counts":
            cached = self._deconv_cache.get(self._output)
            if cached is None:
                # Lanzar deconvolución en segundo plano; re-renderiza al estar.
                self.status_label.setText(t("replay.response_computing"))
                self._ensure_deconv(self._output)
                return
            z, n, e = cached
            unit_override = self._OUTPUT_UNIT.get(self._output)

        # Filtrar con la banda vigente, a la frecuencia de muestreo REAL.
        proc = WaveformProcessor(sample_rate_hz=sr_int, filt=self._filt)
        zf = proc.apply(z) if z is not None else None
        nf = proc.apply(n) if n is not None else None
        ef = proc.apply(e) if e is not None else None

        # Rotar las horizontales si procede.
        h1_label, h2_label = f"{band}N", f"{band}E"
        if self._rotated:
            baz = self._back_azimuth()
            if baz is not None and nf is not None and ef is not None:
                from shakevision.processing.measurements import rotate_ne_rt
                nf, ef = rotate_ne_rt(nf, ef, baz)
                h1_label, h2_label = f"{band}R", f"{band}T"

        self.waveform_panel.set_amp_unit_override(unit_override)
        self.waveform_panel.load_static(zf, nf, ef, start_ts, sr)
        self.waveform_panel.set_channel_labels(f"{band}Z", h1_label, h2_label)
        self.spectrogram_panel.set_channel(f"{band}Z")
        # Arrays mostrados → exportar CSV lo que se ve (filtrado/rotado/físico).
        self._display_arrays = (zf, nf, ef, start_ts, sr)
        self._reapply_arrivals()
        self._render_spectrogram(zf, nf, ef, sr_int, start_ts)

    # ------------------------------------------------------------------
    # Salida física (deconvolución completa del Stream) — v0.7.7
    # ------------------------------------------------------------------
    def _on_output_changed(self, _idx: int) -> None:
        self._output = self.output_combo.currentData() or "counts"
        self._render()

    def _ensure_deconv(self, output: str) -> None:
        """Lanza (si hace falta) la deconvolución completa en segundo plano."""

        if self._stream is None or self._deconv_pending == output:
            return
        self._deconv_pending = output
        net, sta = self._net.strip().upper(), self._sta.strip().upper()
        loc = self._loc.strip() or "--"
        band = (self._cha[:2] or "BH").upper()
        import threading

        def _work() -> None:
            arrays = None
            try:
                arrays = self._deconvolve(output, net, sta, loc, band)
            except Exception:  # noqa: BLE001
                logger.debug("Replay: deconvolución falló", exc_info=True)
            self._deconv_ready.emit((output, arrays))

        threading.Thread(target=_work, name="replay-deconv", daemon=True).start()

    def _deconvolve(self, output, net, sta, loc, band):
        """Quita la respuesta de TODO el Stream (ObsPy empareja por canal, así
        que BH1/BH2 funcionan) y devuelve arrays físicos (z, n, e) o ``None``."""

        if self._stream is None:
            return None
        if self._response_service is None:
            self._response_service = ResponseService()
        inv = self._response_service.inventory_for(net, sta, loc, f"{band}?")
        if inv is None:
            return None
        st = self._stream.copy()
        st.remove_response(inventory=inv, output=output,
                           water_level=60, taper=True)
        z, n, e, _ts, _sr, _dur = _stream_to_channels(st)
        return (z, n, e)

    def _on_deconv_ready(self, payload) -> None:
        output, arrays = payload
        self._deconv_pending = None
        if arrays is None:
            # Falló (sin metadata/red) → volver a counts.
            self.status_label.setText(t("analysis.response_fail"))
            self._output = "counts"
            self.output_combo.blockSignals(True)
            self.output_combo.setCurrentIndex(0)
            self.output_combo.blockSignals(False)
            self._render()
            return
        self._deconv_cache[output] = arrays
        if output == self._output:
            self._render()
            self.status_label.setText(t("analysis.response_ok"))

    def _render_spectrogram(self, zf, nf, ef, sr_int: int,
                            start_ts: Optional[float] = None) -> None:
        try:
            zc = next((a for a in (zf, nf, ef) if a is not None and a.size), None)
            if zc is not None:
                spec = SpectrumComputer(sample_rate_hz=sr_int).compute(zc)
                if spec is not None:
                    self.spectrogram_panel.update_from_spectrum(
                        spec, t0_abs=start_ts)
        except Exception:  # noqa: BLE001
            logger.debug("Replay: espectrograma estático omitido", exc_info=True)

    def _on_replay_filter_changed(self, *_a) -> None:
        """Filtro PROPIO de Replay (v0.8.0): reconstruye ``_filt`` desde sus
        controles y re-filtra la traza ya cargada (sin re-descargar)."""

        from shakevision.config import FilterConfig
        self._filt = FilterConfig(
            enabled=bool(self.filt_check.isChecked()),
            lowcut_hz=float(self.filt_low.value()),
            highcut_hz=float(self.filt_high.value()),
            order=int(getattr(self._filt, "order", 4)),
        )
        if self._loaded_arrays:
            self._render()

    def on_filter_changed(self, cfg) -> None:
        """(Legado) Filtro de la barra lateral. v0.8.0: Replay ya NO está
        cableado a esto (tiene filtro propio); se conserva por compatibilidad."""

        self._filt = cfg
        if self._loaded_arrays:
            self._render()

    def _update_psd(self) -> None:
        """Recalcula la PSD (Welch) del tramo seleccionado en el canal Z."""

        from shakevision.processing.measurements import welch_psd
        seg, fs = self.waveform_panel.selected_segment("Z")
        if seg is None or len(seg) < 8:
            self.spectrum_panel.clear()
            return
        freqs, psd = welch_psd(seg, fs)
        self.spectrum_panel.update_psd(freqs, psd)

    def _reapply_arrivals(self) -> None:
        # load_static limpia los marcadores; re-superponer las llegadas.
        if self._last_arrivals:
            try:
                self.waveform_panel.set_phase_markers(self._last_arrivals)
            except (RuntimeError, AttributeError):
                pass

    def _back_azimuth(self):
        """Back-azimuth (estación→fuente, grados) o ``None`` si falta info."""

        if not (self._event and self._station_coords):
            return None
        try:
            from obspy.geodetics import gps2dist_azimuth
            st_lat, st_lon = self._station_coords
            _, _, baz = gps2dist_azimuth(
                self._event["lat"], self._event["lon"], st_lat, st_lon)
            return float(baz)
        except Exception:  # noqa: BLE001
            logger.debug("Replay: back-azimuth falló", exc_info=True)
            return None

    def _on_rotate_toggled(self, checked: bool) -> None:
        self._rotated = bool(checked)
        self._render()

    def _on_toggle_spectrogram(self, on: bool) -> None:
        try:
            self.spectrogram_panel.setVisible(bool(on))
        except (RuntimeError, AttributeError):
            pass

    def _on_toggle_psd(self, on: bool) -> None:
        try:
            self.spectrum_panel.setVisible(bool(on))
        except (RuntimeError, AttributeError):
            pass

    # ------------------------------------------------------------------
    # Llegadas teóricas (TauP) — segundo plano, defensivo. v0.7.7.
    # ------------------------------------------------------------------
    def _compute_arrivals_async(self) -> None:
        ev = self._event
        if not ev:
            return
        net, sta = self._net.strip().upper(), self._sta.strip().upper()
        loc = self._loc.strip() or "--"
        cha = self._cha.strip().upper() or "BHZ"
        if cha.endswith("?") or cha.endswith("*"):
            cha = cha[:-1] + "Z"
        import threading

        def _work() -> None:
            try:
                arrivals = self._taup_arrivals(ev, net, sta, loc, cha)
            except Exception:  # noqa: BLE001
                logger.debug("Replay: TauP falló", exc_info=True)
                arrivals = []
            self._arrivals_ready.emit(arrivals)

        threading.Thread(target=_work, name="replay-taup", daemon=True).start()

    def _taup_arrivals(self, ev: dict, net: str, sta: str, loc: str, cha: str):
        """Devuelve ``[(label, abs_ts, color), …]`` con P/S teóricas, o ``[]``.

        Necesita coordenadas de la estación (de StationXML) + las del evento.
        Usa el modelo iasp91. Todo defensivo: cualquier fallo → ``[]``.
        """

        if self._response_service is None:
            self._response_service = ResponseService()
        coords = self._response_service.coordinates_for(net, sta, loc, cha)
        if coords is None:
            return []
        # Guardar para el back-azimuth de la rotación ZNE→ZRT.
        self._station_coords = coords
        st_lat, st_lon = coords
        from obspy.geodetics import locations2degrees
        from obspy.taup import TauPyModel

        dist_deg = locations2degrees(ev["lat"], ev["lon"], st_lat, st_lon)
        self._event_dist_deg = float(dist_deg)   # distancia epicentral
        model = TauPyModel(model="iasp91")
        arr = model.get_travel_times(
            source_depth_in_km=ev["depth_km"], distance_in_degree=dist_deg,
            phase_list=["P", "p", "S", "s"])
        out: list[tuple[str, float, str]] = []
        first_p = next((a for a in arr if a.name in ("P", "p")), None)
        first_s = next((a for a in arr if a.name in ("S", "s")), None)
        if first_p is not None:
            out.append(("P", ev["origin_ts"] + float(first_p.time), "#43d17a"))
        if first_s is not None:
            out.append(("S", ev["origin_ts"] + float(first_s.time), "#ff5ad6"))
        return out

    def _window_bounds(self):
        """``(t0, t1)`` Unix de la traza cargada, o ``None``."""

        if not self._loaded_arrays:
            return None
        z, n, e, start_ts, sr = self._loaded_arrays
        length = max((len(a) for a in (z, n, e) if a is not None), default=0)
        if length == 0 or sr <= 0:
            return None
        return float(start_ts), float(start_ts) + (length - 1) / float(sr)

    def _apply_arrivals(self, arrivals) -> None:
        arrivals = list(arrivals) if arrivals else []
        bounds = self._window_bounds()
        # Solo mostramos las llegadas que CAEN dentro de la ventana cargada
        # (si no, aparecían flotando lejos del dato — caso teleseísmico, P/S
        # llegan mucho después del origen).
        in_win, out_win = [], []
        if bounds is not None:
            t0, t1 = bounds
            for a in arrivals:
                (in_win if t0 <= a[1] <= t1 else out_win).append(a)
        else:
            in_win = arrivals
        self._last_arrivals = in_win
        if in_win:
            try:
                self.waveform_panel.set_phase_markers(in_win)
            except (RuntimeError, AttributeError):
                pass

        # Estado: distancia epicentral + aviso si alguna fase quedó fuera.
        dist = getattr(self, "_event_dist_deg", None)
        dist_txt = f"{dist:.1f}" if dist is not None else "—"
        if in_win:
            msg = t("replay.arrivals_shown", dist=dist_txt)
        elif arrivals and bounds is not None:
            # Todas fuera: decir cuánto después del inicio llega la primera.
            t0 = bounds[0]
            offs = min(a[1] for a in arrivals) - t0
            msg = t("replay.arrivals_outside",
                    dist=dist_txt, secs=f"{offs:.0f}")
        else:
            msg = ""
        if msg:
            self.status_label.setText(msg)

        # Habilitar rotación ZNE→ZRT si tenemos back-azimuth (evento + coords
        # de estación) y la traza tiene horizontales.
        has_horiz = bool(
            self._loaded_arrays
            and self._loaded_arrays[1] is not None
            and self._loaded_arrays[2] is not None)
        self.rotate_btn.setEnabled(
            bool(self._event and self._station_coords and has_horiz))

    @Slot(str)
    def _on_download_failed(self, msg: str) -> None:
        self._overlay.hide_overlay()
        self.download_btn.setEnabled(True)
        self.status_label.setText(msg)

    # ------------------------------------------------------------------
    # Unidades físicas (m/s) — igual que en el Live, pero con la estación
    # del formulario de Replay.  v0.7.7.
    # ------------------------------------------------------------------
    def _on_units_requested(self, use_velocity: bool) -> None:
        if not use_velocity:
            self.waveform_panel.set_units(False)
            return
        net = self._net.strip().upper()
        sta = self._sta.strip().upper()
        loc = self._loc.strip() or "--"
        cha = self._cha.strip().upper() or "BHZ"
        # Resolver el canal vertical concreto (p. ej. "BH?" → "BHZ").
        if cha.endswith("?") or cha.endswith("*"):
            cha = cha[:-1] + "Z"
        import threading

        def _work() -> None:
            if self._response_service is None:
                self._response_service = ResponseService()
            sens = self._response_service.sensitivity_for(net, sta, loc, cha)
            self._sensitivity_ready.emit(sens)

        threading.Thread(target=_work, name="replay-resp", daemon=True).start()

    def _apply_sensitivity(self, sens) -> None:
        ok = sens is not None and sens > 0
        try:
            self.waveform_panel.set_units(ok, sens)
        except (RuntimeError, AttributeError):
            pass
        self.status_label.setText(
            t("analysis.response_ok") if ok else t("analysis.response_fail"))

    def _on_duration_preset_clicked(self) -> None:
        """Cambia el spinbox de duración al valor del botón pulsado."""

        btn = self.sender()
        if btn is None:
            return
        seconds = btn.property("seconds")
        if seconds is None:
            return
        self.dur_spin.setValue(int(seconds))

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def _on_clear_clicked(self) -> None:
        """Botón "Limpiar" propio de Replay (desacoplado de Detener)."""

        self.clear_loaded()

    def clear_loaded(self) -> None:
        """Borrón y cuenta nueva de Replay: limpia la traza cargada Y el
        contexto de evento (banner + TauP), y restablece los botones.

        Ya NO la llama el botón Detener del stream en vivo (v0.8.0: Replay es
        independiente de la conexión); la dispara el botón "Limpiar" propio o
        usos internos."""

        self._clear_display()
        self._event = None
        self._event_name = ""
        self._event_station_mode = False
        self._event_dist_deg = None
        self._pending_user_picks = None
        self._update_event_banner()
        self._set_load_cta(False)
        try:
            self.export_btn.setEnabled(False)
            self.clear_btn.setEnabled(False)
        except (RuntimeError, AttributeError):
            pass
        try:
            self._update_station_display()
            self._update_station_hint()
        except (RuntimeError, AttributeError):
            pass
        try:
            self.status_label.clear()
        except (RuntimeError, AttributeError):
            pass

    def _clear_display(self) -> None:
        """Limpia la traza/espectrograma anteriores antes de una descarga."""

        self._loaded = False
        self._loaded_arrays = None
        self._display_arrays = None
        self._last_arrivals = []
        self._station_coords = None
        self._event_dist_deg = None
        self._rotated = False
        self._stream = None
        self._deconv_cache = {}
        self._deconv_pending = None
        self._output = "counts"
        self.output_combo.blockSignals(True)
        self.output_combo.setCurrentIndex(0)
        self.output_combo.blockSignals(False)
        self.rotate_btn.blockSignals(True)
        self.rotate_btn.setChecked(False)
        self.rotate_btn.setEnabled(False)
        self.rotate_btn.blockSignals(False)
        for b in self._export_buttons:
            b.setEnabled(False)
        try:
            self.waveform_panel.reset()
            self.spectrogram_panel.reset()   # v0.8.0 fix: faltaba al limpiar
            self.spectrum_panel.reset()
        except (RuntimeError, AttributeError):
            pass

    # ------------------------------------------------------------------
    # Exportar (PNG / CSV / QuakeML) — v0.7.7
    # ------------------------------------------------------------------
    def _suggested_name(self) -> str:
        stamp = self.start_dt.dateTime().toString("yyyyMMdd_HHmmss")
        return f"{self._net}.{self._sta}_{stamp}"

    def _on_export_png(self) -> None:
        """Guarda una imagen PNG de las trazas (lo que se ve en pantalla)."""

        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, t("replay.button.export_png"),
            f"{self._suggested_name()}.png", "PNG (*.png)")
        if not path:
            return
        try:
            ok = self.waveform_panel.grab().save(path, "PNG")
        except Exception:  # noqa: BLE001
            ok = False
        self.status_label.setText(
            t("replay.export_done") if ok else t("replay.export_fail"))

    def _on_export_csv(self) -> None:
        """Exporta las trazas mostradas (tiempo UTC ISO + Z/N/E o R/T) a CSV."""

        if not self._display_arrays:
            self.status_label.setText(t("replay.export_none"))
            return
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, t("replay.button.export_csv"),
            f"{self._suggested_name()}.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            self._write_csv(path)
            self.status_label.setText(t("replay.export_done"))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Replay: export CSV falló")
            self.status_label.setText(t("replay.export_fail", detail=str(exc)))

    def _write_csv(self, path: str) -> None:
        import csv
        from datetime import datetime, timezone
        import numpy as np

        z, n, e, start_ts, sr = self._display_arrays
        length = max((len(a) for a in (z, n, e) if a is not None), default=0)

        def _col(a):
            if a is None:
                return np.full(length, np.nan, dtype=np.float64)
            a = np.asarray(a, dtype=np.float64)
            if a.size < length:
                out = np.full(length, np.nan)
                out[: a.size] = a
                return out
            return a[:length]

        zc, nc, ec = _col(z), _col(n), _col(e)
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["time_utc", "Z", "N", "E"])
            for i in range(length):
                ts = datetime.fromtimestamp(start_ts + i / sr, tz=timezone.utc)
                w.writerow([ts.isoformat(),
                            f"{zc[i]:.6g}", f"{nc[i]:.6g}", f"{ec[i]:.6g}"])

    def _on_save_catalog(self) -> None:
        """Guarda las fases P/S marcadas en el catálogo local persistente."""

        picks = {}
        try:
            picks = self.waveform_panel.get_picks()
        except (RuntimeError, AttributeError):
            pass
        if not picks:
            self.status_label.setText(t("replay.export_none"))
            return
        from shakevision.services.catalog_store import CatalogStore
        ok = CatalogStore().add_event(
            self._net, self._sta, self._loc, self._cha[:2], picks,
            origin=self._event, description=self._event_name)
        self.status_label.setText(
            t("replay.catalog_saved") if ok else t("replay.export_fail"))

    def load_local_stream(self, path: str, net: str = "", sta: str = "") -> None:
        """Abre una grabación local (MiniSEED) en el navegador estático.

        Reutiliza el mismo pipeline que una descarga (proceso del Stream →
        render). No hay contexto de evento (sin TauP)."""

        try:
            from obspy import read
            stream = read(str(path))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Replay: no se pudo leer %s (%s)", path, exc)
            self.status_label.setText(t("replay.error.no_traces"))
            return
        self._clear_display()
        self._event = None
        self._event_name = ""
        self._update_event_banner()
        if net:
            self._net = net.upper()
        if sta:
            self._sta = sta.upper()
        self._on_download_done(stream)
        # Etiqueta = nombre de fichero (después de _on_download_done, que la
        # sobreescribiría con NET.STA @ hora-del-formulario).
        from pathlib import Path as _P
        self.waveform_panel.set_station_label(_P(str(path)).name)

    def _on_export_quakeml(self) -> None:
        """Exporta los picks P/S manuales como QuakeML (ObsPy)."""

        picks = {}
        try:
            picks = self.waveform_panel.get_picks()
        except (RuntimeError, AttributeError):
            pass
        if not picks:
            self.status_label.setText(t("replay.export_none"))
            return
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, t("replay.button.export_quakeml"),
            f"{self._suggested_name()}.xml", "QuakeML (*.xml)")
        if not path:
            return
        try:
            self._write_quakeml(path, picks)
            self.status_label.setText(t("replay.export_done"))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Replay: export QuakeML falló")
            self.status_label.setText(t("replay.export_fail", detail=str(exc)))

    def _write_quakeml(self, path: str, picks: dict) -> None:
        from obspy import UTCDateTime
        from obspy.core.event import (
            Catalog, Event, Pick, WaveformStreamID, Origin,
        )

        loc = "" if self._loc in ("--", "*") else self._loc
        cha_z = self._cha[:-1] + "Z" if self._cha.endswith(("?", "*")) else self._cha
        ev = Event()
        # Origen (si venimos de un sismo del globo, usamos su tiempo/coords).
        if self._event is not None:
            ev.origins.append(Origin(
                time=UTCDateTime(self._event["origin_ts"]),
                latitude=self._event["lat"], longitude=self._event["lon"],
                depth=self._event["depth_km"] * 1000.0))
        for phase, abs_ts in picks.items():
            cha = cha_z if phase == "P" else (
                self._cha[:-1] + "N" if self._cha.endswith(("?", "*")) else self._cha)
            ev.picks.append(Pick(
                time=UTCDateTime(float(abs_ts)),
                phase_hint=phase,
                waveform_id=WaveformStreamID(
                    network_code=self._net, station_code=self._sta,
                    location_code=loc, channel_code=cha)))
        Catalog(events=[ev]).write(path, format="QUAKEML")

    @Slot()
    def _cleanup_download_thread(self) -> None:
        if self._download_thread is None:
            return
        self._download_thread.wait(2000)
        self._download_thread.deleteLater()
        self._download_thread = None
        if self._download_worker is not None:
            self._download_worker.deleteLater()
            self._download_worker = None

    # ------------------------------------------------------------------
    # Para que ProWindow / MainWindow gestionen el cierre de forma limpia
    # ------------------------------------------------------------------
    def close_resources(self) -> None:
        self._clear_display()
        self._cleanup_download_thread()


# ============================================================
# Helpers
# ============================================================
def _format_mm_ss(seconds: float) -> str:
    s = int(max(0.0, seconds))
    m, s = divmod(s, 60)
    if m >= 60:
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"
