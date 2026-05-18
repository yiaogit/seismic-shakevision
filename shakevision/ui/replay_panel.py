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
import time as _time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDateTimeEdit,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
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
        self._buffer = RingBuffer(
            sample_rate_hz=config.stream.sample_rate_hz,
            buffer_seconds=config.stream.buffer_seconds,
        )
        self._processor = WaveformProcessor(
            sample_rate_hz=config.stream.sample_rate_hz, filt=config.filt,
        )
        self._spectrum = SpectrumComputer(
            sample_rate_hz=config.stream.sample_rate_hz,
        )

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
        form.addWidget(self.net_edit, 0, 1)

        # Station
        self._lbl_sta = QLabel()
        form.addWidget(self._lbl_sta, 0, 2)
        self.sta_edit = QLineEdit("ANMO")
        self.sta_edit.setMaximumWidth(100)
        form.addWidget(self.sta_edit, 0, 3)

        # Location
        self._lbl_loc = QLabel()
        form.addWidget(self._lbl_loc, 0, 4)
        self.loc_edit = QLineEdit("00")
        self.loc_edit.setMaximumWidth(60)
        form.addWidget(self.loc_edit, 0, 5)

        # Channel
        self._lbl_cha = QLabel()
        form.addWidget(self._lbl_cha, 0, 6)
        self.cha_edit = QLineEdit("BH?")
        self.cha_edit.setMaximumWidth(80)
        form.addWidget(self.cha_edit, 0, 7)

        # Start datetime (UTC)
        self._lbl_start = QLabel()
        form.addWidget(self._lbl_start, 1, 0)
        self.start_dt = QDateTimeEdit()
        self.start_dt.setDisplayFormat("yyyy-MM-dd HH:mm:ss 'UTC'")
        self.start_dt.setCalendarPopup(True)
        self.start_dt.setDateTime(
            QDateTime.currentDateTimeUtc().addSecs(-3600)   # hace 1 hora
        )
        form.addWidget(self.start_dt, 1, 1, 1, 3)

        # Duration
        self._lbl_dur = QLabel()
        form.addWidget(self._lbl_dur, 1, 4)
        self.dur_spin = QSpinBox()
        self.dur_spin.setRange(10, 6 * 3600)
        self.dur_spin.setValue(300)
        self.dur_spin.setSuffix(" s")
        form.addWidget(self.dur_spin, 1, 5)

        # Speed
        self._lbl_speed = QLabel()
        form.addWidget(self._lbl_speed, 1, 6)
        self.speed_combo = QComboBox()
        for sp in SPEED_OPTIONS:
            self.speed_combo.addItem(f"×{sp:g}", userData=sp)
        # Seleccionar 1.0
        self.speed_combo.setCurrentIndex(SPEED_OPTIONS.index(DEFAULT_SPEED))
        self.speed_combo.currentIndexChanged.connect(self._on_speed_changed)
        form.addWidget(self.speed_combo, 1, 7)

        root.addLayout(form)

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

        # ─── Barra de progreso del clip ───
        prog_row = QHBoxLayout()
        prog_row.setSpacing(6)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("0:00 / 0:00")
        prog_row.addWidget(self.progress_bar, stretch=1)
        self.cursor_slider = QSlider(Qt.Horizontal)
        self.cursor_slider.setRange(0, 1000)
        self.cursor_slider.setEnabled(False)
        self.cursor_slider.sliderMoved.connect(self._on_seek)
        prog_row.addWidget(self.cursor_slider, stretch=1)
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
        self._source.status_changed.connect(self.status_label.setText)
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

    # ------------------------------------------------------------------
    # Stream loop
    # ------------------------------------------------------------------
    @Slot(object)
    def _on_batch(self, batch: SampleBatch) -> None:
        """Acumula el batch en el buffer interno. El refresh lo pintará."""

        # Reusar el procesador? Por simplicidad, lo aplicamos en el
        # refresh tick (no aquí), igual que MainWindow. Aquí solo
        # escribimos al buffer.
        self._buffer.append(batch)

    @Slot()
    def _on_refresh_tick(self) -> None:
        """30 FPS: lee la ventana visible, filtra y pinta widgets."""

        if self._source is None:
            return
        snapshot = self._buffer.snapshot(
            self._config.stream.display_window_seconds
        )
        if snapshot.times.size == 0:
            return
        filtered = self._processor.apply_snapshot(snapshot)
        self.waveform_panel.update_snapshot(filtered)
        try:
            spec = self._spectrum.compute(filtered.samples.get("Z"))
            if spec is not None:
                self.spectrogram_panel.update_spectrogram(spec)
        except Exception:  # noqa: BLE001
            # Spectrogram puede fallar en ventanas muy cortas; no es crítico
            pass

    @Slot(float, float)
    def _on_progress(self, cursor_s: float, duration_s: float) -> None:
        pct = 0 if duration_s <= 0 else int(1000 * cursor_s / duration_s)
        self.progress_bar.setValue(pct)
        self.progress_bar.setFormat(
            f"{_format_mm_ss(cursor_s)} / {_format_mm_ss(duration_s)}"
        )
        # Solo actualizar el slider si el usuario NO lo está arrastrando
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
        self.cursor_slider.setValue(0)
        self.progress_bar.setValue(0)

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
