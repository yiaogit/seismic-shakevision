"""
Panel de **reproducción histórica** (Pro tab #4).

Permite al usuario:
  1. Elegir una estación (manual N.S.L.C. o uno de los presets recientes).
  2. Elegir una ventana temporal (start datetime UTC + duración).
  3. Pulsar "Download" → llama a ``DataselectClient`` en un hilo.
  4. Ver el progreso, y al terminar arrancar la reproducción con la
     velocidad elegida (½× – 60×).
  5. Pausar / continuar / detener / ajustar velocidad en vivo.

El panel es **independiente** del flujo Live: tiene su propio
RingBuffer, WaveformProcessor, SpectrumComputer y QTimer. Así no
interfiere con la sesión live en marcha (un usuario puede tener
ambos abiertos a la vez).

Dependencias UI reutilizadas: WaveformPanel, SpectrogramPanel,
LoadingOverlay (mismos widgets que usa el Live tab).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDateTimeEdit,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import QDateTime

from shakevision.config import AppConfig, seedlink_channels_for, seedlink_location_for
from shakevision.i18n import LocaleService, t
from shakevision.processing.buffer import RingBuffer
from shakevision.processing.filters import WaveformProcessor
from shakevision.processing.spectrum import SpectrumComputer
from shakevision.services.dataselect import (
    DataselectClient,
    DataselectError,
    NoDataAvailable,
)
from shakevision.sources.replay import SPEED_OPTIONS, DEFAULT_SPEED, ReplaySource
from shakevision.sources.base import SampleBatch
from shakevision.ui.loading_overlay import LoadingOverlay
from shakevision.ui.spectrogram_widget import SpectrogramPanel
from shakevision.ui.waveform_widget import WaveformPanel

logger = logging.getLogger(__name__)


# Frecuencia de refresco UI dentro del panel de reproducción.
_REFRESH_FPS: int = 30
_REFRESH_INTERVAL_MS: int = int(1000 / _REFRESH_FPS)


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

    def __init__(self, config: AppConfig, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._config = config
        self._source: Optional[ReplaySource] = None
        self._download_thread: Optional[QThread] = None
        self._download_worker: Optional[_DownloadWorker] = None

        # Buffer/Processor/Spectrum independientes del Live tab.
        # Nota: el RingBuffer del proyecto usa `capacity_seconds`, no
        # `buffer_seconds`. Mantener el nombre alineado con processing/buffer.py.
        self._buffer = RingBuffer(
            sample_rate_hz=config.stream.sample_rate_hz,
            capacity_seconds=config.stream.buffer_seconds,
        )
        self._processor = WaveformProcessor(
            sample_rate_hz=config.stream.sample_rate_hz, filt=config.filt,
        )
        self._spectrum = SpectrumComputer(
            sample_rate_hz=config.stream.sample_rate_hz,
        )
        # Cuenta cada cuántos frames refrescamos espectrograma (igual
        # que MainWindow: 30 FPS para waveform / 10 FPS para spectrum).
        self._spectrum_frame_skip = 0

        self._build_ui()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(_REFRESH_INTERVAL_MS)
        self._refresh_timer.timeout.connect(self._on_refresh_tick)

        LocaleService.language_changed_signal().connect(self._retranslate)

    # ------------------------------------------------------------------
    # Construcción de UI
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # ─── Formulario superior ───
        form = QGridLayout()
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(6)

        # Network
        self._lbl_net = QLabel()
        form.addWidget(self._lbl_net, 0, 0)
        self.net_edit = QLineEdit("IU")
        self.net_edit.setMaximumWidth(60)
        self.net_edit.setToolTip(t("replay.tooltip.network"))
        form.addWidget(self.net_edit, 0, 1)

        # Station
        self._lbl_sta = QLabel()
        form.addWidget(self._lbl_sta, 0, 2)
        self.sta_edit = QLineEdit("ANMO")
        self.sta_edit.setMaximumWidth(100)
        self.sta_edit.setToolTip(t("replay.tooltip.station"))
        form.addWidget(self.sta_edit, 0, 3)

        # Location
        self._lbl_loc = QLabel()
        form.addWidget(self._lbl_loc, 0, 4)
        self.loc_edit = QLineEdit("00")
        self.loc_edit.setMaximumWidth(60)
        self.loc_edit.setToolTip(t("replay.tooltip.location"))
        form.addWidget(self.loc_edit, 0, 5)

        # Channel
        self._lbl_cha = QLabel()
        form.addWidget(self._lbl_cha, 0, 6)
        self.cha_edit = QLineEdit("BH?")
        self.cha_edit.setMaximumWidth(80)
        self.cha_edit.setToolTip(t("replay.tooltip.channel"))
        form.addWidget(self.cha_edit, 0, 7)

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
        self.start_dt.setDisplayFormat("yyyy-MM-dd  HH:mm:ss  'UTC'")
        self.start_dt.setCalendarPopup(True)
        self.start_dt.setKeyboardTracking(True)
        self.start_dt.setDateTime(
            QDateTime.currentDateTimeUtc().addSecs(-3600)
        )
        # Empezar con el cursor en la sección "minutos" (más útil para
        # ajustar precisión que en el año).
        self.start_dt.setCurrentSection(QDateTimeEdit.MinuteSection)
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

        # Speed
        # ──────────────────────────────────────────────────────────────
        # setMinimumWidth/setMinimumContentsLength evita que "×60" se
        # corte. El popup también respeta el ancho.
        self._lbl_speed = QLabel()
        form.addWidget(self._lbl_speed, 1, 6)
        self.speed_combo = QComboBox()
        for sp in SPEED_OPTIONS:
            self.speed_combo.addItem(f"×{sp:g}", userData=sp)
        self.speed_combo.setCurrentIndex(SPEED_OPTIONS.index(DEFAULT_SPEED))
        self.speed_combo.currentIndexChanged.connect(self._on_speed_changed)
        self.speed_combo.setMinimumWidth(96)
        self.speed_combo.setSizeAdjustPolicy(
            QComboBox.AdjustToContents
        )
        form.addWidget(self.speed_combo, 1, 7)

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
        ):
            btn = QPushButton(label)
            btn.setMaximumWidth(70)
            btn.setProperty("seconds", seconds)
            btn.clicked.connect(self._on_duration_preset_clicked)
            preset_row.addWidget(btn)
            self._duration_preset_buttons.append(btn)
        preset_row.addStretch(1)
        root.addLayout(preset_row)

        # ─── Botonera (Download / Play / Pause / Stop) ───
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self.download_btn = QPushButton()
        self.download_btn.clicked.connect(self._on_download_clicked)
        btn_row.addWidget(self.download_btn)

        self.play_btn = QPushButton()
        self.play_btn.setEnabled(False)
        self.play_btn.clicked.connect(self._on_play_clicked)
        btn_row.addWidget(self.play_btn)

        self.pause_btn = QPushButton()
        self.pause_btn.setEnabled(False)
        self.pause_btn.clicked.connect(self._on_pause_clicked)
        btn_row.addWidget(self.pause_btn)

        self.stop_btn = QPushButton()
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop_clicked)
        btn_row.addWidget(self.stop_btn)

        btn_row.addStretch(1)

        self.status_label = QLabel("")
        self.status_label.setObjectName("StatusValue")
        btn_row.addWidget(self.status_label)

        root.addLayout(btn_row)

        # ─── Visualización: waveform + spectrogram ───
        splitter = QSplitter(Qt.Vertical, parent=self)
        self.waveform_panel = WaveformPanel(parent=splitter)
        self.spectrogram_panel = SpectrogramPanel(parent=splitter)
        splitter.addWidget(self.waveform_panel)
        splitter.addWidget(self.spectrogram_panel)
        splitter.setStretchFactor(0, 65)
        splitter.setStretchFactor(1, 35)
        root.addWidget(splitter, stretch=1)

        # ─── Cursor único de reproducción ───────────────────────────
        # Antes había DOS controles (QProgressBar + QSlider) que se
        # solapaban y confundían al usuario. Ahora hay UN solo QSlider
        # con flancos "tiempo actual" a la izquierda y "duración total"
        # a la derecha, igual que un reproductor de vídeo.
        prog_row = QHBoxLayout()
        prog_row.setSpacing(8)
        self.time_cursor_label = QLabel("0:00")
        self.time_cursor_label.setObjectName("StatusValue")
        self.time_cursor_label.setMinimumWidth(48)
        self.time_cursor_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        prog_row.addWidget(self.time_cursor_label)

        self.cursor_slider = QSlider(Qt.Horizontal)
        self.cursor_slider.setRange(0, 1000)
        self.cursor_slider.setEnabled(False)
        self.cursor_slider.sliderMoved.connect(self._on_seek)
        # También permitimos click directo en una posición (no solo
        # arrastrar): el ratón pulsado se trata como seek inmediato.
        self.cursor_slider.actionTriggered.connect(self._on_slider_action)
        prog_row.addWidget(self.cursor_slider, stretch=1)

        self.time_total_label = QLabel("0:00")
        self.time_total_label.setObjectName("StatusValue")
        self.time_total_label.setMinimumWidth(48)
        prog_row.addWidget(self.time_total_label)
        root.addLayout(prog_row)

        # Overlay para fase de descarga
        self._overlay = LoadingOverlay(self)
        self._overlay.hide_overlay()

        self._retranslate()

    # ------------------------------------------------------------------
    # i18n
    # ------------------------------------------------------------------
    def _retranslate(self) -> None:
        self._lbl_net.setText(t("replay.field.network"))
        self._lbl_sta.setText(t("replay.field.station"))
        self._lbl_loc.setText(t("replay.field.location"))
        self._lbl_cha.setText(t("replay.field.channel"))
        self._lbl_start.setText(t("replay.field.start"))
        self._lbl_dur.setText(t("replay.field.duration"))
        self._lbl_speed.setText(t("replay.field.speed"))
        self.download_btn.setText(t("replay.button.download"))
        self.play_btn.setText(t("replay.button.play"))
        self.pause_btn.setText(t("replay.button.pause"))
        self.stop_btn.setText(t("replay.button.stop"))
        self._lbl_dur_preset.setText(t("replay.field.duration_preset"))
        # Re-aplicar tooltips traducidos
        self.net_edit.setToolTip(t("replay.tooltip.network"))
        self.sta_edit.setToolTip(t("replay.tooltip.station"))
        self.loc_edit.setToolTip(t("replay.tooltip.location"))
        self.cha_edit.setToolTip(t("replay.tooltip.channel"))

    # ------------------------------------------------------------------
    # Sugerencia desde el globo (Pro tab puede usarlo en futuro)
    # ------------------------------------------------------------------
    def prefill_from_event(
        self, network: str, station: str, when: datetime, duration_s: int = 300,
    ) -> None:
        """Rellena formulario a partir de un evento clicado en el globo."""

        self.net_edit.setText(network.upper())
        self.sta_edit.setText(station.upper())
        # Heurística de location/channel basada en la red conocida
        self.loc_edit.setText(seedlink_location_for(network))
        ch = seedlink_channels_for(network)[0]
        # Convertir EHZ → EH?, BHZ → BH? para descargar los 3 componentes
        self.cha_edit.setText(ch[:-1] + "?")
        self.start_dt.setDateTime(
            QDateTime.fromSecsSinceEpoch(
                int(when.replace(tzinfo=timezone.utc).timestamp() - 60),
                Qt.OffsetFromUTC, 0,
            )
        )
        self.dur_spin.setValue(int(duration_s))

    # ------------------------------------------------------------------
    # Botones
    # ------------------------------------------------------------------
    def _on_download_clicked(self) -> None:
        """Lanza la descarga en un QThread y muestra el overlay."""

        # Limpiar source anterior si lo había
        self._teardown_source()

        net = self.net_edit.text().strip().upper()
        sta = self.sta_edit.text().strip().upper()
        loc = self.loc_edit.text().strip()
        cha = self.cha_edit.text().strip().upper()
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
        """Construye ReplaySource y habilita los controles."""

        self._overlay.hide_overlay()
        self.download_btn.setEnabled(True)

        speed = float(self.speed_combo.currentData() or DEFAULT_SPEED)
        label = (
            f"{self.net_edit.text().upper()}.{self.sta_edit.text().upper()} "
            f"@ {self.start_dt.dateTime().toString('yyyy-MM-dd HH:mm')} UTC"
        )

        try:
            self._source = ReplaySource(
                stream=stream, speed=speed, station_label=label, parent=self,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Replay: no se pudo construir ReplaySource")
            self.status_label.setText(t("replay.error.unexpected", detail=str(exc)))
            return

        self._source.data_ready.connect(self._on_batch)
        # ReplaySource emite KEYS i18n ("replay.status.*"); las
        # traducimos con t() antes de mostrarlas. Las keys también
        # admiten {placeholders} para futuras versiones.
        self._source.status_changed.connect(self._on_source_status)
        self._source.progress.connect(self._on_progress)
        self._source.finished.connect(self._on_source_finished)

        self.play_btn.setEnabled(True)
        self.stop_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.cursor_slider.setEnabled(True)
        self.status_label.setText(
            t("replay.ready", duration=_format_mm_ss(self._source.duration_seconds))
        )

    @Slot(str)
    def _on_download_failed(self, msg: str) -> None:
        self._overlay.hide_overlay()
        self.download_btn.setEnabled(True)
        self.status_label.setText(msg)

    def _on_play_clicked(self) -> None:
        if self._source is None:
            return
        if self._source.is_paused:
            self._source.resume()
        else:
            self._source.start()
        self.play_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self._refresh_timer.start()

    def _on_pause_clicked(self) -> None:
        if self._source is None:
            return
        self._source.pause()
        self.play_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)

    def _on_stop_clicked(self) -> None:
        if self._source is None:
            return
        self._source.stop()
        self._refresh_timer.stop()
        self.play_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.cursor_slider.setValue(0)
        self.time_cursor_label.setText("0:00")

    def _on_speed_changed(self, _idx: int) -> None:
        if self._source is None:
            return
        speed = float(self.speed_combo.currentData() or DEFAULT_SPEED)
        self._source.set_speed(speed)

    def _on_seek(self, raw: int) -> None:
        if self._source is None:
            return
        # Slider 0..1000 → 0..duration
        position = (raw / 1000.0) * self._source.duration_seconds
        self._source.seek(position)

    def _on_slider_action(self, action: int) -> None:
        """Permite hacer click directo en la barra para saltar a esa
        posición (no solo arrastrar). Qt envía ``SliderAction`` para
        cualquier interacción, así que filtramos las acciones de
        click (move y SliderPressed) y aplicamos el seek correspondiente.
        """

        # Qt usa enteros enum: 0=NoAction; las acciones útiles son
        # SliderMove, SliderPressed, SliderPageStepAdd/Sub.
        from PySide6.QtWidgets import QAbstractSlider
        if action in (
            QAbstractSlider.SliderPressed,
            QAbstractSlider.SliderPageStepAdd,
            QAbstractSlider.SliderPageStepSub,
        ):
            self._on_seek(self.cursor_slider.sliderPosition())

    def _on_duration_preset_clicked(self) -> None:
        """Cambia el spinbox de duración al valor del botón pulsado."""

        btn = self.sender()
        if btn is None:
            return
        seconds = btn.property("seconds")
        if seconds is None:
            return
        self.dur_spin.setValue(int(seconds))

    @Slot(str)
    def _on_source_status(self, key_or_text: str) -> None:
        """Traduce la clave i18n emitida por ReplaySource y la muestra.

        Si el string no parece una clave (no empieza por ``replay.``)
        se asume texto libre por compatibilidad con código legacy.
        """

        if key_or_text.startswith("replay.status."):
            text = t(key_or_text,
                     label=self._source.station_label if self._source else "",
                     speed=self._source.speed if self._source else 1.0)
        else:
            text = key_or_text
        self.status_label.setText(text)

    # ------------------------------------------------------------------
    # Stream loop
    # ------------------------------------------------------------------
    @Slot(object)
    def _on_batch(self, batch: SampleBatch) -> None:
        """Acumula el batch en el buffer interno. El refresh lo pintará.

        Usa la misma firma de write que MainWindow (timestamp + z/n/e
        separados); pasar el objeto SampleBatch entero no funciona porque
        RingBuffer.write espera kwargs explícitos.
        """

        self._buffer.write(
            timestamp_unix=batch.timestamp_unix,
            z=batch.z,
            n=batch.n,
            e=batch.e,
        )

    @Slot()
    def _on_refresh_tick(self) -> None:
        """30 FPS: lee la ventana visible, filtra y pinta widgets."""

        if self._source is None:
            return
        if self._buffer.total_written == 0:
            return
        raw = self._buffer.read_window(
            seconds=self._config.stream.display_window_seconds
        )
        processed = self._processor.apply_snapshot(raw)
        self.waveform_panel.update_from_snapshot(processed)
        # Spectrogram: 1 de cada 3 frames (≈10 FPS) — patrón idéntico
        # al MainWindow para no saturar SciPy.
        self._spectrum_frame_skip = (self._spectrum_frame_skip + 1) % 3
        if self._spectrum_frame_skip == 0:
            try:
                z_samples = processed.samples.get("Z")
                if z_samples is not None and z_samples.size > 0:
                    spec = self._spectrum.compute(z_samples)
                    if spec is not None:
                        self.spectrogram_panel.update_from_spectrum(spec)
            except Exception:  # noqa: BLE001
                # Espectrograma puede fallar con ventanas muy cortas
                # (FFT exige cierto mínimo de muestras); ignorarlo.
                pass

    @Slot(float, float)
    def _on_progress(self, cursor_s: float, duration_s: float) -> None:
        """Actualiza el cursor único y las etiquetas mm:ss laterales.

        El cursor NO se actualiza si el usuario está arrastrando
        manualmente (sliderDown) para evitar que el "tic tac" del
        clock pelee con el dedo del usuario.
        """

        pct = 0 if duration_s <= 0 else int(1000 * cursor_s / duration_s)
        self.time_cursor_label.setText(_format_mm_ss(cursor_s))
        self.time_total_label.setText(_format_mm_ss(duration_s))
        if not self.cursor_slider.isSliderDown():
            self.cursor_slider.blockSignals(True)
            self.cursor_slider.setValue(pct)
            self.cursor_slider.blockSignals(False)

    @Slot()
    def _on_source_finished(self) -> None:
        self._refresh_timer.stop()
        self.play_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        # No deshabilitamos stop_btn — permite "rebobinar" reseteando.

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def _teardown_source(self) -> None:
        self._refresh_timer.stop()
        if self._source is not None:
            try:
                self._source.stop()
            except Exception:  # noqa: BLE001
                pass
            self._source = None
        # Reset UI
        self.play_btn.setEnabled(False)
        self.pause_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.cursor_slider.setEnabled(False)
        self.cursor_slider.setValue(0)
        self.time_cursor_label.setText("0:00")
        self.time_total_label.setText("0:00")

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
        self._teardown_source()
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
