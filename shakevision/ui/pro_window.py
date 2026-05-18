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

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from shakevision.config import AppConfig, StationPreset
from shakevision.i18n import LocaleService, t
from shakevision.ui.control_panel import ControlPanel
from shakevision.ui.helicorder_widget import HelicorderPanel
from shakevision.ui.intensity_card import IntensityCard
from shakevision.ui.particle_motion_widget import ParticleMotionPanel
from shakevision.ui.replay_panel import ReplayPanel
from shakevision.ui.spectrogram_widget import SpectrogramPanel
from shakevision.ui.waveform_widget import WaveformPanel


# Índices de sub-pestañas dentro de Pro (constantes internas)
PRO_LIVE: int = 0
PRO_HELICORDER: int = 1
PRO_PARTICLE: int = 2
PRO_REPLAY: int = 3

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

    # Sub-pestaña actualmente visible (0/1/2/3). MainWindow lo lee para
    # decidir si refrescar oscilograma/espectrograma o no.
    PRO_LIVE: int = PRO_LIVE
    PRO_HELICORDER: int = PRO_HELICORDER
    PRO_PARTICLE: int = PRO_PARTICLE
    PRO_REPLAY: int = PRO_REPLAY

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

        # Columna derecha: MMI arriba + sub-pestañas debajo
        right = QWidget(central)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        self.intensity_card = IntensityCard(parent=right)
        right_layout.addWidget(self.intensity_card)

        self.subtabs = QTabWidget(parent=right)
        self.subtabs.setDocumentMode(True)

        # ── Sub-tab "En vivo" ──
        live_container = QWidget()
        live_layout = QHBoxLayout(live_container)
        live_layout.setContentsMargins(0, 0, 0, 0)
        live_splitter = QSplitter(Qt.Vertical, parent=live_container)
        self.waveform_panel = WaveformPanel(parent=live_splitter)
        self.spectrogram_panel = SpectrogramPanel(parent=live_splitter)
        live_splitter.addWidget(self.waveform_panel)
        live_splitter.addWidget(self.spectrogram_panel)
        live_splitter.setStretchFactor(0, 65)
        live_splitter.setStretchFactor(1, 35)
        live_layout.addWidget(live_splitter)
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

        # ── Sub-tab "Replay" (descarga IRIS + reproducción histórica) ──
        # Tiene su propio buffer/processor; no comparte estado con el live.
        self.replay_panel = ReplayPanel(config=config, parent=self.subtabs)
        self.subtabs.addTab(self.replay_panel, t("pro.subtab.replay"))

        right_layout.addWidget(self.subtabs, stretch=1)
        root.addWidget(right, stretch=1)

        # ─── Conectar las 6 señales del ControlPanel a las que
        #     reemitimos hacia afuera ───
        self.control_panel.station_changed.connect(self.station_changed)
        self.control_panel.filter_changed.connect(self.filter_changed)
        self.control_panel.trigger_changed.connect(self.trigger_changed)
        self.control_panel.connect_clicked.connect(self.connect_clicked)
        self.control_panel.disconnect_clicked.connect(self.disconnect_clicked)
        self.control_panel.listen_clicked.connect(self.listen_clicked)

        # ─── Restaurar geometría guardada en sesiones previas ───
        self._restore_geometry()

        # ─── Suscribirse a cambios de idioma para re-traducir tab titles ───
        LocaleService.language_changed_signal().connect(self._retranslate)

    def _retranslate(self) -> None:
        """Re-aplica el título de la ventana y las etiquetas de sub-pestañas."""

        self.setWindowTitle(t("pro.window_title"))
        self.subtabs.setTabText(PRO_LIVE, t("pro.subtab.live"))
        self.subtabs.setTabText(PRO_HELICORDER, t("pro.subtab.helicorder"))
        self.subtabs.setTabText(PRO_PARTICLE, t("pro.subtab.particle"))
        self.subtabs.setTabText(PRO_REPLAY, t("pro.subtab.replay"))

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def show_and_focus(self) -> None:
        """Muestra la ventana y la trae al frente con focus."""

        self.show()
        # Si estaba minimizada en macOS/Windows, restaurarla
        if self.windowState() & Qt.WindowMinimized:
            self.setWindowState(
                self.windowState() & ~Qt.WindowMinimized | Qt.WindowActive
            )
        self.raise_()
        self.activateWindow()

    def is_live_subtab_visible(self) -> bool:
        """¿Es la sub-pestaña "En vivo" la actualmente seleccionada?"""

        return self.subtabs.currentIndex() == PRO_LIVE

    def is_particle_subtab_visible(self) -> bool:
        """¿Es la sub-pestaña "Hodograma" la actualmente seleccionada?"""

        return self.subtabs.currentIndex() == PRO_PARTICLE

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

        self._save_geometry()
        try:
            self.replay_panel.close_resources()
        except Exception:  # noqa: BLE001
            pass
        event.ignore()
        self.hide()

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
