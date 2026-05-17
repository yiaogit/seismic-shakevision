"""
Ventana principal de ShakeVision.

Reúne en una sola ``QMainWindow``:
  - El panel de control lateral (izquierda).
  - El panel de formas de onda (derecha).
  - Una barra de estado inferior con la latencia y los mensajes.

Flujo de datos
--------------
  1. La fuente activa (``MockSource`` por ahora) corre en un hilo
     trabajador y emite ``SampleBatch`` cada ~100 ms.
  2. ``_on_data_ready`` recibe el batch en el hilo de la UI y lo
     escribe en el búfer circular (``RingBuffer``).
  3. Un ``QTimer`` a 30 FPS lee la última ventana del búfer y la pasa
     al ``WaveformPanel`` para refrescar las tres trazas.
  4. La barra de estado muestra la latencia entre el último timestamp
     escrito y el reloj actual.

Cambiar de estación o pulsar "Detener" detiene la fuente y limpia el
búfer; pulsar "Conectar" instancia la fuente apropiada para el preset
seleccionado.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (
    QFileDialog,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from shakevision import APP_NAME, __version__
from shakevision.config import (
    AppConfig,
    FilterConfig,
    StationPreset,
    TriggerConfig,
)
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
from shakevision.services import FileCache
from shakevision.services.iris import IRISClient
from shakevision.services.shakenet import ShakeNetClient
from shakevision.services.usgs import USGSClient
from shakevision.services.report import ReportGenerator
from shakevision.services.worker import DataRefreshWorker
from shakevision.sources import DataSource, MockSource, SampleBatch, SeedLinkSource
from shakevision.ui.animations import make_breathing_glow, make_fade_in
from shakevision.i18n import LocaleService, t
from shakevision.ui.app_header import AppHeader, ConnectionState
from shakevision.ui.dashboard_view import DashboardPanel
from shakevision.ui.globe_view import GlobePanel
from shakevision.ui.theme import COLOR_ALERT
from shakevision.ui.audio_player import AudioPlayer
from shakevision.ui.pdf_exporter import PdfExporter
from shakevision.ui.macos_native import (
    enhance_macos_window,
    is_macos,
    macos_dependency_hint,
    title_bar_inset_for,
)
from shakevision.ui.pro_window import ProWindow


# Índices de las pestañas de nivel superior (solo 2 tras la
# extracción de Pro a ventana flotante)
TAB_GLOBE: int = 0      # 🌍 Globo (vista por defecto)
TAB_DATA: int = 1       # 📊 Datos

# Periodo de refresco del helicorder (más lento que el oscilograma).
# 24 h cambia muy despacio; cada 5 s es más que suficiente.
HELICORDER_REFRESH_MS: int = 5000


class MainWindow(QMainWindow):
    """Ventana principal de la aplicación."""

    def __init__(self, config: AppConfig) -> None:
        super().__init__()

        # Guardar la configuración mutable (las señales del panel la actualizan)
        self._config = config

        # Estación actualmente seleccionada (la primera por defecto)
        self._current_station: StationPreset = config.stations[0]

        # Búfer circular compartido entre la fuente y la UI
        self._buffer = RingBuffer(
            sample_rate_hz=config.stream.sample_rate_hz,
            capacity_seconds=config.stream.buffer_seconds,
        )

        # Procesador DSP (detrend + Butterworth pasa-banda).
        # Se aplica a la ventana de visualización en cada frame.
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
        # Cada elemento es la tupla (panel, efecto, animación) para
        # poder detenerlas y limpiar los efectos al finalizar.
        self._alert_animations: list = []

        # Contador para limitar el cómputo del espectrograma a 1/3 de
        # los frames. La UI sigue a 30 FPS pero el espectro se actualiza
        # a ~10 Hz, suficiente para percibirlo "en tiempo real" y
        # ahorrando ~5 ms de SciPy por dos de cada tres frames.
        self._spectrum_frame_skip: int = 0

        # Fuente de datos activa (None mientras esté desconectado)
        self._source: Optional[DataSource] = None

        # Configuración básica de la ventana.
        # Tras el rediseño "Globo como protagonista" la ventana es más
        # ancha por defecto para que las gráficas y el mapa respiren.
        self.setWindowTitle(f"{APP_NAME}  v{__version__}")
        self.resize(1500, 950)
        self.setMinimumSize(1200, 800)

        # ----------------------------------------------------------------
        # Construcción del layout
        # ----------------------------------------------------------------
        central = QWidget(self)
        self.setCentralWidget(central)

        # Capa más externa: vertical (header + cuerpo).
        # En macOS dejamos que el contenido pase por debajo de la barra
        # de título nativa (vidrio); para evitar que los semáforos pisen
        # el logo añadimos un margen superior con title_bar_inset_for().
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---- Cabecera global (siempre visible) ----
        self.app_header = AppHeader(
            app_name=APP_NAME, version=__version__, parent=central
        )
        # Reservar espacio para los semáforos en macOS con título transparente
        top_inset = title_bar_inset_for(self) if is_macos() else 0
        if top_inset:
            outer.addSpacing(top_inset)
        outer.addWidget(self.app_header)

        # ---- Contenedor del cuerpo principal ----
        body = QWidget(central)
        outer.addWidget(body, stretch=1)

        root = QHBoxLayout(body)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ─── Diseño actual: 2 pestañas de nivel superior ───
        # El usuario común entra en "🌍 Globo" y ve el mapa; quien
        # quiera datos pulsa "📊 Datos". El banco de trabajo "🔬 Pro"
        # ahora vive en una VENTANA FLOTANTE separada (ProWindow) que
        # se abre con el botón "🔬 Pro" del AppHeader.
        self._tabs = QTabWidget(parent=body)
        self._tabs.setDocumentMode(True)
        self._tabs.setTabPosition(QTabWidget.North)
        self._tabs.currentChanged.connect(self._on_tab_changed)

        # ── Tab 1: Globo 3D ── (vista por defecto, pantalla completa)
        self.globe_panel = GlobePanel(parent=self._tabs)
        self._tabs.addTab(self.globe_panel, t("globe.tab_title"))

        # ── Tab 2: Datos (7 gráficas ECharts, pantalla completa) ──
        self.dashboard_panel = DashboardPanel(parent=self._tabs)
        self._tabs.addTab(self.dashboard_panel, t("dashboard.tab_title"))

        # Globo es la vista por defecto (índice 0)
        self._tabs.setCurrentIndex(0)
        root.addWidget(self._tabs, stretch=1)

        # Animación de fade-in al cambiar de pestaña
        self._fade_in_animation = None

        # ─── Ventana flotante "Pro" ───
        # Instanciada UNA vez al arrancar y oculta. El botón del
        # AppHeader la llama con show_and_focus(); al cerrarla el
        # propio ProWindow intercepta closeEvent y solo se oculta,
        # preservando todo el estado (buffers, helicorder, etc.).
        self.pro_window = ProWindow(config=config)
        # Conectar las 6 señales del ControlPanel (re-emitidas por
        # ProWindow) a los slots existentes de MainWindow.
        self.pro_window.station_changed.connect(self._on_station_changed)
        self.pro_window.filter_changed.connect(self._on_filter_changed)
        self.pro_window.trigger_changed.connect(self._on_trigger_changed)
        self.pro_window.connect_clicked.connect(self._on_connect_clicked)
        self.pro_window.disconnect_clicked.connect(self._on_disconnect_clicked)
        self.pro_window.listen_clicked.connect(self._on_listen_clicked)

        # Atajos cómodos a los paneles internos del banco de trabajo —
        # permiten que el resto de MainWindow siga escribiendo
        # ``self.waveform_panel.update(...)`` sin cambiar.
        self.control_panel = self.pro_window.control_panel
        self.intensity_card = self.pro_window.intensity_card
        self.waveform_panel = self.pro_window.waveform_panel
        self.spectrogram_panel = self.pro_window.spectrogram_panel
        self.helicorder_panel = self.pro_window.helicorder_panel
        self.particle_panel = self.pro_window.particle_panel

        # Mostrar inmediatamente la estación inicial en la cabecera del panel
        self.waveform_panel.set_station_label(self._current_station.label)
        # … y en la barra superior de la app
        self.app_header.set_station(
            f"{self._current_station.network}.{self._current_station.station}"
        )
        self.app_header.set_connection_state(ConnectionState.DISCONNECTED)

        # Botón "🔬 Pro" del AppHeader → mostrar la ventana flotante.
        self.app_header.pro_clicked.connect(self._on_pro_button_clicked)
        # Botón ⚙ → diálogo de preferencias (idioma + zona horaria)
        self.app_header.settings_clicked.connect(self._on_settings_clicked)

        # Temporizador independiente para el helicorder (refresco lento)
        self._helicorder_timer = QTimer(self)
        self._helicorder_timer.setInterval(HELICORDER_REFRESH_MS)
        self._helicorder_timer.timeout.connect(self.helicorder_panel.refresh)
        self._helicorder_timer.start()

        # ----------------------------------------------------------------
        # Barra de estado
        # ----------------------------------------------------------------
        self._status_bar = QStatusBar(self)
        self.setStatusBar(self._status_bar)

        # Etiquetas permanentes (alineadas a la derecha): latencia, estado
        self._latency_label = QLabel(t("status.latency_none"))
        self._latency_label.setObjectName("StatusValue")
        self._connection_label = QLabel(t("header.status.disconnected"))
        self._connection_label.setObjectName("StatusWarn")
        self._status_bar.addPermanentWidget(self._latency_label)
        self._status_bar.addPermanentWidget(self._connection_label)
        self._status_bar.showMessage(t("status.ready"))

        # Re-traducir cuando cambie el idioma: tabs, menús, status bar
        LocaleService.language_changed_signal().connect(self._retranslate)

        # ----------------------------------------------------------------
        # Menú "Archivo" mínimo
        # ----------------------------------------------------------------
        self._build_menus()

        # NOTA: las conexiones señal-slot del ControlPanel ahora se
        # establecen contra ProWindow (que las reemite); ver más arriba
        # en este __init__.

        # ----------------------------------------------------------------
        # Reloj de refresco de UI: lee del búfer a "refresh_fps" Hz
        # ----------------------------------------------------------------
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(1000 // max(1, config.stream.refresh_fps))
        self._refresh_timer.timeout.connect(self._on_refresh_tick)
        self._refresh_timer.start()

        # ----------------------------------------------------------------
        # Capa de servicios externos (USGS + ShakeNet) que alimenta el globo
        # ----------------------------------------------------------------
        self._data_cache = FileCache()
        self._usgs_client = USGSClient(self._data_cache)
        self._shakenet_client = ShakeNetClient(self._data_cache)
        self._iris_client = IRISClient(self._data_cache)
        # Un solo worker alimenta tanto al Globo como al Datos. El
        # periodo per-panel se gestiona en Python (filtrando el catálogo
        # completo del feed más amplio que tengamos en caché). Esta
        # decisión revierte la versión "dos workers" porque introducía
        # una carrera al inicializar QThread/QTimer en paralelo: a
        # veces uno de los dos workers no emitía nunca el primer batch
        # y el overlay del Globo se quedaba para siempre en "Cargando".
        self._data_worker = DataRefreshWorker(
            usgs=self._usgs_client,
            shakenet=self._shakenet_client,
            iris=self._iris_client,    # IRIS/USGS estaciones IU+US
            period="all_month",   # pedimos el feed más amplio para que
                                   # cualquier filtro local (1h/24h/7d)
                                   # pueda extraerse de él sin nueva HTTP.
            network="AM",
            parent=self,
        )

        # Periodos visibles independientes (Python filtra en cliente)
        self._globe_period: str = "all_day"
        self._dashboard_period: str = "all_day"
        # Región seleccionada para el radar PAGER ("all" o nombre país)
        self._dashboard_pager_region: str = "all"

        # Conexiones de datos → ambos paneles reciben siempre el
        # catálogo completo; el filtro temporal sucede en
        # _on_earthquakes_ready usando _filter_for_period().
        self._data_worker.earthquakes_ready.connect(self._on_earthquakes_ready)
        self._data_worker.stations_ready.connect(self.globe_panel.update_stations)
        # _on_stations_ready también empuja el catálogo al dashboard
        # (para el KPI station_summary y el filtro de fuente).
        self._data_worker.stations_ready.connect(self._on_stations_ready)
        self._data_worker.error.connect(self._on_data_error)

        # Caché del último lote de sismos para exportar reporte sin volver
        # a tocar la red (la actualización viene del worker cada 60 s).
        self._latest_earthquakes: list = []
        # Caché de estaciones por (network, code) para resolver clicks
        # del globo a metadatos completos (lat/lng/site_name).
        self._stations_by_nsl: dict[tuple[str, str], object] = {}
        self._report_generator: Optional[ReportGenerator] = None

        # Cada panel cambia su propio periodo, pero ambos comparten el
        # mismo catálogo descargado — el filtrado es local e inmediato.
        self.dashboard_panel.period_changed.connect(
            self._on_dashboard_period_changed
        )
        # Filtro de región para el radar PAGER (exclusivo del dashboard)
        self.dashboard_panel.pager_region_changed.connect(
            self._on_dashboard_pager_region_changed
        )
        self.globe_panel.period_changed.connect(
            self._on_globe_period_changed
        )
        # Click en una estación del globo → diálogo de confirmación →
        # añadir a la lista del ControlPanel de la ventana Pro.
        self.globe_panel.station_clicked.connect(
            self._on_globe_station_clicked
        )

        # Reconectar el botón "Reintentar" de los overlays
        for panel in (self.globe_panel, self.dashboard_panel):
            overlay = getattr(panel, "_overlay", None)
            if overlay is not None:
                overlay.retry_clicked.connect(self._on_retry_data)

        # Arrancar el worker único
        self._data_worker.start_periodic_refresh(
            earthquakes_period_s=60.0,
            stations_period_s=3600.0,
            kick_immediately=True,
        )

    # ------------------------------------------------------------------
    # Construcción de menús
    # ------------------------------------------------------------------
    def _build_menus(self) -> None:
        """Crea la barra de menús superior (re-construible al cambiar idioma)."""

        menu_bar = self.menuBar()
        menu_bar.clear()  # idempotente: permite re-construir tras retranslate

        # Menú Archivo
        self._file_menu = menu_bar.addMenu(t("menu.file"))

        self._export_html_action = QAction(t("menu.file.export_html"), self)
        self._export_html_action.setShortcut("Ctrl+E")
        self._export_html_action.triggered.connect(self._on_export_report)
        self._file_menu.addAction(self._export_html_action)

        self._export_pdf_action = QAction(t("menu.file.export_pdf"), self)
        self._export_pdf_action.setShortcut("Ctrl+Shift+E")
        self._export_pdf_action.triggered.connect(self._on_export_report_pdf)
        self._file_menu.addAction(self._export_pdf_action)

        self._file_menu.addSeparator()

        self._exit_action = QAction(t("menu.file.exit"), self)
        self._exit_action.setShortcut("Ctrl+Q")
        self._exit_action.triggered.connect(self.close)
        self._file_menu.addAction(self._exit_action)

        # Menú Ver
        self._view_menu = menu_bar.addMenu(t("menu.view"))
        self._show_pro_action = QAction(t("menu.view.show_pro"), self)
        self._show_pro_action.setShortcut("Ctrl+P")
        self._show_pro_action.triggered.connect(self._on_pro_button_clicked)
        self._view_menu.addAction(self._show_pro_action)

        # Menú Ayuda
        self._help_menu = menu_bar.addMenu(t("menu.help"))
        self._about_action = QAction(t("menu.help.about"), self)
        self._about_action.triggered.connect(self._show_about)
        self._help_menu.addAction(self._about_action)

    def _retranslate(self) -> None:
        """Al cambiar de idioma: actualizar tabs, menús y el connection label.

        Las child widgets que se traducen por sí mismas (AppHeader,
        ControlPanel, ProWindow…) ya están suscritas al signal por su
        cuenta — aquí solo cubrimos lo que vive directamente en
        MainWindow.
        """

        # Tabs de nivel superior
        self._tabs.setTabText(TAB_GLOBE, t("globe.tab_title"))
        self._tabs.setTabText(TAB_DATA, t("dashboard.tab_title"))

        # Menús: reconstruir
        self._build_menus()

        # Status bar permanente
        if self._source is None:
            self._connection_label.setText(t("header.status.disconnected"))
            self._latency_label.setText(t("status.latency_none"))

    # ------------------------------------------------------------------
    # Slots del panel de control
    # ------------------------------------------------------------------
    def _on_station_changed(self, preset: StationPreset) -> None:
        """Actualiza la cabecera y, si la fuente está activa, la reinicia."""

        self._current_station = preset
        self.waveform_panel.set_station_label(preset.label)
        self.app_header.set_station(f"{preset.network}.{preset.station}")
        self._status_bar.showMessage(
            t("status.station_selected",
              station=f"{preset.network}.{preset.station}"),
            4000,
        )

        # Reiniciar la conexión si ya estaba activa
        if self._source is not None:
            self._stop_source()
            self._buffer.clear()
            self._start_source_for(preset)

    def _on_filter_changed(self, cfg: FilterConfig) -> None:
        """Recibe la nueva configuración de filtro y la propaga al procesador."""

        self._config.filt = cfg
        self._processor.update_filter(cfg)
        if cfg.enabled:
            self._status_bar.showMessage(
                t("status.filter_enabled",
                  low=cfg.lowcut_hz, high=cfg.highcut_hz, order=cfg.order),
                3000,
            )
        else:
            self._status_bar.showMessage(t("status.filter_disabled"), 3000)

    def _on_trigger_changed(self, cfg: TriggerConfig) -> None:
        """Recibe la nueva configuración del detector."""

        self._config.trigger = cfg
        self._detector.update_config(cfg)
        self._recorder.update_pre_event_seconds(cfg.pre_event_seconds)
        self._status_bar.showMessage(
            t("status.trigger_set",
              sta=cfg.sta_seconds, lta=cfg.lta_seconds, th=cfg.threshold_on),
            3000,
        )

    def _on_connect_clicked(self) -> None:
        """Arranca la fuente de datos correspondiente al preset actual."""

        if self._source is not None:
            self._status_bar.showMessage(t("status.source_already_active"), 2000)
            return

        self._buffer.clear()
        self._start_source_for(self._current_station)

    def _on_disconnect_clicked(self) -> None:
        """Detiene la fuente de datos y limpia la pantalla.

        Pulsar Detener también detiene cualquier sonificación en curso
        — antes podían quedarse colgadas en "Reproduciendo" y romper
        toda la UI si el usuario también pulsaba Detener en ese estado.
        """

        # SIEMPRE detener audio primero (idempotente). Esto cubre el
        # caso de "Escuchar últimos 60 s" → clip colgado → Detener.
        self._audio_player.stop()

        if self._source is None:
            self._status_bar.showMessage(t("status.no_source_active"), 2500)
            return

        self._stop_source()
        self._set_connection_status("Desconectado", "StatusWarn")
        self._latency_label.setText(t("status.latency_none"))
        self.waveform_panel.reset()
        self.spectrogram_panel.reset()
        self.particle_panel.reset()
        self.helicorder_panel.reset()
        self.intensity_card.reset()
        self._intensity_smoother.reset()
        self._stop_alert_blink()
        self._detector.reset()
        self._status_bar.showMessage(t("status.acquisition_stopped"), 3000)

    # ------------------------------------------------------------------
    # Gestión de la fuente de datos
    # ------------------------------------------------------------------
    def _start_source_for(self, preset: StationPreset) -> None:
        """Crea e inicia la fuente apropiada para el preset dado.

        Resolución del servidor SeedLink en este orden:
          1. Si el preset trae ``seedlink_host``/``seedlink_port``
             explícitos (típico cuando se construyó a partir de un
             click en el globo), se usan.
          2. Para AM (Raspberry Shake) caemos al servidor configurado
             globalmente en ``AppConfig`` (``rs.local`` por defecto)
             para preservar el comportamiento histórico.
          3. Para cualquier otra red (IU/US/II/IC…) se consulta
             ``seedlink_server_for()`` que enruta a rtserve.iris.
        """

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
                # Mantener el host global configurado para AM (rs.local
                # por defecto, sustituible por el usuario en su config).
                host = self._config.seedlink_host
                port = self._config.seedlink_port
            else:
                # Redes profesionales → IRIS rtserve
                host, port = seedlink_server_for(preset.network)

            # Canales por red (AM=EHZ, IRIS=BHZ…). Pedirle EHZ a IRIS
            # provoca un "timeout silencioso": el servidor acepta el
            # SELECT pero nunca envía datos porque ese stream no existe.
            channels = seedlink_channels_for(preset.network)

            # Location: si el preset trae uno concreto válido, lo usamos;
            # si no, lo derivamos de la red (IRIS → "00", AM → "").
            # Filtrar comodines incompatibles con SeedLink.
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
        self._set_connection_status("Conectando…", "StatusWarn")
        source.start()
        # El estado pasará a "Conectado" cuando llegue el primer batch
        # (gestionado por _on_data_ready).

    def _stop_source(self) -> None:
        """Detiene de forma segura la fuente activa.

        Robusto frente a:
          * Click repetido en Detener (idempotente — segunda llamada
            sale inmediatamente al ver self._source = None).
          * Source bloqueada en handshake SeedLink (stop interno usa
            socket.shutdown + terminate del hilo como fallback).
          * Race entre deleteLater y hilos trabajadores aún vivos
            (esperamos al hilo dentro de source.stop() antes de
            deleteLater).
        """

        if self._source is None:
            return

        # ─── PASO 1: Quitar la referencia DE INMEDIATO para que un
        # segundo click en Detener (mientras este stop tarda) sea no-op.
        src = self._source
        self._source = None

        # Feedback inmediato. El stop() de SeedLinkSource puede tardar
        # hasta 8-10 s si el handshake estaba colgado; sin este mensaje
        # el usuario cree que la app se quedó frita.
        self._status_bar.showMessage(t("status.stopping_source"), 0)

        # ─── PASO 2: Desconectar señales para no recibir más callbacks
        # de un objeto que vamos a destruir.
        try:
            src.data_ready.disconnect(self._on_data_ready)
            src.status_changed.disconnect(self._on_source_status)
        except (RuntimeError, TypeError):
            pass

        # ─── PASO 3: stop() bloquea hasta que el hilo worker muera
        # (o el watchdog de terminate() se dispare). Capturar
        # cualquier excepción para no impedir la limpieza posterior.
        try:
            src.stop()
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception(
                "Excepción al detener la fuente; continuando con cleanup."
            )

        # ─── PASO 4: deleteLater solo es seguro AHORA que el hilo
        # worker está garantizado muerto.
        src.deleteLater()

        self._status_bar.showMessage(t("status.source_stopped"), 3000)

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
        # El helicorder tiene su propio temporizador para repintar.
        self.helicorder_panel.ingest(batch.z)

        # Al recibir el primer batch, marcar la conexión como activa.
        if self._connection_label.text() != "Conectado":
            self._set_connection_status("Conectado", "StatusOk")

    def _on_source_status(self, message: str) -> None:
        """Muestra los mensajes de la fuente en la barra de estado."""

        self._status_bar.showMessage(message, 4000)

    def _on_refresh_tick(self) -> None:
        """Lee la última ventana del búfer, la procesa y refresca todas las vistas."""

        # Si no hay datos aún, no hace falta repintar.
        if self._buffer.total_written == 0:
            return

        # 1. Leer la ventana de visualización del búfer circular.
        raw = self._buffer.read_window(
            seconds=self._config.stream.display_window_seconds
        )

        # 2. Pasarla por la cadena DSP (detrend + Butterworth pasa-banda).
        #    Cuando el filtro está deshabilitado, ``apply_snapshot`` se
        #    comporta como copia: el coste sigue siendo despreciable.
        processed = self._processor.apply_snapshot(raw)

        # 3. Pintar las trazas resultantes — solo si la VENTANA Pro
        # está visible (Globo y Datos no consumen el búfer local; si
        # Pro está oculta, no hay nada que renderizar y ahorramos CPU).
        if self.pro_window.isVisible():
            if self.pro_window.is_live_subtab_visible():
                self.waveform_panel.update_from_snapshot(processed)
                # Espectrograma: solo cada 3 frames (≈ 10 Hz) para
                # reducir la carga de SciPy. La forma de onda sí se
                # refresca cada frame para conservar la fluidez.
                self._spectrum_frame_skip = (self._spectrum_frame_skip + 1) % 3
                if self._spectrum_frame_skip == 0:
                    spectrum = self._spectrum_computer.compute(
                        processed.samples["Z"]
                    )
                    self.spectrogram_panel.update_from_spectrum(spectrum)
            elif self.pro_window.is_particle_subtab_visible():
                self.particle_panel.update_from_snapshot(processed)
        # La pestaña helicorder se refresca con su propio temporizador
        # (HELICORDER_REFRESH_MS), no en este tick.

        # 3b. Actualizar la tarjeta de intensidad — siempre visible,
        #     independientemente de la pestaña seleccionada.
        gain = default_gain_for(
            self._current_station.network, self._current_station.station
        )
        intensity_snap = IntensitySnapshot.from_samples(
            samples=processed.samples["Z"],
            gain_cm_s_per_count=gain,
            smoother=self._intensity_smoother,
        )
        self.intensity_card.update_from_snapshot(intensity_snap)

        # 5. Detección STA/LTA y, si dispara, lanzar grabación + alerta.
        result = self._detector.process(processed)
        if result.signal == EventSignal.TRIGGERED:
            self._on_event_triggered(result.cft_max)
        elif result.signal == EventSignal.RELEASED:
            self._on_event_released()

        # Actualizar la latencia entre la última muestra y "ahora"
        latency_s = max(0.0, time.time() - raw.latest_timestamp_unix)
        if latency_s < 10.0:
            self._latency_label.setText(
                t("status.latency_ms", value=latency_s * 1000)
            )
        else:
            self._latency_label.setText(
                t("status.latency_s", value=latency_s)
            )

    # ------------------------------------------------------------------
    # Sonificación bajo demanda
    # ------------------------------------------------------------------
    def _on_listen_clicked(self, seconds: int, speed_factor: int) -> None:
        """Toma la última ventana del búfer y la reproduce acelerada."""

        if self._buffer.total_written == 0:
            self._status_bar.showMessage(t("status.no_audio_yet"), 4000)
            return

        # Leer la ventana solicitada (canal Z, el más representativo)
        snap = self._buffer.read_window(seconds=float(seconds))
        z = snap.samples.get("Z")
        if z is None or z.size == 0:
            self._status_bar.showMessage(t("status.empty_channel"), 3000)
            return

        # Sonificar y reproducir
        result = sonify(
            samples=z,
            input_rate_hz=self._config.stream.sample_rate_hz,
            speed_factor=float(speed_factor),
        )
        if result.audio.size == 0:
            self._status_bar.showMessage(t("status.no_audio_generated"), 3000)
            return

        self._audio_player.play(result.audio, result.audio_rate_hz)
        self._status_bar.showMessage(
            t("status.playing_clip",
              seconds=seconds, speed=speed_factor,
              duration=result.audio_duration_s),
            int(result.audio_duration_s * 1000) + 1500,
        )

    def _on_playback_started(self) -> None:
        """Deshabilita el botón para evitar reproducciones solapadas."""

        self.control_panel.set_listen_button_enabled(
            False, label="🔊 Reproduciendo…"
        )

    def _on_playback_finished(self) -> None:
        """Restaura el botón al terminar el clip."""

        self.control_panel.set_listen_button_enabled(True)

    def _on_playback_failed(self, message: str) -> None:
        """Muestra el error y restaura el botón."""

        self._status_bar.showMessage(t("status.audio_error", message=message), 5000)
        self.control_panel.set_listen_button_enabled(True)

    # ------------------------------------------------------------------
    # Manejo de eventos sísmicos detectados
    # ------------------------------------------------------------------
    def _on_event_triggered(self, cft_max: float) -> None:
        """El detector ha cruzado el umbral: alerta visual + grabación."""

        self._start_alert_blink()
        self._status_bar.showMessage(
            t("status.event_detected", cft=cft_max), 8000,
        )

        # Lanzar la grabación del MiniSEED en este mismo tick. Captura
        # cualquier excepción para no detener nunca la UI.
        try:
            result = self._recorder.record_event(
                buffer=self._buffer,
                network=self._current_station.network,
                station=self._current_station.station,
                location=self._current_station.location,
                trigger_time_unix=time.time(),
            )
        except Exception as exc:  # pragma: no cover - red de seguridad
            self._status_bar.showMessage(
                t("status.event_save_failed", error=str(exc)), 6000,
            )
            return

        if result.success and result.path is not None:
            self._status_bar.showMessage(
                t("status.event_saved", path=str(result.path)), 8000,
            )
        else:
            self._status_bar.showMessage(
                t("status.event_save_failed", error=str(result.error)), 6000,
            )

    def _on_event_released(self) -> None:
        """El detector ha bajado del umbral de salida."""

        self._stop_alert_blink()
        self._status_bar.showMessage(t("status.event_ended"), 4000)

    # ------------------------------------------------------------------
    # Datos externos (USGS) — caché para reporte
    # ------------------------------------------------------------------
    # Ventana temporal (en segundos) por nombre de feed USGS
    # NOTA: ``all_6h`` no es un feed real de USGS — pedimos ``all_month``
    # como super-set y filtramos localmente en cliente. Aquí solo
    # registramos las equivalencias para los selectores del UI.
    _PERIOD_SECONDS = {
        "all_hour":  3600,
        "all_6h":    6 * 3600,
        "all_day":   86_400,
        "all_week":  7 * 86_400,
        "all_month": 30 * 86_400,
    }

    def _filter_for_period(self, quakes: list, period: str) -> list:
        """Devuelve los sismos ocurridos en las últimas ``period`` segundos."""

        import time as _time
        seconds = self._PERIOD_SECONDS.get(period, 86_400)
        cutoff = _time.time() - seconds
        return [q for q in quakes if q.timestamp_unix >= cutoff]

    def _period_seconds(self, period: str) -> int:
        """Helper para mapear nombre de periodo → segundos."""

        return self._PERIOD_SECONDS.get(period, 86_400)

    def _on_earthquakes_ready(self, quakes: list) -> None:
        """Recibe el catálogo completo, lo guarda y lo distribuye filtrado."""

        self._latest_earthquakes = list(quakes)
        self._status_bar.showMessage(
            t("status.usgs_loaded", count=len(quakes)), 3000,
        )

        # Globo: filtro temporal puro.
        globe_q = self._filter_for_period(quakes, self._globe_period)
        self.globe_panel.update_earthquakes(globe_q)

        # Dashboard: aplicar tanto periodo como filtro de fuente,
        # y pasar period_seconds para que el payload se construya
        # con la ventana correcta en todas las gráficas.
        self._push_dashboard_payload()

    def _push_dashboard_payload(self) -> None:
        """Recalcula y envía el payload del dashboard con periodo + PAGER region."""

        period_s = self._period_seconds(self._dashboard_period)
        # pager_region "all" se trata como sin filtro en build_payload
        pager_region = (
            None if self._dashboard_pager_region in ("", "all")
            else self._dashboard_pager_region
        )
        self.dashboard_panel.update_earthquakes(
            self._latest_earthquakes,
            period_seconds=period_s,
            pager_region=pager_region,
        )

    def _on_stations_ready(self, stations: list) -> None:
        """Cuenta estaciones por proveedor y avisa en la barra de estado."""

        n_shake = sum(1 for s in stations if s.provider == "shakenet")
        n_usgs = sum(1 for s in stations if s.provider == "usgs")
        # Empujar el catálogo al dashboard para que aparezca en el KPI
        self.dashboard_panel.update_stations(stations)
        # Indexar por (network, code) para resolver clicks del globo
        self._stations_by_nsl = {
            (s.network, s.code): s for s in stations
        }
        # Si ya tenemos sismos cargados, repintar el panel para refrescar
        # el KPI station_summary también.
        if self._latest_earthquakes:
            self._push_dashboard_payload()
        if len(stations) == 0:
            self._status_bar.showMessage(t("status.stations_zero"), 10000)
        else:
            self._status_bar.showMessage(
                t("status.stations_count", shake=n_shake, usgs=n_usgs),
                5000,
            )

    def _on_data_error(self, msg: str) -> None:
        """Propaga el error a la barra de estado y a los overlays."""

        self._status_bar.showMessage(msg, 8000)
        # Solo mostrar overlay rojo si todavía no hemos recibido datos:
        # si ya hay catálogo cargado, basta con el aviso en la barra.
        if not self._latest_earthquakes:
            self.globe_panel.show_error(msg)
            self.dashboard_panel.show_error(msg)

    # Mapeo period_id → clave i18n. La etiqueta humana se resuelve en
    # runtime via t() para que cambie con el idioma activo.
    _PERIOD_I18N_KEYS = {
        "all_hour":  "period.last_hour",
        "all_6h":    "period.last_6h",
        "all_day":   "period.last_day",
        "all_week":  "period.last_week",
        "all_month": "period.last_month",
    }

    @classmethod
    def _period_label(cls, period: str) -> str:
        """Devuelve la etiqueta humana traducida del periodo."""

        key = cls._PERIOD_I18N_KEYS.get(period)
        return t(key) if key else period

    def _on_dashboard_period_changed(self, period: str) -> None:
        """Re-filtra el catálogo local para el dashboard (sin nueva HTTP)."""

        self._dashboard_period = period
        self._status_bar.showMessage(
            t("status.dashboard_filter", period=self._period_label(period)),
            2500,
        )
        if self._latest_earthquakes:
            self._push_dashboard_payload()

    def _on_dashboard_pager_region_changed(self, region: str) -> None:
        """Cambia la región del radar PAGER (afecta solo a esa gráfica)."""

        self._dashboard_pager_region = region or "all"
        label = t("region.everywhere") if region in ("", "all") else region
        self._status_bar.showMessage(
            t("status.pager_region", region=label), 2500,
        )
        if self._latest_earthquakes:
            self._push_dashboard_payload()

    def _on_globe_period_changed(self, period: str) -> None:
        """Re-filtra el catálogo local para el globo (sin nueva HTTP)."""

        self._globe_period = period
        self._status_bar.showMessage(
            t("status.globe_filter", period=self._period_label(period)),
            2500,
        )
        if self._latest_earthquakes:
            filtered = self._filter_for_period(
                self._latest_earthquakes, period
            )
            self.globe_panel.update_earthquakes(filtered)

    # ------------------------------------------------------------------
    # Globe → Pro: click en estación → confirmación → add_station
    # ------------------------------------------------------------------
    def _on_globe_station_clicked(self, network: str, code: str) -> None:
        """Maneja el click sobre una estación en el globo 3D.

        Flujo:
          1. Resolver el ShakeStation completo desde la caché por
             (network, code). Si no existe, mostrar aviso y salir.
          2. Si es estación Raspberry Shake (provider="shakenet"):
             mostrar diálogo solo informativo — la red AM no tiene
             SeedLink público, no podemos conectar a una estación
             remota arbitraria.
          3. Si es estación USGS/IRIS: preguntar al usuario si quiere
             añadirla al banco de trabajo Pro. Si confirma, construir
             un StationPreset con el host correcto (rtserve.iris…) y
             llamar a pro_window.add_station(). Mostrar estado.
        """

        from PySide6.QtWidgets import QMessageBox
        from shakevision.config import (
            seedlink_channels_for,
            seedlink_location_for,
            seedlink_server_for,
        )

        station = self._stations_by_nsl.get((network, code))
        if station is None:
            self._status_bar.showMessage(
                t("status.station_not_found", network=network, code=code),
                4000,
            )
            return

        site = station.site_name or f"{network}.{code}"

        # ── Raspberry Shake: no soportamos conexión remota ──
        # El popup informativo se queda en una fase posterior; aquí
        # solo mostramos un mensaje en la barra de estado.
        if station.provider == "shakenet":
            QMessageBox.information(
                self,
                t("dialog.shake.title"),
                t("dialog.shake.body",
                  network=network, code=code, site=site,
                  lat=station.latitude, lon=station.longitude,
                  elev=station.elevation_m),
            )
            return

        # ── Estación USGS/IRIS: ofrecer conexión ──
        host, port = seedlink_server_for(network)
        loc = seedlink_location_for(network)
        channels = seedlink_channels_for(network)
        used = self.pro_window.dynamic_station_count()
        cap = self.control_panel.MAX_DYNAMIC_STATIONS

        # Construir los selectores SeedLink reales para mostrar al usuario
        selectors = ", ".join(
            f"{loc}{c}" if loc else c for c in channels
        )

        msg = t(
            "dialog.usgs.body",
            network=network, code=code, site=site,
            lat=station.latitude, lon=station.longitude,
            elev=station.elevation_m,
            host=host, port=port,
            channels=selectors,
            slot=used + 1, cap=cap,
        )
        answer = QMessageBox.question(
            self,
            t("dialog.usgs.title", network=network, code=code),
            msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if answer != QMessageBox.Yes:
            return

        # Construir el preset con host + location + canal explícitos.
        # Importante: location NO puede ser "*" (SeedLink no acepta
        # wildcards). Usamos el code estándar de la red ("00" para IRIS).
        preset = StationPreset(
            label=f"{network}.{code} — {site[:30]}",
            network=network,
            station=code,
            location=loc,                   # "00" para IRIS, "" para AM
            channel=channels[0],            # primer canal (Z) como referencia
            seedlink_host=host,
            seedlink_port=port,
        )
        added = self.pro_window.add_station(preset)
        n = self.pro_window.dynamic_station_count()
        if added:
            self._status_bar.showMessage(
                t("status.station_added",
                  network=network, code=code, n=n, cap=cap),
                6000,
            )
        else:
            self._status_bar.showMessage(
                t("status.station_already_there",
                  network=network, code=code),
                4000,
            )

    def _on_retry_data(self) -> None:
        """Disparado por el botón 'Reintentar' de cualquiera de los overlays."""

        self._status_bar.showMessage(t("status.retrying_usgs"), 4000)
        # Volver a mostrar el spinner mientras se intenta
        for panel in (self.globe_panel, self.dashboard_panel):
            overlay = getattr(panel, "_overlay", None)
            if overlay is not None:
                overlay.show_loading("Reintentando", "Conectando con USGS…")
        self._data_worker.refresh_now()

    def _on_export_report(self) -> None:
        """Pregunta al usuario dónde guardar el reporte y lo escribe."""

        if not self._latest_earthquakes:
            self._status_bar.showMessage(t("status.no_data_for_report"), 6000)
            return

        # Sugerir un nombre por defecto basado en la fecha actual
        from datetime import datetime
        default_name = datetime.utcnow().strftime(
            "shakevision_reporte_%Y%m%d_%H%M.html"
        )
        default_path = str(Path.home() / default_name)

        path_str, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar reporte HTML",
            default_path,
            "HTML (*.html);;Todos los archivos (*)",
        )
        if not path_str:
            return  # cancelado

        target = Path(path_str)
        if target.suffix.lower() != ".html":
            target = target.with_suffix(".html")

        # Construir el generador perezosamente
        if self._report_generator is None:
            try:
                self._report_generator = ReportGenerator()
            except Exception as exc:
                self._status_bar.showMessage(
                    t("status.template_load_error", error=str(exc)), 8000,
                )
                return

        try:
            written = self._report_generator.generate(
                quakes=self._latest_earthquakes,
                station_label=(
                    f"{self._current_station.network}."
                    f"{self._current_station.station}"
                ),
                version=__version__,
                output_path=target,
            )
        except Exception as exc:
            self._status_bar.showMessage(
                t("status.report_error", error=str(exc)), 8000,
            )
            return

        self._status_bar.showMessage(
            t("status.report_exported", path=str(written)), 8000,
        )

    def _on_export_report_pdf(self) -> None:
        """Misma lógica que el HTML pero invocando QWebEngineView.printToPdf."""

        if not self._latest_earthquakes:
            self._status_bar.showMessage(t("status.no_data_for_report"), 6000)
            return

        from datetime import datetime
        default_name = datetime.utcnow().strftime(
            "shakevision_reporte_%Y%m%d_%H%M.pdf"
        )
        default_path = str(Path.home() / default_name)

        path_str, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar reporte PDF",
            default_path,
            "PDF (*.pdf);;Todos los archivos (*)",
        )
        if not path_str:
            return

        target = Path(path_str)
        if target.suffix.lower() != ".pdf":
            target = target.with_suffix(".pdf")

        # Generar el HTML con el mismo ReportGenerator
        if self._report_generator is None:
            try:
                self._report_generator = ReportGenerator()
            except Exception as exc:
                self._status_bar.showMessage(
                    t("status.template_load_error", error=str(exc)), 8000,
                )
                return

        html = self._report_generator.render(
            quakes=self._latest_earthquakes,
            station_label=(
                f"{self._current_station.network}."
                f"{self._current_station.station}"
            ),
            version=__version__,
        )

        # Crear el exportador (lo guardamos como atributo para que viva
        # mientras se completa la exportación asíncrona).
        self._pdf_exporter = PdfExporter(self)
        self._pdf_exporter.finished.connect(
            lambda p: self._status_bar.showMessage(
                t("status.pdf_exported", path=str(p)), 8000,
            )
        )
        self._pdf_exporter.failed.connect(
            lambda msg: self._status_bar.showMessage(
                t("status.pdf_error", error=str(msg)), 8000,
            )
        )
        self._status_bar.showMessage(t("status.generating_pdf"), 30000)
        self._pdf_exporter.export(html, target)

    # ------------------------------------------------------------------
    # Ventana flotante Pro: abrir/levantar
    # ------------------------------------------------------------------
    def _on_pro_button_clicked(self) -> None:
        """Acción del botón 🔬 Pro del AppHeader / menú Ver."""

        # show_and_focus es idempotente: si ya estaba visible solo la
        # trae al frente; si estaba oculta la muestra. Nunca recrea.
        self.pro_window.show_and_focus()

    def _on_settings_clicked(self) -> None:
        """Abre el diálogo de preferencias.

        El diálogo aplica los cambios al instante via los servicios
        singleton (LocaleService, TimezoneService). MainWindow solo
        necesita refrescar el dashboard payload tras 'Aplicar' para que
        las marcas de tiempo del JS se redibujen con la nueva tz.
        """

        from shakevision.ui.settings_dialog import SettingsDialog

        dlg = SettingsDialog(self)
        dlg.settings_applied.connect(self._on_settings_applied)
        dlg.exec()

    def _on_settings_applied(self) -> None:
        """Tras aplicar preferencias: empujar payload del dashboard."""

        if self._latest_earthquakes:
            self._push_dashboard_payload()

    # ------------------------------------------------------------------
    # Navegación por las pestañas inferiores
    # ------------------------------------------------------------------
    def _on_tab_changed(self, index: int) -> None:
        """Aplica un fade-in al widget recién visible — excepto a las
        vistas web (Globo, Datos), donde el QGraphicsOpacityEffect
        ralentiza la composición de Chromium y produce un parpadeo
        oscuro de varios segundos antes de estabilizarse.
        """

        new_widget = self._tabs.widget(index)
        if new_widget is None:
            return
        # Saltar el fade en widgets que envuelven QWebEngineView
        if new_widget in (self.globe_panel, self.dashboard_panel):
            return
        self._fade_in_animation = make_fade_in(new_widget, duration_ms=180)
        self._fade_in_animation.start()

    # ------------------------------------------------------------------
    # Animación de alerta (respiración cíclica del marco)
    # ------------------------------------------------------------------
    def _start_alert_blink(self) -> None:
        """Inicia la respiración: borde rojo fijo + halo difuso pulsante."""

        if self._alert_animations:
            return  # Ya hay alerta activa, no apilamos animaciones

        # Activar el borde rojo estático (regla QSS [alert="true"])
        self._apply_alert_property(True)

        # Aplicar un halo de sombra rojo a cada panel y animar su radio
        # de difuminado entre 8 y 32 píxeles con curva sinusoidal.
        for panel in (self.waveform_panel, self.spectrogram_panel):
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
        """Activa/desactiva la propiedad ``alert`` del panel de ondas (QSS)."""

        for panel in (self.waveform_panel, self.spectrogram_panel):
            panel.setProperty("alert", "true" if on else "false")
            style = panel.style()
            if style is not None:
                style.unpolish(panel)
                style.polish(panel)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _set_connection_status(self, text: str, object_name: str) -> None:
        """Actualiza el indicador de conexión (barra de estado + cabecera)."""

        # Barra inferior (texto + clase QSS)
        self._connection_label.setText(text)
        self._connection_label.setObjectName(object_name)
        style = self._connection_label.style()
        if style is not None:
            style.unpolish(self._connection_label)
            style.polish(self._connection_label)

        # Cabecera superior (LED de tres colores)
        # Inferimos el estado del nombre de la clase QSS asignada.
        if object_name == "StatusOk":
            header_state = ConnectionState.CONNECTED
        elif object_name == "StatusAlert":
            header_state = ConnectionState.ERROR
        elif "Conectando" in text or "Connect" in text:
            header_state = ConnectionState.CONNECTING
        else:
            header_state = ConnectionState.DISCONNECTED
        self.app_header.set_connection_state(header_state)

    def _show_about(self) -> None:
        """Muestra un cuadro "Acerca de" minimalista en la barra de estado."""

        self._status_bar.showMessage(
            t("status.about", app=APP_NAME, version=__version__), 6000,
        )

    # ------------------------------------------------------------------
    # Cierre
    # ------------------------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802 (firma impuesta por Qt)
        """Aplica las mejoras nativas en cuanto la ventana es visible.

        El handle nativo de NSWindow / HWND / X11 solo existe después
        de que la ventana se haya mostrado al menos una vez, por eso lo
        hacemos aquí en lugar de en ``__init__``.
        """

        super().showEvent(event)
        if not getattr(self, "_native_enhancements_applied", False):
            self._native_enhancements_applied = True
            level = enhance_macos_window(self)
            hint = macos_dependency_hint()
            if hint and level != "native_full":
                # Sugerir al usuario instalar pyobjc para mejor estética
                self._status_bar.showMessage(hint, 8000)

    def closeEvent(self, event) -> None:  # noqa: N802 (firma impuesta por Qt)
        """Detiene los temporizadores y la fuente al cerrar la ventana.

        También fuerza el cierre real (destrucción) de la ventana flotante
        Pro: su propio closeEvent solo la oculta, así que aquí marcamos
        ``_force_close = True`` para que respete la solicitud de salida.
        """

        self._refresh_timer.stop()
        self._helicorder_timer.stop()
        self._stop_alert_blink()
        self._audio_player.stop()
        self._data_worker.stop()
        self._stop_source()
        # Cerrar realmente la ventana Pro (no solo ocultarla)
        if hasattr(self, "pro_window") and self.pro_window is not None:
            # Reemplazamos su closeEvent para que esta vez sí termine
            self.pro_window.closeEvent = lambda e: e.accept()
            self.pro_window.close()
        super().closeEvent(event)
