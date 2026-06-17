"""Controlador de la canalización Workbench en tiempo real.

v0.7.7 (S1): extraído de ``MainWindow`` (god-object de 1663 líneas). Posee
toda la canalización de forma de onda en vivo y **conduce** una vista
``ProWindow`` (sus paneles), sin referenciar ningún widget del shell.

Diseño
------
* **Posee** la canalización: ``_source / _buffer / _processor /
  _spectrum_computer / _detector / _recorder / _audio_player /
  _refresh_timer / _helicorder_timer / _intensity_smoother /
  _spectrum_frame_skip / _alert_animations / _current_station``.
* **Conduce** la vista vía ``self._view`` (un ``ProWindow``): empuja datos a
  ``self._view.waveform_panel`` etc.
* **No** referencia widgets del shell (status bar, header, labels). Emite
  señales que ``MainWindow`` cablea a sus widgets — manteniendo el
  controlador desacoplado y testeable.
* Lleva su **propio** estado de conexión (``_connected``) en vez de leer el
  texto del label del shell (como hacía el código original).

El traslado preserva el comportamiento 1:1; la lógica de cada método es la
misma que tenía en ``MainWindow`` antes de v0.7.7.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect

from shakevision.i18n import t
from shakevision.processing.buffer import RingBuffer
from shakevision.processing.detector import EventSignal, StaLtaDetector
from shakevision.processing.filters import WaveformProcessor
from shakevision.processing.intensity import (
    IntensitySmoother,
    IntensitySnapshot,
    default_gain_for,
)
from shakevision.processing.recorder import EventRecorder
from shakevision.processing.sonifier import sonify
from shakevision.processing.spectrum import SpectrumComputer
from shakevision.sources import DataSource, MockSource, SampleBatch, SeedLinkSource
from shakevision.ui.animations import make_breathing_glow
from shakevision.ui.audio_player import AudioPlayer
from shakevision.ui.theme import COLOR_ALERT

if TYPE_CHECKING:  # evita import circular en runtime
    from shakevision.config import (
        AppConfig,
        FilterConfig,
        StationPreset,
        TriggerConfig,
    )
    from shakevision.ui.pro_window import ProWindow

logger = logging.getLogger(__name__)

# Periodo de refresco del helicorder (más lento que el oscilograma).
HELICORDER_REFRESH_MS: int = 5000


class WorkbenchController(QObject):
    """Orquesta la canalización Workbench y conduce una vista ``ProWindow``."""

    # ── Señales hacia el shell (MainWindow las cablea a sus widgets) ──
    #: Mensaje para la status bar: (texto, milisegundos; 0 = persistente).
    status_message = Signal(str, int)
    #: Texto final (ya traducido) para el label de latencia.
    latency_text = Signal(str)
    #: Etiqueta de estación para el header (``"RED.ESTACION"``).
    station_changed = Signal(str)
    #: Estado de conexión: (texto, object_name QSS). MainWindow lo traduce
    #: en label inferior + LED del header (ver ``_set_connection_status``).
    connection_status_changed = Signal(str, str)
    #: v0.7.7: sensibilidad (counts/(m/s)) obtenida en un hilo de fondo;
    #: ``None`` si no disponible. Se aplica en el hilo de la UI.
    _sensitivity_ready = Signal(object)

    def __init__(
        self,
        config: "AppConfig",
        view: "ProWindow",
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._view = view

        # v0.7.7: servicio de respuesta instrumental (lazy) + marshaling de
        # la sensibilidad obtenida en hilo de fondo al hilo de la UI.
        self._response_service = None
        self._sensitivity_ready.connect(self._apply_sensitivity)

        # Estación actualmente seleccionada (la primera por defecto)
        self._current_station: "StationPreset" = config.stations[0]

        # Búfer circular compartido entre la fuente y la UI
        self._buffer = RingBuffer(
            sample_rate_hz=config.stream.sample_rate_hz,
            capacity_seconds=config.stream.buffer_seconds,
        )

        # Procesador DSP (detrend + Butterworth pasa-banda).
        self._processor = WaveformProcessor(
            sample_rate_hz=config.stream.sample_rate_hz,
            filt=config.filt,
        )

        # Calculador de espectrograma para el panel inferior derecho
        self._spectrum_computer = SpectrumComputer(
            sample_rate_hz=config.stream.sample_rate_hz
        )

        # Suavizador del PGV para la tarjeta de intensidad (estilo VU meter)
        self._intensity_smoother = IntensitySmoother(
            decay_per_second=0.3,
            refresh_hz=float(config.stream.refresh_fps),
        )

        # Reproductor de audio (sonificación bajo demanda)
        self._audio_player = AudioPlayer(parent=self)
        self._audio_player.playback_started.connect(self._on_playback_started)
        self._audio_player.playback_finished.connect(self._on_playback_finished)
        self._audio_player.playback_failed.connect(self._on_playback_failed)

        # Detector STA/LTA con histéresis
        self._detector = StaLtaDetector(
            sample_rate_hz=config.stream.sample_rate_hz,
            config=config.trigger,
        )

        # Grabador de eventos en MiniSEED
        self._recorder = EventRecorder(
            sample_rate_hz=config.stream.sample_rate_hz,
            pre_event_seconds=config.trigger.pre_event_seconds,
        )

        # Animaciones activas durante una alerta de evento sísmico.
        self._alert_animations: list = []

        # Contador para limitar el cómputo del espectrograma a 1/3 frames.
        self._spectrum_frame_skip: int = 0

        # Fuente de datos activa (None mientras esté desconectado)
        self._source: Optional[DataSource] = None

        # Preset pendiente de reconexión (coalesce de cambios rápidos de
        # estación). Ver on_station_changed / _do_pending_reconnect.
        self._pending_reconnect: Optional["StationPreset"] = None

        # Estado de conexión propio (sustituye la lectura del label del
        # shell que hacía el código original en _on_data_ready).
        self._connected: bool = False

        # Mostrar la estación inicial en la cabecera del panel de ondas.
        self._view.waveform_panel.set_station_label(self._current_station.label)

        # Temporizador independiente para el helicorder (refresco lento)
        self._helicorder_timer = QTimer(self)
        self._helicorder_timer.setInterval(HELICORDER_REFRESH_MS)
        self._helicorder_timer.timeout.connect(self._view.helicorder_panel.refresh)
        self._helicorder_timer.start()

        # Temporizador de refresco de las vistas en vivo (oscilograma…)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(1000 // max(1, config.stream.refresh_fps))
        self._refresh_timer.timeout.connect(self._on_refresh_tick)
        self._refresh_timer.start()

    # ------------------------------------------------------------------
    # API pública leída por el shell
    # ------------------------------------------------------------------
    @property
    def view(self) -> "ProWindow":
        """La vista ``ProWindow`` conducida por este controlador."""

        return self._view

    @property
    def current_station(self) -> "StationPreset":
        """Estación seleccionada actualmente."""

        return self._current_station

    @property
    def has_source(self) -> bool:
        """``True`` si hay una fuente de datos activa."""

        return self._source is not None

    def shutdown(self) -> None:
        """Detiene temporizadores, audio, alerta y la fuente activa.

        Lo llama ``MainWindow.closeEvent``. Equivale al cleanup que antes
        estaba inline en el closeEvent del god-object.
        """

        self._pending_reconnect = None
        self._refresh_timer.stop()
        self._helicorder_timer.stop()
        self._stop_alert_blink()
        self._audio_player.stop()
        # Al cerrar la app: esperar (acotado) a que el hilo SeedLink muera.
        self._stop_source(wait_ms=3000)

    # ------------------------------------------------------------------
    # Slots de control (MainWindow cablea las señales de ProWindow aquí)
    # ------------------------------------------------------------------
    def on_station_changed(self, preset: "StationPreset") -> None:
        """Actualiza la cabecera y, si la fuente está activa, la reinicia."""

        self._current_station = preset
        self._view.waveform_panel.set_station_label(preset.label)
        self.station_changed.emit(f"{preset.network}.{preset.station}")
        self.status_message.emit(
            t("status.station_selected",
              station=f"{preset.network}.{preset.station}"),
            4000,
        )

        # Reiniciar la conexión si ya estaba activa.
        #
        # IMPORTANTE: NO reconectamos de forma síncrona aquí. Este slot se
        # ejecuta dentro de la pila de señales del combo (setCurrentIndex)
        # y, al añadir una estación desde el globo, dentro del callback del
        # puente QWebChannel + un QMessageBox modal. Destruir y recrear un
        # QThread/socket de forma reentrante en ese contexto provoca un
        # cierre inesperado (segfault). Lo diferimos a la siguiente
        # iteración del bucle de eventos, ya sobre una pila limpia.
        if self._source is not None:
            self._pending_reconnect = preset
            QTimer.singleShot(0, self._do_pending_reconnect)

    def _do_pending_reconnect(self) -> None:
        """Ejecuta la reconexión diferida hacia el último preset pedido.

        Coalesce: si el usuario cambió de estación varias veces seguidas,
        solo nos conectamos a la última. Se ejecuta sobre una pila limpia
        del bucle de eventos (ver on_station_changed).
        """

        preset = self._pending_reconnect
        self._pending_reconnect = None
        if preset is None:
            return

        self._stop_source()
        self._buffer.clear()
        self._start_source_for(preset)

    def on_filter_changed(self, cfg: "FilterConfig") -> None:
        """Recibe la nueva configuración de filtro y la propaga al procesador."""

        self._config.filt = cfg
        self._processor.update_filter(cfg)
        if cfg.enabled:
            self.status_message.emit(
                t("status.filter_enabled",
                  low=cfg.lowcut_hz, high=cfg.highcut_hz, order=cfg.order),
                3000,
            )
        else:
            self.status_message.emit(t("status.filter_disabled"), 3000)

    def on_trigger_changed(self, cfg: "TriggerConfig") -> None:
        """Recibe la nueva configuración del detector."""

        self._config.trigger = cfg
        self._detector.update_config(cfg)
        self._recorder.update_pre_event_seconds(cfg.pre_event_seconds)
        self.status_message.emit(
            t("status.trigger_set",
              sta=cfg.sta_seconds, lta=cfg.lta_seconds, th=cfg.threshold_on),
            3000,
        )

    def on_connect_clicked(self) -> None:
        """Arranca la fuente de datos correspondiente al preset actual."""

        if self._source is not None:
            self.status_message.emit(t("status.source_already_active"), 2000)
            return

        self._buffer.clear()
        self._start_source_for(self._current_station)

    def on_disconnect_clicked(self) -> None:
        """Detiene la fuente de datos y limpia la pantalla.

        Pulsar Detener también detiene cualquier sonificación en curso.
        """

        # Cancelar cualquier reconexión diferida pendiente: el usuario
        # pidió desconectar, no reconectar a otra estación.
        self._pending_reconnect = None

        # SIEMPRE detener audio primero (idempotente).
        self._audio_player.stop()

        # v0.7.7: al pulsar Detener, limpiar también la traza histórica
        # cargada en la pestaña Replay (el usuario lo pidió: "detener" = borrón
        # y cuenta nueva de TODO lo cargado, no solo del stream en vivo).
        try:
            self._view.replay_panel.clear_loaded()
        except (RuntimeError, AttributeError):
            pass

        if self._source is None:
            self.status_message.emit(t("status.no_source_active"), 2500)
            return

        self._stop_source()
        self._connected = False
        # v0.7.7: vaciar el búfer compartido + estado DSP. CLAVE: si no, el
        # reloj de refresco (que sigue corriendo) vuelve a leer los datos
        # viejos en el próximo tick y re-dibuja las trazas ya "limpiadas".
        self._buffer.clear()
        self._spectrum_frame_skip = 0
        self.connection_status_changed.emit("Desconectado", "StatusWarn")
        self.latency_text.emit(t("status.latency_none"))
        self._view.waveform_panel.reset()
        self._view.spectrogram_panel.reset()
        self._view.particle_panel.reset()
        self._view.helicorder_panel.reset()
        self._view.intensity_card.reset()
        self._intensity_smoother.reset()
        self._stop_alert_blink()
        self._detector.reset()
        # v0.7.7: ocultar la fila de progreso de conexión.
        try:
            self._view.control_panel.clear_connection_status()
        except (RuntimeError, AttributeError):
            pass
        self.status_message.emit(t("status.acquisition_stopped"), 3000)

    # ------------------------------------------------------------------
    # Modo análisis (v0.7.7): congelar + unidades físicas
    # ------------------------------------------------------------------
    def on_units_toggled(self, use_velocity: bool) -> None:
        """Alterna counts ↔ velocidad (m/s). La sensibilidad se obtiene del
        StationXML de IRIS en un hilo de fondo (no bloquea la UI)."""

        if not use_velocity:
            try:
                self._view.waveform_panel.set_units(False)
            except (RuntimeError, AttributeError):
                pass
            return

        st = self._current_station
        # La estación Demo (XX.MOCK) es sintética: no tiene respuesta
        # instrumental real → m/s no aplica. Avisar y revertir.
        if st.network == "XX":
            self._apply_sensitivity(None)
            return

        from shakevision.config import (
            seedlink_channels_for,
            seedlink_location_for,
        )
        net, sta = st.network, st.station
        loc = (st.location or "").strip() or seedlink_location_for(net)
        cha = seedlink_channels_for(net)[0]          # canal vertical (Z)
        self.status_message.emit(t("analysis.fetching_response"), 0)

        import threading

        def _work() -> None:
            from shakevision.services.response import ResponseService
            if self._response_service is None:
                self._response_service = ResponseService()
            sens = self._response_service.sensitivity_for(net, sta, loc, cha)
            self._sensitivity_ready.emit(sens)

        threading.Thread(target=_work, name="resp-fetch", daemon=True).start()

    def _apply_sensitivity(self, sens) -> None:
        """Aplica la sensibilidad recibida del hilo de fondo (hilo UI)."""

        ok = sens is not None and sens > 0
        try:
            self._view.waveform_panel.set_units(ok, sens)
        except (RuntimeError, AttributeError):
            pass
        if ok:
            self.status_message.emit(t("analysis.response_ok"), 4000)
        else:
            self.status_message.emit(t("analysis.response_fail"), 5000)

    # ------------------------------------------------------------------
    # Gestión de la fuente de datos
    # ------------------------------------------------------------------
    def _start_source_for(self, preset: "StationPreset") -> None:
        """Crea e inicia la fuente apropiada para el preset dado."""

        # Estación simulada: fuente local sin red
        if preset.network == "XX" and preset.station == "MOCK":
            source: DataSource = MockSource(
                sample_rate_hz=self._config.stream.sample_rate_hz,
                station_label=preset.label,
            )
        else:
            from shakevision.config import (
                seedlink_channels_for,
                seedlink_location_for,
                seedlink_server_for,
            )

            if preset.seedlink_host and preset.seedlink_port:
                host, port = preset.seedlink_host, preset.seedlink_port
            elif preset.network == "AM":
                host = self._config.seedlink_host
                port = self._config.seedlink_port
            else:
                host, port = seedlink_server_for(preset.network)

            channels = seedlink_channels_for(preset.network)

            loc = (preset.location or "").strip()
            if loc in ("", "*", "--"):
                loc = seedlink_location_for(preset.network)

            source = SeedLinkSource(
                host=host,
                port=port,
                network=preset.network,
                station=preset.station,
                location=loc,
                channels=channels,
                sample_rate_hz=self._config.stream.sample_rate_hz,
                station_label=preset.label,
            )

        # Conectar señales antes de arrancar para no perder el primer batch
        source.data_ready.connect(self._on_data_ready)
        source.status_changed.connect(self._on_source_status)

        self._source = source
        # v0.7.7: etiquetas del eje izquierdo según la banda REAL de la
        # estación (antes "EH" fijo). El Mock cae en el default BHZ/BHN/BHE.
        try:
            from shakevision.config import seedlink_channels_for as _chs
            zc, nc, ec = _chs(preset.network)
            self._view.waveform_panel.set_channel_labels(zc, nc, ec)
        except (RuntimeError, AttributeError, ValueError):
            pass
        self._connected = False
        # Informar al panel de que hay una fuente activa: a partir de ahora
        # añadir estaciones NO debe cambiar la selección (no cortar el stream).
        self._view.control_panel.set_source_active(True)
        self.connection_status_changed.emit("Conectando…", "StatusWarn")
        # v0.7.7: arrancar el spinner de progreso en el panel de control.
        self._set_panel_progress(t("header.status.connecting"), busy=True)
        source.start()
        # El estado pasará a "Conectado" cuando llegue el primer batch.

    def _stop_source(self, wait_ms: int = 0) -> None:
        """Detiene de forma segura la fuente activa (idempotente).

        ``wait_ms`` solo se usa al cerrar la app (espera acotada, sin
        terminate); en desconexión normal es 0 (asíncrono, no bloquea).
        """

        if self._source is None:
            return

        # PASO 1: quitar la referencia de inmediato (segundo Detener = no-op)
        src = self._source
        self._source = None
        # Ya no hay fuente activa: añadir estaciones vuelve a auto-seleccionar.
        self._view.control_panel.set_source_active(False)

        # Feedback inmediato (stop() puede tardar varios segundos).
        self.status_message.emit(t("status.stopping_source"), 0)

        # PASO 2: desconectar nuestras señales de la fuente — no más
        # callbacks hacia el controlador mientras el hilo se cierra.
        try:
            src.data_ready.disconnect(self._on_data_ready)
            src.status_changed.disconnect(self._on_source_status)
        except (RuntimeError, TypeError):
            pass

        # PASO 3: stop() ahora es ASÍNCRONO (no bloquea la UI ni usa
        # terminate()). La fuente se auto-destruye cuando su hilo termina,
        # así que NO llamamos a deleteLater aquí (causaría usar un objeto
        # que el worker aún referencia mientras el socket se cierra).
        try:
            src.stop(wait_ms=wait_ms)
        except Exception:  # noqa: BLE001
            logger.exception(
                "Excepción al detener la fuente; continuando con cleanup."
            )

        self.status_message.emit(t("status.source_stopped"), 3000)

    # ------------------------------------------------------------------
    # Slots del flujo de datos
    # ------------------------------------------------------------------
    def _on_data_ready(self, batch: SampleBatch) -> None:
        """Escribe el bloque recibido en el búfer circular."""

        self._buffer.write(
            timestamp_unix=batch.timestamp_unix,
            z=batch.z,
            n=batch.n,
            e=batch.e,
        )
        # Alimentar también el búfer largo del helicorder con el canal Z.
        self._view.helicorder_panel.ingest(batch.z)

        # Al recibir el primer batch, marcar la conexión como activa.
        if not self._connected:
            self._connected = True
            self.connection_status_changed.emit("Conectado", "StatusOk")
            # v0.7.7: streaming — detener el spinner y mostrar "recibiendo
            # datos" (estado estable).
            self._set_panel_progress(
                t("source.status.streaming",
                  station=f"{self._current_station.network}."
                          f"{self._current_station.station}"),
                busy=False,
            )

    def _on_source_status(self, message: str) -> None:
        """Muestra los mensajes de la fuente en la barra de estado + panel."""

        self.status_message.emit(message, 4000)
        # v0.7.7: reflejar el progreso en el panel de control. El spinner
        # gira mientras conectamos (aún sin primer paquete) y se detiene en
        # los mensajes de error (marcados con ❌ en todos los idiomas).
        busy = (not self._connected) and ("❌" not in message)
        self._set_panel_progress(message, busy=busy)

    # ------------------------------------------------------------------
    def _set_panel_progress(self, text: str, busy: bool) -> None:
        """Actualiza la fila spinner+estado del ControlPanel (defensivo)."""

        try:
            self._view.control_panel.set_connection_status(text, busy=busy)
        except (RuntimeError, AttributeError):
            # Vista/panel destruido o sin el método — no romper la UI.
            pass

    def _on_refresh_tick(self) -> None:
        """Lee la última ventana del búfer, la procesa y refresca las vistas."""

        # Si no hay datos aún, no hace falta repintar.
        if self._buffer.total_written == 0:
            return

        # 1. Leer la ventana de visualización del búfer circular.
        raw = self._buffer.read_window(
            seconds=self._config.stream.display_window_seconds
        )

        # 2. Pasarla por la cadena DSP (detrend + Butterworth pasa-banda).
        processed = self._processor.apply_snapshot(raw)

        # 3. Pintar las trazas — solo si la VENTANA Pro está visible.
        if self._view.isVisible():
            if self._view.is_live_subtab_visible():
                self._view.waveform_panel.update_from_snapshot(processed)
                # Espectrograma: solo cada 3 frames (≈ 10 Hz).
                self._spectrum_frame_skip = (self._spectrum_frame_skip + 1) % 3
                if self._spectrum_frame_skip == 0:
                    spectrum = self._spectrum_computer.compute(
                        processed.samples["Z"]
                    )
                    self._view.spectrogram_panel.update_from_spectrum(spectrum)
            elif self._view.is_particle_subtab_visible():
                self._view.particle_panel.update_from_snapshot(processed)
        # La pestaña helicorder se refresca con su propio temporizador.

        # 3b. Actualizar la tarjeta de intensidad — siempre visible.
        gain = default_gain_for(
            self._current_station.network, self._current_station.station
        )
        intensity_snap = IntensitySnapshot.from_samples(
            samples=processed.samples["Z"],
            gain_cm_s_per_count=gain,
            smoother=self._intensity_smoother,
        )
        self._view.intensity_card.update_from_snapshot(intensity_snap)

        # 5. Detección STA/LTA y, si dispara, grabación + alerta.
        result = self._detector.process(processed)
        # v0.7.7: lectura en vivo del cft en la barra del oscilograma (ayuda
        # a ajustar el umbral sin adivinar).
        try:
            self._view.waveform_panel.set_cft(
                result.cft_max, self._config.trigger.threshold_on)
        except (RuntimeError, AttributeError):
            pass
        if result.signal == EventSignal.TRIGGERED:
            self._on_event_triggered(result.cft_max)
        elif result.signal == EventSignal.RELEASED:
            self._on_event_released()

        # Actualizar la latencia entre la última muestra y "ahora".
        latency_s = max(0.0, time.time() - raw.latest_timestamp_unix)
        if latency_s < 10.0:
            self.latency_text.emit(
                t("status.latency_ms", value=latency_s * 1000)
            )
        else:
            self.latency_text.emit(t("status.latency_s", value=latency_s))

    # ------------------------------------------------------------------
    # Sonificación bajo demanda
    # ------------------------------------------------------------------
    def on_listen_clicked(self, seconds: int, speed_factor: int) -> None:
        """Toma la última ventana del búfer y la reproduce acelerada (toggle)."""

        if self._audio_player.is_playing:
            self._audio_player.stop()
            return

        if self._buffer.total_written == 0:
            self.status_message.emit(t("status.no_audio_yet"), 4000)
            return

        # Leer la ventana solicitada (canal Z, el más representativo)
        snap = self._buffer.read_window(seconds=float(seconds))
        z = snap.samples.get("Z")
        if z is None or z.size == 0:
            self.status_message.emit(t("status.empty_channel"), 3000)
            return

        # Sonificar y reproducir
        result = sonify(
            samples=z,
            input_rate_hz=self._config.stream.sample_rate_hz,
            speed_factor=float(speed_factor),
        )
        if result.audio.size == 0:
            self.status_message.emit(t("status.no_audio_generated"), 3000)
            return

        self._audio_player.play(result.audio, result.audio_rate_hz)
        self.status_message.emit(
            t("status.playing_clip",
              seconds=seconds, speed=speed_factor,
              duration=result.audio_duration_s),
            int(result.audio_duration_s * 1000) + 1500,
        )
        # Métrica local: tiempo total escuchado.
        try:
            from shakevision.services.usage_tracker import UsageTracker
            UsageTracker.record_audio_played(result.audio_duration_s)
        except Exception:  # noqa: BLE001 — métricas nunca rompen UI
            logger.debug("UsageTracker.record_audio_played falló",
                         exc_info=True)

    def _on_playback_started(self) -> None:
        """Mientras suena el clip, el botón se convierte en "Parar"."""

        self._view.control_panel.set_listen_button_enabled(
            True, label=t("controls.sound.stop_playing")
        )

    def _on_playback_finished(self) -> None:
        """Restaura el botón al terminar el clip + notifica al usuario."""

        self._view.control_panel.set_listen_button_enabled(True)
        self.status_message.emit(t("status.playback_finished"), 2500)

    def _on_playback_failed(self, message: str) -> None:
        """Muestra el error y restaura el botón."""

        text = t(message) if message.startswith("audio.error.") else message
        self.status_message.emit(t("status.audio_error", message=text), 5000)
        self._view.control_panel.set_listen_button_enabled(True)

    # ------------------------------------------------------------------
    # Manejo de eventos sísmicos detectados
    # ------------------------------------------------------------------
    def _on_event_triggered(self, cft_max: float) -> None:
        """El detector ha cruzado el umbral: alerta visual + grabación."""

        self._start_alert_blink()
        self.status_message.emit(
            t("status.event_detected", cft=cft_max), 8000,
        )
        # v0.7.7: si el usuario activó ⚡ (auto-análisis), congelar y marcar
        # el evento para analizarlo. No-op si ⚡ está apagado.
        try:
            self._view.waveform_panel.on_trigger(cft_max)
        except (RuntimeError, AttributeError):
            pass

        # Lanzar la grabación del MiniSEED en este mismo tick.
        try:
            result = self._recorder.record_event(
                buffer=self._buffer,
                network=self._current_station.network,
                station=self._current_station.station,
                location=self._current_station.location,
                trigger_time_unix=time.time(),
            )
        except Exception as exc:  # pragma: no cover - red de seguridad
            self.status_message.emit(
                t("status.event_save_failed", error=str(exc)), 6000,
            )
            return

        if result.success and result.path is not None:
            self.status_message.emit(
                t("status.event_saved", path=str(result.path)), 8000,
            )
        else:
            self.status_message.emit(
                t("status.event_save_failed", error=str(result.error)), 6000,
            )

    def _on_event_released(self) -> None:
        """El detector ha bajado del umbral de salida."""

        self._stop_alert_blink()
        self.status_message.emit(t("status.event_ended"), 4000)

    # ------------------------------------------------------------------
    # Animación de alerta (borde rojo + halo pulsante sobre los paneles)
    # ------------------------------------------------------------------
    def _start_alert_blink(self) -> None:
        """Inicia la respiración: borde rojo fijo + halo difuso pulsante."""

        if self._alert_animations:
            return  # Ya hay alerta activa, no apilamos animaciones

        self._apply_alert_property(True)

        for panel in (self._view.waveform_panel, self._view.spectrogram_panel):
            effect = QGraphicsDropShadowEffect(panel)
            effect.setColor(QColor(COLOR_ALERT))
            effect.setOffset(0, 0)
            effect.setBlurRadius(8.0)
            panel.setGraphicsEffect(effect)

            anim = make_breathing_glow(
                effect, b"blurRadius", low=8.0, high=32.0, duration_ms=1400
            )
            anim.start()
            self._alert_animations.append((panel, effect, anim))

    def _stop_alert_blink(self) -> None:
        """Detiene la respiración y limpia los efectos visuales."""

        for panel, _effect, anim in self._alert_animations:
            anim.stop()
            panel.setGraphicsEffect(None)
        self._alert_animations.clear()
        self._apply_alert_property(False)

    def _apply_alert_property(self, on: bool) -> None:
        """Activa/desactiva la propiedad ``alert`` de los paneles (QSS)."""

        for panel in (self._view.waveform_panel, self._view.spectrogram_panel):
            panel.setProperty("alert", "true" if on else "false")
            style = panel.style()
            if style is not None:
                style.unpolish(panel)
                style.polish(panel)
