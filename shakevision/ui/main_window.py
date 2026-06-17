"""
Ventana principal de SeismicGuard.

Reúne en una sola ``QMainWindow``:
  - El panel de control lateral (izquierda).
  - El panel de formas de onda (derecha).
  - Una barra de estado inferior con la latencia y los mensajes.

Arquitectura (v0.7.7)
---------------------
``MainWindow`` es el **shell**: header, pestañas Globo/Datos, status bar,
diálogos, exportación de reporte y el feed USGS para el globo/dashboard.

Toda la **canalización Workbench en tiempo real** (fuente de datos, búfer,
DSP, detector STA/LTA, grabación, sonificación, espectrograma, timers de
refresco y la animación de alerta) vive en ``WorkbenchController``, que
conduce la ``ProWindow``. MainWindow solo instancia el controlador, cablea
las señales de control de la ProWindow a sus slots, y conecta las señales
del controlador (status/latencia/estación/conexión) a sus widgets.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
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
    StationPreset,
)
from shakevision.services import FileCache
from shakevision.services.iris import IRISClient
from shakevision.services.shakenet import ShakeNetClient
from shakevision.services.usgs import USGSClient
from shakevision.services.report import ReportGenerator
from shakevision.services.worker import DataRefreshWorker
from shakevision.utils.periods import filter_for_period, period_seconds
from shakevision.ui.animations import make_fade_in
from shakevision.i18n import LocaleService, t
from shakevision.ui.app_header import AppHeader, ConnectionState
from shakevision.ui.dashboard_view import DashboardPanel
from shakevision.ui.globe_view import GlobePanel
from shakevision.ui.pdf_exporter import PdfExporter
from shakevision.ui.macos_native import (
    enhance_macos_window,
    is_macos,
    macos_dependency_hint,
    title_bar_inset_for,
)
from shakevision.ui.pro_window import ProWindow
from shakevision.ui.signal_safety import subscribe
from shakevision.ui.workbench_controller import WorkbenchController

logger = logging.getLogger(__name__)


# Índices de las pestañas de nivel superior (v0.5.3: Profile salió
# a un diálogo, ya no es tab — su botón en AppHeader abre el modal).
TAB_GLOBE: int = 0      # 🌍 Globo (vista por defecto)
TAB_DATA:  int = 1      # 📊 Datos
TAB_EVENTS: int = 2     # 📋 Eventos (centro de eventos)
TAB_MINE: int = 3       # 👤 Mi colección (favoritos + registros)


class MainWindow(QMainWindow):
    """Ventana principal de la aplicación."""

    def __init__(self, config: AppConfig) -> None:
        super().__init__()

        # Guardar la configuración mutable (las señales del panel la actualizan)
        self._config = config

        # v0.7.7 (S1): toda la canalización Workbench (source, buffer,
        # processor, detector, recorder, audio, timers, …) vive ahora en
        # ``WorkbenchController``. Se instancia más abajo, tras crear la
        # ProWindow que conduce. MainWindow solo cablea sus señales.

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
        # NOTA: el connect de currentChanged se hace MÁS ABAJO, tras
        # crear todos los panels. Si se conecta aquí, el primer addTab
        # dispara currentChanged y _on_tab_changed accede a panels
        # que aún no existen → AttributeError al arrancar.

        # ── Tab 1: Globo 3D ── (vista por defecto, pantalla completa)
        # v0.5 阶段 N: usamos QIcon real en lugar de emoji 🌍 en el
        # título. Más legible, escala bien en HiDPI y respeta el tema.
        from shakevision.ui.icons import get_icon as _get_icon_n
        from shakevision.ui.theme_manager import ThemeManager as _TM_n
        _theme_n = _TM_n.current_theme()

        self.globe_panel = GlobePanel(parent=self._tabs)
        self._tabs.addTab(
            self.globe_panel,
            _get_icon_n("globe", theme=_theme_n, size=64),
            t("globe.tab_title"),
        )

        # ── Tab 2: Datos (7 gráficas ECharts, pantalla completa) ──
        self.dashboard_panel = DashboardPanel(parent=self._tabs)
        self._tabs.addTab(
            self.dashboard_panel,
            _get_icon_n("chart", theme=_theme_n, size=64),
            t("dashboard.tab_title"),
        )

        # ── Tab 3: Centro de eventos (catálogo + estaciones cercanas) ──
        from shakevision.ui.event_center_panel import EventCenterPanel
        self.event_center = EventCenterPanel(parent=self._tabs)
        self.event_center.review_requested.connect(self._on_event_review_requested)
        self._tabs.addTab(
            self.event_center,
            _get_icon_n("events", theme=_theme_n, size=64),
            t("events.tab_title"),
        )

        # ── Tab 4: Mi colección (favoritos + grabaciones + catálogo) ──
        from shakevision.ui.my_data_panel import MyDataPanel
        self.my_data = MyDataPanel(parent=self._tabs)
        self.my_data.review_event.connect(self._on_review_favorite_event)
        self.my_data.use_station.connect(self._on_use_favorite_station)
        self.my_data.recording_activated.connect(self._on_recording_activated)
        self.my_data.review_catalog.connect(self._on_review_catalog)
        self._tabs.addTab(
            self.my_data,
            _get_icon_n("user", theme=_theme_n, size=64),
            t("mine.tab_title"),
        )

        # NOTA v0.5.3: Profile dejó de ser tab — ahora se abre desde
        # el botón 👤 de la AppHeader como diálogo modal (ProfileDialog).
        # profile_panel se mantiene como atributo lazy (se instancia al
        # abrir el diálogo) para no construir QNetworkAccessManager en
        # vano si el usuario nunca abre Profile.
        self.profile_dialog = None    # type: ignore[assignment]

        # Tamaño visual del icono en la pestaña (Qt no usa el size del
        # QIcon directamente para el render del tab).
        from PySide6.QtCore import QSize as _QSize_n
        self._tabs.setIconSize(_QSize_n(18, 18))

        # Reaplicar iconos cuando el tema cambia (claro <-> oscuro)
        # para que el color del trazo coincida con el texto del tab.
        # v0.7.7 (B1): subscribe() en vez de lambda — disconnect en
        # destroyed + guarda RuntimeError.
        subscribe(self, _TM_n.changed_signal(), self._refresh_tab_icons)

        # Globo es la vista por defecto (índice 0)
        self._tabs.setCurrentIndex(0)
        # Conectar currentChanged AHORA, no antes: ya existen los 3
        # panels, así que cualquier disparo subsiguiente es seguro.
        self._tabs.currentChanged.connect(self._on_tab_changed)
        root.addWidget(self._tabs, stretch=1)

        # Animación de fade-in al cambiar de pestaña
        self._fade_in_animation = None

        # ─── Ventana flotante "Pro" ───
        # Instanciada UNA vez al arrancar y oculta. El botón del
        # AppHeader la llama con show_and_focus(); al cerrarla el
        # propio ProWindow intercepta closeEvent y solo se oculta,
        # preservando todo el estado (buffers, helicorder, etc.).
        self.pro_window = ProWindow(config=config)

        # v0.7.7 (S1): el controlador posee la canalización (source, buffer,
        # detector, timers, audio…) y conduce la ProWindow. MainWindow
        # cablea las 6 señales de control de la ProWindow a sus slots.
        self._workbench = WorkbenchController(config, view=self.pro_window)
        self.pro_window.station_changed.connect(
            self._workbench.on_station_changed)
        self.pro_window.filter_changed.connect(
            self._workbench.on_filter_changed)
        self.pro_window.trigger_changed.connect(
            self._workbench.on_trigger_changed)
        self.pro_window.connect_clicked.connect(
            self._workbench.on_connect_clicked)
        self.pro_window.disconnect_clicked.connect(
            self._workbench.on_disconnect_clicked)
        self.pro_window.listen_clicked.connect(
            self._workbench.on_listen_clicked)
        # v0.7.7: las unidades físicas (m/s) las pide la barra del propio
        # oscilograma; el controlador obtiene la sensibilidad. Congelar y
        # los pickers son internos al panel (no necesitan al controlador).
        self.pro_window.waveform_panel.units_requested.connect(
            self._workbench.on_units_toggled)

        # v0.7.7: modo kiosko (monitorización a pantalla completa, estilo
        # SWARM): F11 alterna; Esc sale. Oculta cabecera + barra de pestañas
        # para una vista limpia del globo/datos.
        self._kiosk: bool = False
        QShortcut(QKeySequence("F11"), self, activated=self._toggle_kiosk)
        QShortcut(QKeySequence("Esc"), self, activated=self._exit_kiosk)

        # Atajos cómodos a los paneles internos del banco de trabajo —
        # permiten que el resto de MainWindow siga escribiendo
        # ``self.waveform_panel.update(...)`` sin cambiar.
        self.control_panel = self.pro_window.control_panel
        self.intensity_card = self.pro_window.intensity_card
        self.waveform_panel = self.pro_window.waveform_panel
        self.spectrogram_panel = self.pro_window.spectrogram_panel
        self.helicorder_panel = self.pro_window.helicorder_panel
        self.particle_panel = self.pro_window.particle_panel

        # Estación inicial en la barra superior (el panel de ondas lo fija
        # el propio controlador en su __init__).
        _st0 = self._workbench.current_station
        self.app_header.set_station(f"{_st0.network}.{_st0.station}")
        self.app_header.set_connection_state(ConnectionState.DISCONNECTED)

        # Botón "🔬 Pro" del AppHeader → mostrar la ventana flotante.
        self.app_header.pro_clicked.connect(self._on_pro_button_clicked)
        # Botón ⚙ → diálogo de preferencias (idioma + zona horaria)
        self.app_header.settings_clicked.connect(self._on_settings_clicked)
        # Botón 👤 Profile (v0.5.3) → abre ProfileDialog modal.
        self.app_header.profile_clicked.connect(self._open_profile_dialog)

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

        # v0.7.7 (S1): cablear las señales del controlador a los widgets
        # del shell (ya existen status bar + labels). El controlador no
        # referencia estos widgets directamente.
        self._workbench.status_message.connect(self._status_bar.showMessage)
        self._workbench.latency_text.connect(self._latency_label.setText)
        self._workbench.station_changed.connect(self.app_header.set_station)
        self._workbench.connection_status_changed.connect(
            self._set_connection_status)

        # Re-traducir cuando cambie el idioma: tabs, menús, status bar
        subscribe(self, LocaleService.language_changed_signal(),
                  self._retranslate)  # v0.7.7 (B1)

        # ----------------------------------------------------------------
        # Menú "Archivo" mínimo
        # ----------------------------------------------------------------
        self._build_menus()

        # NOTA: las conexiones señal-slot del ControlPanel ahora se
        # establecen contra ProWindow (que las reemite); ver más arriba
        # en este __init__. El reloj de refresco de UI y los timers viven
        # ahora en WorkbenchController.

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
        # v0.7.7: el centro de eventos puede ampliar la ventana del feed
        # (día/semana/mes) y refrescar a demanda.
        self.event_center.period_changed.connect(self._data_worker.set_period)
        self.event_center.refresh_requested.connect(self._data_worker.refresh_now)
        # Click en una estación del globo → diálogo de confirmación →
        # añadir a la lista del ControlPanel de la ventana Pro.
        self.globe_panel.station_clicked.connect(
            self._on_globe_station_clicked
        )
        # v0.7.7: click en un sismo → revisión histórica (Replay) con la
        # estación seleccionada + ventana alrededor del origen + P/S teóricas.
        self.globe_panel.earthquake_clicked.connect(
            self._on_globe_quake_clicked
        )
        # v0.6 Phase 13: right-click en sismo → toggle favorito.
        self.globe_panel.favorite_toggled.connect(
            self._on_globe_favorite_toggled
        )
        # Cuando el FavoritesStore cambie (por cualquier vía: globe,
        # Profile dialog, settings import…), re-empuja la lista al
        # globo para que actualice las ★ visuales.
        # v0.7.7 (B1): subscribe() — disconnect en destroyed + guarda.
        from shakevision.services.favorites_store import FavoritesStore
        subscribe(self, FavoritesStore.changed_signal(),
                  self._push_favorited_event_ids_to_globe)
        # Push inicial cuando el globo esté listo (los favoritos
        # persistidos en QSettings ya tienen IDs, hay que mostrarlos
        # con ★ aunque el usuario no haga ningún cambio).
        try:
            bridge = getattr(self.globe_panel, "_bridge", None)
            if bridge is not None:
                bridge.globe_ready.connect(
                    self._push_favorited_event_ids_to_globe
                )
        except Exception:  # noqa: BLE001
            logger.debug("No se pudo conectar globe_ready del bridge",
                         exc_info=True)

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
        self._tabs.setTabText(TAB_EVENTS, t("events.tab_title"))
        self._tabs.setTabText(TAB_MINE, t("mine.tab_title"))

        # Menús: reconstruir
        self._build_menus()

        # Status bar permanente
        if not self._workbench.has_source:
            self._connection_label.setText(t("header.status.disconnected"))
            self._latency_label.setText(t("status.latency_none"))

    # ------------------------------------------------------------------
    # Datos externos (USGS) — caché para reporte
    # ------------------------------------------------------------------
    # Ventana temporal (en segundos) por nombre de feed USGS
    # NOTA: ``all_6h`` no es un feed real de USGS — pedimos ``all_month``
    # como super-set y filtramos localmente en cliente. Aquí solo
    # registramos las equivalencias para los selectores del UI.
    # v0.7.7 (O2): el mapeo periodo→segundos y el filtrado por ventana
    # se extrajeron a ``shakevision.utils.periods`` (funciones puras
    # testeables). Estos métodos delegan para no tocar a los llamadores.
    def _filter_for_period(self, quakes: list, period: str) -> list:
        """Devuelve los sismos ocurridos en las últimas ``period`` segundos."""

        return filter_for_period(quakes, period)

    def _period_seconds(self, period: str) -> int:
        """Helper para mapear nombre de periodo → segundos."""

        return period_seconds(period)

    def _on_earthquakes_ready(self, quakes: list) -> None:
        """Recibe el catálogo completo, lo guarda y lo distribuye filtrado."""

        self._latest_earthquakes = list(quakes)
        self._status_bar.showMessage(
            t("status.usgs_loaded", count=len(quakes)), 3000,
        )

        # Globo: filtro temporal puro.
        globe_q = self._filter_for_period(quakes, self._globe_period)
        self.globe_panel.update_earthquakes(globe_q)

        # Centro de eventos (nivel superior): catálogo completo + frescura.
        try:
            self.event_center.set_events(quakes)
            self.event_center.set_last_updated()
        except (RuntimeError, AttributeError):
            pass

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
        self._latest_stations = list(stations)
        # Centro de eventos: catálogo de estaciones para "más cercanas".
        try:
            self.event_center.set_stations(stations)
        except (RuntimeError, AttributeError):
            pass
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
    def _on_globe_quake_clicked(self, quake_id: str) -> None:
        """v0.7.7: click en un sismo del globo → revisión histórica.

        Abre el Workbench en la pestaña Replay, fija la ventana temporal
        alrededor del origen del sismo (manteniendo la estación seleccionada)
        y guarda las coordenadas del evento para superponer las llegadas
        teóricas P/S tras la descarga. NO descarga automáticamente: el usuario
        revisa la estación/ventana y pulsa Descargar.
        """

        if not quake_id:
            return
        from datetime import datetime, timezone
        from shakevision.i18n import t
        from PySide6.QtWidgets import QMessageBox
        from shakevision.services.favorites_store import FavoritesStore

        quake = None
        for q in getattr(self, "_latest_earthquakes", []) or []:
            if q.id == quake_id:
                quake = q
                break
        if quake is None:
            return

        when = datetime.fromtimestamp(quake.timestamp_unix, tz=timezone.utc)
        box = QMessageBox(self)
        box.setWindowTitle(t("dialog.replay_event.title"))
        box.setText(t("dialog.replay_event.body",
                      mag=f"{quake.magnitude:.1f}", place=quake.place,
                      when=when.strftime("%Y-%m-%d %H:%M:%S UTC")))
        review_btn = box.addButton(t("dialog.btn_review"), QMessageBox.AcceptRole)
        fav_now = FavoritesStore.is_favorite_event(quake_id)
        fav_btn = box.addButton(
            t("dialog.btn_unfavorite") if fav_now else t("dialog.btn_favorite"),
            QMessageBox.ActionRole)
        box.addButton(t("dialog.btn_cancel"), QMessageBox.RejectRole)
        box.setDefaultButton(review_btn)
        box.exec()
        clicked = box.clickedButton()
        if clicked is review_btn:
            self._open_event_in_replay(quake)
        elif clicked is fav_btn:
            self._on_globe_favorite_toggled(quake_id)   # add/quita favorito

    def _find_quake(self, quake_id: str):
        for q in getattr(self, "_latest_earthquakes", []) or []:
            if q.id == quake_id:
                return q
        return None

    def _nearest_station_to(self, quake):
        """Estación IRIS/Shake más cercana al sismo (o None)."""

        from shakevision.processing.measurements import great_circle_degrees
        stations = getattr(self, "_latest_stations", None) or []
        best, best_d = None, None
        for s in stations:
            lat = getattr(s, "latitude", None)
            lon = getattr(s, "longitude", None)
            # Solo redes reproducibles vía IRIS dataselect (no Raspberry Shake).
            if lat is None or lon is None or getattr(s, "provider", "") != "usgs":
                continue
            d = great_circle_degrees(quake.latitude, quake.longitude, lat, lon)
            if best_d is None or d < best_d:
                best, best_d = s, d
        return best

    def _event_name(self, quake) -> str:
        return f"M{quake.magnitude:.1f} — {quake.place}"

    def _open_event_in_replay(self, quake, station=None) -> None:
        """Abre el Workbench/Replay en el evento dado (sin diálogo).

        Si se da (o se encuentra) una estación CERCANA, se usa esa para el
        evento (ventana razonable, P/S dentro del dato), sin tocar el combo ni
        la conexión en vivo. Si no hay catálogo de estaciones, cae al modo
        antiguo (estación seleccionada en la barra lateral).
        """

        from datetime import datetime, timezone
        when = datetime.fromtimestamp(quake.timestamp_unix, tz=timezone.utc)
        self.pro_window.show_and_focus()
        self.pro_window.subtabs.setCurrentIndex(self.pro_window.PRO_REPLAY)
        # Tip para usuarios de UN solo monitor: el análisis abre en OTRA ventana
        # (el Workbench), que puede quedar tapada por la principal.
        self._status_bar.showMessage(t("status.opened_in_workbench"), 5000)
        if station is None:
            station = self._nearest_station_to(quake)
        try:
            if station is not None:
                from shakevision.config import seedlink_channels_for
                band = seedlink_channels_for(station.network)[0][:2]
                self.pro_window.replay_panel.set_event_review(
                    lat=quake.latitude, lon=quake.longitude,
                    depth_km=quake.depth_km, origin=when,
                    event_name=self._event_name(quake),
                    net=station.network, sta=station.code, band=band,
                    duration_s=600,
                )
            else:
                self.pro_window.replay_panel.prefill_from_event_context(
                    lat=quake.latitude, lon=quake.longitude,
                    depth_km=quake.depth_km, origin=when, duration_s=600,
                    event_name=self._event_name(quake),
                )
        except Exception:  # noqa: BLE001
            logger.debug("Replay: prefill desde evento falló", exc_info=True)

    def _on_event_review_requested(self, quake_id: str, station) -> None:
        """Centro de eventos: el usuario eligió un evento + estación cercana."""

        quake = self._find_quake(quake_id)
        if quake is not None:
            self._open_event_in_replay(quake, station=station)

    def _on_recording_activated(self, path: str, net: str, sta: str) -> None:
        """Doble clic en una grabación local → abrir en Replay."""

        self.pro_window.show_and_focus()
        self.pro_window.subtabs.setCurrentIndex(self.pro_window.PRO_REPLAY)
        try:
            self.pro_window.replay_panel.load_local_stream(path, net, sta)
        except Exception:  # noqa: BLE001
            logger.debug("Replay: cargar grabación local falló", exc_info=True)

    def _on_review_catalog(self, idx: int) -> None:
        """"Mi colección": doble clic en el catálogo → reabrir esa revisión
        (estación + ventana + picks P/S guardados) en Replay."""

        from shakevision.services.catalog_store import CatalogStore
        detail = CatalogStore().get_event(int(idx))
        if not detail:
            self._status_bar.showMessage(t("mine.catalog_open_failed"), 4000)
            return
        self.pro_window.show_and_focus()
        self.pro_window.subtabs.setCurrentIndex(self.pro_window.PRO_REPLAY)
        self._status_bar.showMessage(t("status.opened_in_workbench"), 5000)
        try:
            self.pro_window.replay_panel.load_catalog_event(detail)
        except Exception:  # noqa: BLE001
            logger.debug("Replay: reabrir desde catálogo falló", exc_info=True)

    def _on_review_favorite_event(self, fav) -> None:
        """"Mi colección": doble clic en un sismo favorito → revisar.

        El favorito guarda lat/lon/depth (v0.7.7) → se construye un objeto
        tipo-Earthquake y se reusa la ruta de revisión. Favoritos antiguos sin
        coords se intentan resolver en el feed actual por id.
        """

        from types import SimpleNamespace
        if getattr(fav, "latitude", 0.0) or getattr(fav, "longitude", 0.0):
            quake = SimpleNamespace(
                id=fav.id, magnitude=fav.magnitude, place=fav.place,
                timestamp_unix=fav.timestamp_unix, latitude=fav.latitude,
                longitude=fav.longitude, depth_km=fav.depth_km)
        else:
            quake = self._find_quake(fav.id)
        if quake is not None:
            self._open_event_in_replay(quake)
        else:
            self._status_bar.showMessage(t("mine.fav_no_coords"), 4000)

    def _on_use_favorite_station(self, net: str, code: str) -> None:
        """"Mi colección": doble clic en estación favorita → añadir al combo
        del Workbench (sin conectar) y mostrarlo."""

        st = self._stations_by_nsl.get((net, code))
        if st is not None:
            self._on_globe_station_clicked(net, code)
        else:
            # Sin metadatos no podemos construir un preset completo; al menos
            # abrir el Workbench para que el usuario la seleccione/añada.
            self.pro_window.show_and_focus()
            self._status_bar.showMessage(
                t("status.station_already_there", network=net, code=code), 3000)

    # ------------------------------------------------------------------
    def _on_globe_favorite_toggled(self, quake_id: str) -> None:
        """v0.6 Phase 13: right-click sobre un sismo en el globo.

        Si el sismo ya está en favoritos → quitarlo. Si no → añadirlo
        (con los metadatos completos del Earthquake actual). El
        FavoritesStore emite ``changed_signal`` que dispara el push de
        la lista actualizada al globo + refresh del Profile dialog.
        """

        if not quake_id:
            return
        try:
            from shakevision.i18n import t
            from shakevision.services.favorites_store import FavoritesStore
        except Exception:  # noqa: BLE001
            return

        # Buscar el sismo en la caché reciente (la lista que se enviÃ³
        # al globo). Es la fuente más fresca disponible en proceso.
        quake = None
        for q in getattr(self, "_latest_earthquakes", []) or []:
            if q.id == quake_id:
                quake = q
                break

        if FavoritesStore.is_favorite_event(quake_id):
            FavoritesStore.remove_event(quake_id)
            self._status_bar.showMessage(
                t("status.favorite_removed", id=quake_id)
                if quake is None
                else t("status.favorite_removed_named",
                       place=quake.place, mag=quake.magnitude),
                3500,
            )
        else:
            if quake is None:
                # Sin metadatos no podemos crear el favorito. Aviso y salir.
                self._status_bar.showMessage(
                    t("status.favorite_not_found", id=quake_id), 3500,
                )
                return
            FavoritesStore.add_event(
                id=quake.id,
                magnitude=float(quake.magnitude),
                place=quake.place or "",
                timestamp_unix=float(quake.timestamp_unix),
                latitude=float(quake.latitude),
                longitude=float(quake.longitude),
                depth_km=float(quake.depth_km),
            )
            self._status_bar.showMessage(
                t("status.favorite_added",
                  place=quake.place, mag=quake.magnitude),
                3500,
            )

    def _push_favorited_event_ids_to_globe(self) -> None:
        """v0.6 Phase 13: empuja la lista actual de IDs favoritos al
        JS del globo para que actualice las marcas ★. Slot de
        ``FavoritesStore.changed_signal``."""

        try:
            from shakevision.services.favorites_store import FavoritesStore
            ids = [e.id for e in FavoritesStore.list_events()]
            if hasattr(self, "globe_panel"):
                self.globe_panel.push_favorited_event_ids(ids)
        except Exception:  # noqa: BLE001
            logger.debug("No se pudieron empujar favoritos al globo",
                         exc_info=True)

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

        # Métrica local: cada click cuenta, independientemente del
        # resultado (proveedor / cancelación). El usuario está
        # interactuando con el globo.
        try:
            from shakevision.services.usage_tracker import UsageTracker
            UsageTracker.record_station_clicked()
        except Exception:  # noqa: BLE001 — métricas nunca rompen UI
            logger.debug("UsageTracker.record_station_clicked falló",
                         exc_info=True)

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
        from shakevision.services.favorites_store import FavoritesStore
        box = QMessageBox(self)
        box.setWindowTitle(t("dialog.usgs.title", network=network, code=code))
        box.setText(msg)
        add_btn = box.addButton(t("dialog.btn_add_workbench"),
                                QMessageBox.AcceptRole)
        fav_now = FavoritesStore.is_favorite_station(network, code)
        fav_btn = box.addButton(
            t("dialog.btn_unfavorite") if fav_now else t("dialog.btn_favorite"),
            QMessageBox.ActionRole)
        box.addButton(t("dialog.btn_cancel"), QMessageBox.RejectRole)
        box.setDefaultButton(add_btn)
        box.exec()
        clicked = box.clickedButton()
        if clicked is fav_btn:
            if fav_now:
                FavoritesStore.remove_station(network, code)
            else:
                FavoritesStore.add_station(
                    network, code, site_name=site or "", provider="usgs")
            return
        if clicked is not add_btn:
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
                # v0.7.6: i18n (antes hardcoded "Reintentando"/"Conectando")
                overlay.show_loading(
                    t("overlay.retrying"),
                    t("overlay.retrying_subtitle"),
                )
        self._data_worker.refresh_now()

    # ------------------------------------------------------------------
    # Helpers de exportación de reporte (v0.7.7 O1: de-duplicar HTML/PDF)
    # ------------------------------------------------------------------
    def _station_label(self) -> str:
        """Etiqueta ``RED.ESTACION`` del station activo para el reporte."""

        station = self._workbench.current_station
        return f"{station.network}.{station.station}"

    def _ensure_report_generator(self) -> Optional[ReportGenerator]:
        """Crea el ``ReportGenerator`` perezosamente.

        Devuelve ``None`` (y muestra el error en la status bar) si la
        plantilla no carga — los llamadores deben abortar en ese caso.
        """

        if self._report_generator is None:
            try:
                self._report_generator = ReportGenerator()
            except Exception as exc:  # noqa: BLE001
                self._status_bar.showMessage(
                    t("status.template_load_error", error=str(exc)), 8000,
                )
                return None
        return self._report_generator

    def _ask_report_save_path(
        self, ext: str, title: str, file_filter: str,
    ) -> Optional[Path]:
        """Diálogo "guardar como" con nombre por defecto + sufijo forzado.

        Devuelve ``None`` si el usuario cancela.
        """

        from datetime import datetime, timezone
        default_name = datetime.now(timezone.utc).strftime(
            f"shakevision_reporte_%Y%m%d_%H%M.{ext}"
        )
        path_str, _ = QFileDialog.getSaveFileName(
            self, title, str(Path.home() / default_name), file_filter,
        )
        if not path_str:
            return None
        target = Path(path_str)
        if target.suffix.lower() != f".{ext}":
            target = target.with_suffix(f".{ext}")
        return target

    @staticmethod
    def _record_report_metric() -> None:
        """Métrica local "reporte generado" — nunca rompe la UI."""

        try:
            from shakevision.services.usage_tracker import UsageTracker
            UsageTracker.record_report_generated()
        except Exception:  # noqa: BLE001 — métricas nunca rompen UI
            logger.debug("UsageTracker.record_report_generated falló",
                         exc_info=True)

    def _on_export_report(self) -> None:
        """Pregunta al usuario dónde guardar el reporte y lo escribe."""

        if not self._latest_earthquakes:
            self._status_bar.showMessage(t("status.no_data_for_report"), 6000)
            return

        target = self._ask_report_save_path(
            "html", "Exportar reporte HTML",
            "HTML (*.html);;Todos los archivos (*)",
        )
        if target is None:
            return  # cancelado

        generator = self._ensure_report_generator()
        if generator is None:
            return

        try:
            written = generator.generate(
                quakes=self._latest_earthquakes,
                station_label=self._station_label(),
                version=__version__,
                output_path=target,
            )
        except Exception as exc:  # noqa: BLE001
            self._status_bar.showMessage(
                t("status.report_error", error=str(exc)), 8000,
            )
            return

        self._status_bar.showMessage(
            t("status.report_exported", path=str(written)), 8000,
        )
        self._record_report_metric()

    def _on_export_report_pdf(self) -> None:
        """Misma lógica que el HTML pero invocando QWebEngineView.printToPdf."""

        if not self._latest_earthquakes:
            self._status_bar.showMessage(t("status.no_data_for_report"), 6000)
            return

        target = self._ask_report_save_path(
            "pdf", "Exportar reporte PDF",
            "PDF (*.pdf);;Todos los archivos (*)",
        )
        if target is None:
            return

        generator = self._ensure_report_generator()
        if generator is None:
            return

        html = generator.render(
            quakes=self._latest_earthquakes,
            station_label=self._station_label(),
            version=__version__,
        )

        # Crear el exportador (lo guardamos como atributo para que viva
        # mientras se completa la exportación asíncrona).
        self._pdf_exporter = PdfExporter(self)

        def _on_pdf_done(path):
            self._status_bar.showMessage(
                t("status.pdf_exported", path=str(path)), 8000,
            )
            self._record_report_metric()

        self._pdf_exporter.finished.connect(_on_pdf_done)
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

    # ------------------------------------------------------------------
    # Modo kiosko (pantalla completa de monitorización)
    # ------------------------------------------------------------------
    def _toggle_kiosk(self) -> None:
        self._set_kiosk(not self._kiosk)

    def _exit_kiosk(self) -> None:
        if self._kiosk:
            self._set_kiosk(False)

    def _set_kiosk(self, on: bool) -> None:
        """Entra/sale del modo kiosko: oculta cabecera + barra de pestañas y
        pasa a pantalla completa (o revierte)."""

        self._kiosk = bool(on)
        self.app_header.setVisible(not on)
        try:
            self._tabs.tabBar().setVisible(not on)
        except (RuntimeError, AttributeError):
            pass
        if on:
            self.showFullScreen()
            try:
                from shakevision.i18n import t
                self._status_bar.showMessage(t("status.kiosk_on"), 4000)
            except (RuntimeError, AttributeError, KeyError):
                pass
        else:
            self.showNormal()

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

    def _refresh_tab_icons(self) -> None:
        """Re-pinta los iconos de las pestañas con el color del tema.

        v0.5 阶段 N: las pestañas usan QIcon real (globe/chart).
        Al cambiar de tema (claro ↔ oscuro) el trazo del icono debe
        cambiar entre navy y blanco — lo logramos limpiando la caché
        de get_icon y reasignando los QIcons a cada tab.

        v0.5.3: ya no hay tab Profile — su icono se actualiza dentro
        de AppHeader._refresh_button_icons.
        """

        try:
            from shakevision.ui.icons import clear_icon_cache, get_icon
            from shakevision.ui.theme_manager import ThemeManager as _TM
            clear_icon_cache()
            theme = _TM.current_theme()
            self._tabs.setTabIcon(TAB_GLOBE,
                                  get_icon("globe", theme=theme, size=64))
            self._tabs.setTabIcon(TAB_DATA,
                                  get_icon("chart", theme=theme, size=64))
            self._tabs.setTabIcon(TAB_EVENTS,
                                  get_icon("events", theme=theme, size=64))
            self._tabs.setTabIcon(TAB_MINE,
                                  get_icon("user", theme=theme, size=64))
        except Exception as exc:  # noqa: BLE001
            logger.debug("Tab icon refresh skip (%s)", exc)

    def _open_profile_dialog(self) -> None:
        """Abre el ProfileDialog modal (v0.5.3).

        Lazy-construct: solo creamos el diálogo la primera vez que el
        usuario lo abre. En subsiguientes aperturas reutilizamos la
        misma instancia (más rápido + el QNetworkAccessManager interno
        del avatar mantiene su caché HTTP).
        """

        from shakevision.ui.profile_dialog import ProfileDialog

        if self.profile_dialog is None:
            self.profile_dialog = ProfileDialog(self)
            self.profile_dialog.request_github_login.connect(
                self._open_github_login_dialog)
        else:
            # Refrescar datos cada vez que se reabre (stats pueden
            # haber cambiado mientras estaba cerrado).
            self.profile_dialog.refresh()
        self.profile_dialog.show()
        self.profile_dialog.raise_()
        self.profile_dialog.activateWindow()

    def _open_github_login_dialog(self) -> None:
        """Lanza el diálogo de login GitHub (v0.5 阶段 K + L)."""

        from shakevision.ui.github_login_dialog import GitHubLoginDialog

        dlg = GitHubLoginDialog(self)
        # Refrescar el Profile dialog si está visible
        dlg.logged_in.connect(
            lambda _u: self.profile_dialog and self.profile_dialog.refresh())
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

        # Al entrar en "Mi colección": re-escanear disco (grabaciones nuevas /
        # catálogo) sin pulsar Refrescar.
        if index == TAB_MINE:
            try:
                self.my_data.refresh()
            except (RuntimeError, AttributeError):
                pass

        new_widget = self._tabs.widget(index)
        if new_widget is None:
            return
        # Saltar el fade en widgets que envuelven QWebEngineView.
        # v0.5.3: Profile salió a diálogo, solo quedan globe + dashboard.
        skip_widgets = tuple(
            w for w in (
                getattr(self, "globe_panel", None),
                getattr(self, "dashboard_panel", None),
            ) if w is not None
        )
        if new_widget in skip_widgets:
            return
        self._fade_in_animation = make_fade_in(new_widget, duration_ms=180)
        self._fade_in_animation.start()

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

        # v0.7.7 (S1): el controlador detiene timers + alerta + audio +
        # fuente. El worker de datos (feed USGS) sigue viviendo aquí.
        self._workbench.shutdown()
        self._data_worker.stop()
        # Cerrar realmente la ventana Pro (no solo ocultarla)
        if hasattr(self, "pro_window") and self.pro_window is not None:
            # Reemplazamos su closeEvent para que esta vez sí termine
            self.pro_window.closeEvent = lambda e: e.accept()
            self.pro_window.close()
        super().closeEvent(event)
