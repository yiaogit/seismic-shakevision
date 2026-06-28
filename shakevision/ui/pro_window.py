"""
Ventana flotante "Pro" — banco de trabajo profesional.

Contiene exactamente lo que antes era la pestaña ``🔬 Pro`` de
``MainWindow``:

  ┌──────────────┬──────────────────────────────┐
  │              │  Tarjeta de intensidad MMI   │
  │              ├──────────────────────────────┤
  │ ControlPanel │  Sub-pestañas:               │
  │ (estación,   │   📡 En vivo (oscilograma +  │
  │  filtro,     │      espectrograma)          │
  │  STA-LTA,    │   📜 Diario 24h (helicorder) │
  │  audio)      │   🌀 Hodograma (partícula)   │
  │              │                              │
  └──────────────┴──────────────────────────────┘

Por qué es una QMainWindow y no un QDialog:
  * Permite tener barra de estado propia si se quiere en el futuro.
  * Soporta menús nativos por plataforma sin trucos.
  * Es no-modal por defecto — el usuario puede tener Globo y Pro
    visibles al mismo tiempo en monitores diferentes.

Ciclo de vida:
  * MainWindow instancia ProWindow UNA vez al arrancar (oculta).
  * El botón "🔬" del AppHeader llama a ``show_and_focus()``.
  * Al cerrar la ventana ``closeEvent`` la oculta en lugar de
    destruirla → todos los QWebEngineView/pyqtgraph/Buffers
    sobreviven. Reabrir es instantáneo.

Datos:
  * **NO** posee ni source ni buffer ni timer; vive en MainWindow.
  * MainWindow accede a los paneles vía ``self.pro_window.X`` y los
    actualiza en su ``_on_refresh_tick`` (que ahora condiciona en
    ``pro_window.isVisible()`` en lugar del antiguo TAB_PRO).
  * Las señales de ControlPanel (station/filter/trigger/connect/
    disconnect/listen) se RE-EMITEN para que MainWindow se conecte
    igual que antes.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QSettings, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from shakevision.config import AppConfig, StationPreset
from shakevision.i18n import LocaleService, t
from shakevision.ui.control_panel import ControlPanel
from shakevision.ui.helicorder_widget import HelicorderPanel
from shakevision.ui.icons import get_icon
from shakevision.ui.intensity_card import IntensityCard
from shakevision.ui.particle_motion_widget import ParticleMotionPanel
from shakevision.ui.replay_panel import ReplayPanel
from shakevision.ui.spectrogram_widget import SpectrogramPanel
from shakevision.ui.signal_safety import subscribe
from shakevision.ui.waveform_widget import WaveformPanel


# v0.8.0 reestructuración a DOS MODOS de nivel superior:
#   * MODE_LIVE     → contiene las 3 sub-pestañas en vivo (abajo).
#   * MODE_REPLAY   → análisis histórico (ReplayPanel), autocontenido.
# Ver docs/workbench-restructure.md.
MODE_LIVE: int = 0
MODE_REPLAY: int = 1

# Índices de sub-pestañas DENTRO del modo "En vivo" (waveform/24h/hodograma).
PRO_LIVE: int = 0
PRO_HELICORDER: int = 1
PRO_PARTICLE: int = 2

# Tamaño por defecto la primera vez que se abre la ventana
_DEFAULT_WIDTH: int = 1200
_DEFAULT_HEIGHT: int = 800

# Claves QSettings para recordar geometría entre sesiones
_QSETTINGS_ORG: str = "SeismicGuard"
_QSETTINGS_APP: str = "Pro"
_QSETTINGS_KEY_GEOMETRY: str = "pro_window/geometry"


class ProWindow(QMainWindow):
    """Ventana flotante con el banco de trabajo profesional."""

    # ─── Señales reemitidas desde el ControlPanel interno ───
    # MainWindow se conecta a ESTAS, no a las del ControlPanel directo;
    # así el wiring sobrevive a recargas internas del panel sin tocar
    # main_window.
    station_changed = Signal(object)        # StationPreset
    filter_changed = Signal(object)         # FilterConfig
    trigger_changed = Signal(object)        # TriggerConfig
    connect_clicked = Signal()
    disconnect_clicked = Signal()
    listen_clicked = Signal(int, int)       # (seconds, speed_factor)

    # Constantes expuestas (MainWindow / controller las leen).
    MODE_LIVE: int = MODE_LIVE
    MODE_REPLAY: int = MODE_REPLAY
    PRO_LIVE: int = PRO_LIVE
    PRO_HELICORDER: int = PRO_HELICORDER
    PRO_PARTICLE: int = PRO_PARTICLE

    def __init__(
        self,
        config: AppConfig,
        parent: Optional[QWidget] = None,
    ) -> None:
        # Pasamos parent=None para que sea una ventana de nivel raíz
        # con su propia entrada en el dock/taskbar (no una sub-ventana
        # modal). MainWindow guarda la referencia para que no la
        # recolecte el GC.
        super().__init__(parent)
        self.setWindowTitle(t("pro.window_title"))
        self.resize(_DEFAULT_WIDTH, _DEFAULT_HEIGHT)
        self.setMinimumSize(900, 600)
        # Atributo Qt para que el window manager la trate como ventana
        # secundaria y no como diálogo modal.
        self.setWindowFlag(Qt.Window, True)

        # ─── Layout central: ControlPanel + columna derecha ───
        central = QWidget(self)
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        # ControlPanel a la izquierda
        self.control_panel = ControlPanel(config=config, parent=central)
        root.addWidget(self.control_panel)

        # Columna derecha: conmutador de MODO (En vivo / Histórico) — v0.8.0.
        right = QWidget(central)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        self.mode_tabs = QTabWidget(parent=right)
        self.mode_tabs.setDocumentMode(True)

        # ════════ MODO "En vivo" ════════
        # MMI arriba + sub-pestañas (waveform / 24h / hodograma) abajo.
        live_mode = QWidget()
        live_mode_l = QVBoxLayout(live_mode)
        live_mode_l.setContentsMargins(0, 0, 0, 0)
        live_mode_l.setSpacing(8)

        self.intensity_card = IntensityCard(parent=live_mode)
        live_mode_l.addWidget(self.intensity_card)

        self.subtabs = QTabWidget(parent=live_mode)
        self.subtabs.setDocumentMode(True)

        # ── Sub-tab "En vivo" (waveform + espectrograma) ──
        live_container = QWidget()
        live_layout = QVBoxLayout(live_container)
        live_layout.setContentsMargins(0, 0, 0, 0)
        live_layout.setSpacing(4)
        live_bar = QHBoxLayout()
        live_bar.addStretch(1)
        self.live_spec_toggle = QPushButton(t("replay.toggle_spectrogram"))
        self.live_spec_toggle.setObjectName("ToolbarButton")
        self.live_spec_toggle.setCheckable(True)
        self.live_spec_toggle.setChecked(True)
        self.live_spec_toggle.toggled.connect(self._on_live_spec_toggled)
        live_bar.addWidget(self.live_spec_toggle)
        live_layout.addLayout(live_bar)

        live_splitter = QSplitter(Qt.Vertical, parent=live_container)
        self.waveform_panel = WaveformPanel(parent=live_splitter)
        self.spectrogram_panel = SpectrogramPanel(parent=live_splitter)
        live_splitter.addWidget(self.waveform_panel)
        live_splitter.addWidget(self.spectrogram_panel)
        live_splitter.setStretchFactor(0, 65)
        live_splitter.setStretchFactor(1, 35)
        live_layout.addWidget(live_splitter, stretch=1)
        self._live_container = live_container
        self.subtabs.addTab(live_container, t("pro.subtab.live"))

        # ── Sub-tab "Diario 24h" ──
        self.helicorder_panel = HelicorderPanel(
            sample_rate_hz=config.stream.sample_rate_hz, parent=self.subtabs,
        )
        self.subtabs.addTab(self.helicorder_panel, t("pro.subtab.helicorder"))

        # ── Sub-tab "Hodograma" ──
        self.particle_panel = ParticleMotionPanel(
            sample_rate_hz=config.stream.sample_rate_hz, parent=self.subtabs,
        )
        self.subtabs.addTab(self.particle_panel, t("pro.subtab.particle"))

        live_mode_l.addWidget(self.subtabs, stretch=1)
        self.mode_tabs.addTab(live_mode, t("pro.mode.live"))

        # ════════ MODO "Análisis histórico" (autocontenido) ════════
        # Descarga IRIS + reproducción; propio buffer/processor, no comparte
        # estado con el live. v0.8.0: pasa a ser un MODO de nivel superior.
        self.replay_panel = ReplayPanel(config=config, parent=self.mode_tabs)
        self.mode_tabs.addTab(self.replay_panel, t("pro.mode.replay"))

        right_layout.addWidget(self.mode_tabs, stretch=1)
        root.addWidget(right, stretch=1)

        # La tarjeta MMI (tiempo real) solo en la sub-pestaña "En vivo"; al
        # cambiar de modo a Histórico, todo el contenedor live se oculta solo.
        self.subtabs.currentChanged.connect(self._on_subtab_changed)
        self.mode_tabs.currentChanged.connect(self._on_mode_changed)
        self._on_subtab_changed(self.subtabs.currentIndex())
        self._on_mode_changed(self.mode_tabs.currentIndex())

        # v0.8.0: iconos vectoriales en los tabs (sustituyen a los emoji).
        self._apply_tab_icons()
        from shakevision.ui.theme_manager import ThemeManager as _TM
        subscribe(self, _TM.changed_signal(), self._apply_tab_icons)

        # ─── Conectar las 6 señales del ControlPanel a las que
        #     reemitimos hacia afuera ───
        self.control_panel.station_changed.connect(self.station_changed)
        # v0.8.0: la estación del combo EN VIVO se AÑADE a Replay como opción
        # (soft bridge); ``set_station`` solo la SELECCIONA si Replay aún no
        # tenía ninguna (default inicial). Replay tiene su propio selector y NO
        # es secuestrado por cambios del combo en vivo.
        self.control_panel.station_changed.connect(self.replay_panel.set_station)
        self.replay_panel.set_station(self.control_panel.current_station())
        self.control_panel.filter_changed.connect(self.filter_changed)
        # v0.8.0: el filtro de la barra lateral YA NO toca Replay — el modo
        # histórico tiene su propio paso de banda (independiente). Ver
        # docs/workbench-restructure.md.
        self.control_panel.trigger_changed.connect(self.trigger_changed)
        self.control_panel.connect_clicked.connect(self.connect_clicked)
        self.control_panel.disconnect_clicked.connect(self.disconnect_clicked)
        self.control_panel.listen_clicked.connect(self.listen_clicked)

        # ─── Restaurar geometría guardada en sesiones previas ───
        self._restore_geometry()

        # ─── Suscribirse a cambios de idioma para re-traducir tab titles ───
        subscribe(self, LocaleService.language_changed_signal(),
                  self._retranslate)  # v0.7.7 (B1)

    def _apply_tab_icons(self) -> None:
        """Pone los iconos vectoriales (recoloreados al tema) en los tabs."""

        from shakevision.ui.theme_manager import ThemeManager as _TM
        try:
            th = _TM.current_theme()
        except Exception:  # noqa: BLE001
            th = "dark"
        try:
            self.mode_tabs.setTabIcon(MODE_LIVE, get_icon("mode_live", theme=th))
            self.mode_tabs.setTabIcon(MODE_REPLAY,
                                      get_icon("mode_replay", theme=th))
            self.subtabs.setTabIcon(PRO_LIVE, get_icon("mode_live", theme=th))
            self.subtabs.setTabIcon(PRO_HELICORDER, get_icon("heli", theme=th))
            self.subtabs.setTabIcon(PRO_PARTICLE, get_icon("particle", theme=th))
        except (RuntimeError, AttributeError):
            pass

    def _retranslate(self) -> None:
        """Re-aplica el título de la ventana y las etiquetas de sub-pestañas."""

        self.setWindowTitle(t("pro.window_title"))
        self.mode_tabs.setTabText(MODE_LIVE, t("pro.mode.live"))
        self.mode_tabs.setTabText(MODE_REPLAY, t("pro.mode.replay"))
        self.subtabs.setTabText(PRO_LIVE, t("pro.subtab.live"))
        self.subtabs.setTabText(PRO_HELICORDER, t("pro.subtab.helicorder"))
        self.subtabs.setTabText(PRO_PARTICLE, t("pro.subtab.particle"))
        if hasattr(self, "live_spec_toggle"):
            self.live_spec_toggle.setText(t("replay.toggle_spectrogram"))

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def show_and_focus(self) -> None:
        """Muestra la ventana y la trae al frente con focus."""

        self._prewarm_obspy()
        self.show()
        # macOS: tras tener NSWindow nativa (requiere estar visible), hacer que
        # el botón verde haga ZOOM en lugar de abrir un Space a pantalla
        # completa (evita el Space negro al cerrar). Una sola vez.
        if not getattr(self, "_macos_fs_disabled", False):
            from shakevision.ui.macos_native import disable_native_fullscreen
            self._macos_fs_disabled = disable_native_fullscreen(self)
        # Si estaba minimizada en macOS/Windows, restaurarla
        if self.windowState() & Qt.WindowMinimized:
            self.setWindowState(
                self.windowState() & ~Qt.WindowMinimized | Qt.WindowActive
            )
        self.raise_()
        self.activateWindow()

    def _prewarm_obspy(self) -> None:
        """Importa ObsPy en segundo plano la PRIMERA vez que se abre el
        Workbench (v0.7.7, optimización de velocidad de conexión).

        El worker SeedLink importa ObsPy de forma perezosa; la primera
        importación tarda ~1-2 s. Al precalentarla en un hilo daemon
        cuando el usuario abre el banco de trabajo (señal de que pronto
        conectará), la PRIMERA conexión ya encuentra el módulo cacheado en
        ``sys.modules`` y arranca el handshake sin esa espera. Idempotente
        y silencioso: si ObsPy falta, la conexión real lo reportará.
        """

        if getattr(self, "_obspy_prewarmed", False):
            return
        self._obspy_prewarmed = True
        import threading

        def _warm() -> None:
            try:
                import obspy.clients.seedlink.easyseedlink  # noqa: F401
            except Exception:  # noqa: BLE001
                pass

        threading.Thread(
            target=_warm, name="obspy-prewarm", daemon=True
        ).start()

    def _on_live_spec_toggled(self, on: bool) -> None:
        """Mostrar/ocultar el espectrograma en la sub-pestaña En vivo."""

        try:
            self.spectrogram_panel.setVisible(bool(on))
        except (RuntimeError, AttributeError):
            pass

    def _on_subtab_changed(self, index: int) -> None:
        """Tarjeta de intensidad (MMI) solo en la sub-pestaña 'En vivo'."""

        try:
            self.intensity_card.setVisible(index == PRO_LIVE)
        except (RuntimeError, AttributeError):
            pass

    def _on_mode_changed(self, index: int) -> None:
        """Cambio de modo: el ControlPanel lateral (台站/连接/滤波/STA-LTA/声音)
        es **solo del modo En vivo**. En modo Histórico se oculta — Replay es
        autocontenido (tiene su propio selector de estación + filtro), así que
        gana todo el ancho. Ver docs/workbench-restructure.md."""

        try:
            self.control_panel.setVisible(index == MODE_LIVE)
        except (RuntimeError, AttributeError):
            pass

    def show_replay(self) -> None:
        """Cambia al modo Análisis histórico (lo usa MainWindow al revisar)."""

        self.mode_tabs.setCurrentIndex(MODE_REPLAY)

    def show_live(self) -> None:
        """Cambia al modo En vivo."""

        self.mode_tabs.setCurrentIndex(MODE_LIVE)

    def is_live_subtab_visible(self) -> bool:
        """¿Está visible la vista de oscilograma EN VIVO? (modo En vivo +
        sub-pestaña 'En vivo'). El controller lo usa para no refrescar trazas
        ocultas."""

        return (self.mode_tabs.currentIndex() == MODE_LIVE
                and self.subtabs.currentIndex() == PRO_LIVE)

    def is_particle_subtab_visible(self) -> bool:
        """¿Está visible el hodograma EN VIVO? (modo En vivo + sub-pestaña
        'Hodograma')."""

        return (self.mode_tabs.currentIndex() == MODE_LIVE
                and self.subtabs.currentIndex() == PRO_PARTICLE)

    def add_station(self, preset: StationPreset) -> bool:
        """Añade una estación al desplegable del ControlPanel.

        Wrapper directo a ``ControlPanel.append_dynamic_station``;
        MainWindow lo llama cuando el usuario confirma la conexión
        desde un click en el globo. Devuelve ``True`` si la estación
        era nueva, ``False`` si ya existía y solo se seleccionó.
        """

        return self.control_panel.append_dynamic_station(preset)

    def dynamic_station_count(self) -> int:
        return self.control_panel.dynamic_station_count()

    # ------------------------------------------------------------------
    # Eventos de ventana
    # ------------------------------------------------------------------
    def closeEvent(self, event) -> None:  # noqa: N802 (firma Qt)
        """Al pulsar la X: guardar geometría y OCULTAR en lugar de cerrar.

        De esta forma todos los widgets (WaveformPanel, helicorder, …)
        siguen vivos y la próxima vez que el usuario abra Pro se ve
        exactamente como la dejó.

        El ReplayPanel sí libera su ReplaySource activo (si lo hay) para
        evitar que un timer siga emitiendo después de cerrar la ventana.
        """

        try:
            self.replay_panel.close_resources()
        except Exception:  # noqa: BLE001
            pass

        # macOS fallback (sin pyobjc): si la ventana sigue en un Space a
        # pantalla completa nativo, ocultarla AHORA la deja en negro durante la
        # animación de salida (~1 s). Salimos de fullscreen y aplazamos el
        # hide hasta que termine la animación. (Con pyobjc el botón verde ya
        # hace zoom y nunca entramos aquí — ver disable_native_fullscreen.)
        if self.isFullScreen():
            self.setWindowState(
                self.windowState() & ~Qt.WindowFullScreen & ~Qt.WindowMaximized)
            event.ignore()
            QTimer.singleShot(800, self._finish_close_after_fullscreen)
            return

        if self.isMaximized():
            self.setWindowState(self.windowState() & ~Qt.WindowMaximized)
        self._save_geometry()
        event.ignore()
        self.hide()

    def _finish_close_after_fullscreen(self) -> None:
        """Oculta la ventana tras completarse la animación de salida de
        pantalla completa (macOS, ruta de fallback sin pyobjc)."""

        try:
            self._save_geometry()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.hide()
        except RuntimeError:
            pass

    # ------------------------------------------------------------------
    # Persistencia ligera de geometría
    # ------------------------------------------------------------------
    def _save_geometry(self) -> None:
        settings = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
        settings.setValue(_QSETTINGS_KEY_GEOMETRY, self.saveGeometry())

    def _restore_geometry(self) -> None:
        settings = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
        geom = settings.value(_QSETTINGS_KEY_GEOMETRY)
        if geom:
            self.restoreGeometry(geom)
