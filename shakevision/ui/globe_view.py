"""
Vista del globo 3D — wrapper Qt sobre la página HTML/JS de ``web/globe``.

Arquitectura
------------
* La página real está en ``shakevision/web/globe/index.html`` y la
  carga un ``QWebEngineView`` apuntando a su URL local.
* La comunicación con Python se hace via ``QWebChannel``: registramos
  un objeto ``GlobeBridge`` con nombre ``"bridge"`` y la página lo
  obtiene en ``window.bridge``.
* Para empujar datos a la vista llamamos a ``runJavaScript`` sobre el
  ``QWebEnginePage`` activo (más eficiente que pasar por el bridge si
  el flujo es Python → JS de un sentido).

Si el módulo ``QtWebEngineWidgets`` no está disponible (algunas
distribuciones Linux mínimas), mostramos un mensaje informativo en
lugar de explotar.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QUrl, Signal, Slot
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout, QWidget

from shakevision.i18n import LocaleService, t
from shakevision.services.data_models import Earthquake, ShakeStation
from shakevision.ui.layer_mode_manager import LayerModeManager
from shakevision.ui.loading_overlay import LoadingOverlay
from shakevision.ui.theme import (
    COLOR_PANEL,
    COLOR_PANEL_BORDER,
    COLOR_TEXT_SECONDARY,
)
from shakevision.ui.signal_safety import subscribe
from shakevision.ui.theme_manager import ThemeManager

logger = logging.getLogger(__name__)


# Carpeta donde vive index.html / globe.js / styles.css
WEB_GLOBE_DIR: Path = Path(__file__).resolve().parent.parent / "web" / "globe"


# ============================================================
# Bridge (objeto registrado en QWebChannel)
# ============================================================
class GlobeBridge(QObject):
    """Objeto Python que la página JS verá como ``window.bridge``."""

    # Emitidos cuando el usuario interactúa con un punto del globo
    station_clicked = Signal(str, str)        # (network, code)
    earthquake_clicked = Signal(str)          # id
    layer_changed = Signal(str)               # "devices" | "quakes" | "both"
    period_changed = Signal(str)              # "all_hour" / "all_day" / ...
    globe_ready = Signal()                    # JS terminó de inicializarse
    # v0.6 Phase 13: right-click sobre un sismo → toggle favorito
    favorite_toggled = Signal(str)            # earthquake id

    # ------------------------------------------------------------------
    # Slots invocables desde JS
    # ------------------------------------------------------------------
    @Slot(str, str)
    def on_station_clicked(self, network: str, code: str) -> None:
        self.station_clicked.emit(network, code)

    @Slot(str)
    def on_earthquake_clicked(self, quake_id: str) -> None:
        self.earthquake_clicked.emit(quake_id)

    @Slot(str)
    def on_layer_changed(self, layer: str) -> None:
        self.layer_changed.emit(layer)

    @Slot(str)
    def on_period_changed(self, period: str) -> None:
        self.period_changed.emit(period)

    @Slot()
    def on_globe_ready(self) -> None:
        self.globe_ready.emit()

    @Slot(str)
    def on_favorite_toggled(self, quake_id: str) -> None:
        """v0.6 Phase 13: right-click en sismo → toggle favorito."""

        self.favorite_toggled.emit(quake_id)


# ============================================================
# Serializadores Python → JSON puro (no Qt)
# ============================================================
def serialize_stations(stations: list[ShakeStation]) -> list[dict]:
    """Convierte la lista de ShakeStation al formato que espera globe.js.

    Incluye el campo ``provider`` (``shakenet`` o ``usgs``) para que el
    frontend pueda colorearlas con paletas distintas.
    """

    return [
        {
            "network": s.network,
            "code": s.code,
            "lat": float(s.latitude),
            "lng": float(s.longitude),
            "elevation": float(s.elevation_m),
            "site": s.site_name,
            "provider": s.provider,
        }
        for s in stations
    ]


def serialize_earthquakes(quakes: list[Earthquake]) -> list[dict]:
    """Convierte la lista de Earthquake al formato que espera globe.js."""

    return [
        {
            "id": q.id,
            "ts": float(q.timestamp_unix),
            "lat": float(q.latitude),
            "lng": float(q.longitude),
            "depth": float(q.depth_km),
            "mag": float(q.magnitude),
            "place": q.place,
            "pager": q.pager.value if q.pager else None,
            "sig": int(q.significance),
        }
        for q in quakes
    ]


# ============================================================
# Panel principal
# ============================================================
class GlobePanel(QFrame):
    """Panel que muestra el globo 3D dentro del QStackedWidget."""

    # Reenvío conveniente de las señales del bridge
    station_clicked = Signal(str, str)
    earthquake_clicked = Signal(str)
    period_changed = Signal(str)
    # v0.6 Phase 13: right-click sobre sismo → toggle favorito
    favorite_toggled = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("GlobePanel")    # estilo propio v0.5.3
        self.setFrameShape(QFrame.NoFrame)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # v0.5.3: el contenedor del globo SIEMPRE es negro, independiente
        # del tema Qt (claro/oscuro). El globo es un escenario espacial
        # — el espacio es negro. Renderizar el web view sobre un fondo
        # claro genera bordes blancos chocantes alrededor de la esfera.
        self.setStyleSheet(
            "QFrame#GlobePanel { background-color: #000000; border: none; }"
        )
        # Pintar el fondo del propio QFrame también en negro
        from PySide6.QtGui import QPalette as _QPalette
        from PySide6.QtCore import Qt as _Qt
        pal = self.palette()
        pal.setColor(_QPalette.Window, _Qt.black)
        self.setPalette(pal)
        self.setAutoFillBackground(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._view = None        # tipo: QWebEngineView | None
        self._bridge = None      # tipo: GlobeBridge | None
        self._channel = None
        self._ready = False
        self._pending_stations: list[ShakeStation] | None = None
        self._pending_quakes: list[Earthquake] | None = None
        self._got_first_data = False

        try:
            self._init_web_view(layout)
        except ImportError as exc:
            logger.warning("QtWebEngine no disponible: %s", exc)
            layout.addWidget(self._fallback_label(str(exc)))
            return

        # Overlay de carga inicial
        self._overlay = LoadingOverlay(self)
        self._overlay.show_loading(
            t("globe.loading_title"),
            t("globe.loading_subtitle"),
        )

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def update_stations(self, stations: list[ShakeStation]) -> None:
        """Empuja el catálogo de estaciones al globo."""

        if self._view is None:
            return
        if not self._ready:
            self._pending_stations = stations
            return
        payload = json.dumps(serialize_stations(stations))
        self._run_js(f"window.shakevisionGlobe.setDevices({payload});")

    def update_earthquakes(self, quakes: list[Earthquake]) -> None:
        """Empuja la lista de sismos al globo."""

        if self._view is None:
            return
        if not self._ready:
            self._pending_quakes = quakes
            return
        payload = json.dumps(serialize_earthquakes(quakes))
        self._run_js(f"window.shakevisionGlobe.setEarthquakes({payload});")
        self._on_first_data()

    def show_error(self, message: str) -> None:
        """Si la fuente de datos falla, muestra el overlay rojo."""

        if hasattr(self, "_overlay"):
            self._overlay.show_error(
                t("globe.error_title"),
                subtitle=message,
                show_retry=True,
            )

    def _on_first_data(self) -> None:
        """Oculta el overlay tras recibir el primer batch."""

        if not self._got_first_data and hasattr(self, "_overlay"):
            self._got_first_data = True
            self._overlay.hide_overlay()

    def set_layer(self, layer: str) -> None:
        """Forza la capa visible: ``"devices"`` / ``"quakes"`` / ``"both"``."""

        if layer not in {"devices", "quakes", "both"}:
            raise ValueError(f"capa desconocida: {layer!r}")
        if self._view is None or not self._ready:
            return
        self._run_js(f"window.shakevisionGlobe.setLayer({json.dumps(layer)});")

    def push_i18n(self) -> None:
        """Empuja la tabla de i18n actual + el código de idioma al JS.

        v0.6 Phase 10: junto a la tabla mandamos también el ``lang``
        actual ("en"/"es"/"zh"/"fr") para que las etiquetas de país
        del modo Pro se traduzcan inmediatamente.
        """

        if self._view is None or not self._ready:
            return
        try:
            table = LocaleService.current_table()
            lang  = LocaleService.current_language()
        except Exception:  # noqa: BLE001
            table = {}
            lang  = "en"
        payload_table = json.dumps(table)
        payload_lang  = json.dumps(lang)
        self._run_js(
            f"window.shakevisionGlobe.setI18n({payload_table});"
            f"window.shakevisionGlobe.setLang({payload_lang});"
        )

    # ------------------------------------------------------------------
    # Modo visual del globo (Theme × LayerMode → "day"/"night"/"holographic")
    # ------------------------------------------------------------------
    @staticmethod
    def _compute_visual_mode() -> str:
        """Deriva el modo visual del globo del estado global.

        Reglas:
          * LayerMode = "professional"            → "holographic"
          * LayerMode = "standard" + Theme="light" → "day"
          * LayerMode = "standard" + Theme="dark"  → "night"
        """

        try:
            layer = LayerModeManager.current_mode()
        except Exception:  # noqa: BLE001
            layer = "standard"
        if layer == "professional":
            return "holographic"
        try:
            theme = ThemeManager.current_theme()
        except Exception:  # noqa: BLE001
            theme = "dark"
        return "day" if theme == "light" else "night"

    def push_visual_mode(self) -> None:
        """Calcula el modo actual y se lo empuja al JS del globo.

        v0.6 G: ahora también empuja el tema activo ("dark" / "light")
        como segundo argumento, para que el sub-modo "holographic"
        ajuste su environment (espacio negro en oscuro, crepúsculo
        azul en claro).

        Llamada al ``globe_ready`` (modo inicial) y cada vez que
        ``ThemeManager`` o ``LayerModeManager`` notifican un cambio.
        Es idempotente.
        """

        if self._view is None or not self._ready:
            return
        mode = self._compute_visual_mode()
        try:
            theme = ThemeManager.current_theme()    # "dark" | "light"
        except Exception:  # noqa: BLE001
            theme = "dark"
        payload_mode  = json.dumps(mode)
        payload_theme = json.dumps(theme)
        self._run_js(
            f"window.shakevisionGlobe.setVisualMode("
            f"{payload_mode}, {payload_theme});"
        )

    def push_favorited_event_ids(self, ids) -> None:
        """v0.6 Phase 13: empuja la lista de IDs de sismos favoritos.

        El JS resalta esos puntos con un ★ dorado encima + borde más
        grueso. Llamado desde MainWindow cuando FavoritesStore cambia.
        """

        if self._view is None or not self._ready:
            return
        payload = json.dumps(list(ids))
        self._run_js(
            f"window.shakevisionGlobe.setFavoritedEventIds({payload});"
        )

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------
    def _init_web_view(self, layout: QVBoxLayout) -> None:
        """Crea el QWebEngineView + QWebChannel (importación tardía)."""

        # Importación tardía: en algunos entornos sin QtWebEngine,
        # no queremos explotar al importar GlobePanel.
        from PySide6.QtWebChannel import QWebChannel
        from PySide6.QtWebEngineCore import QWebEngineSettings
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self._view = QWebEngineView(self)
        layout.addWidget(self._view, stretch=1)

        # ─── PERMISOS QtWebEngine ───
        # CRÍTICO: por defecto Chromium NO permite que las páginas
        # cargadas vía file:// hagan peticiones a https:// (CSP).
        # Globe.gl / Three.js viven en CDNs externas, así que este
        # toggle es indispensable o la página queda en blanco.
        settings = self._view.page().settings()
        settings.setAttribute(
            QWebEngineSettings.LocalContentCanAccessRemoteUrls, True
        )
        settings.setAttribute(
            QWebEngineSettings.LocalContentCanAccessFileUrls, True
        )

        # Capturar mensajes de la consola JS y enviarlos al logger Python.
        # Indispensable para depurar errores de carga de Globe.gl o de
        # peticiones bloqueadas por CSP.
        self._view.page().javaScriptConsoleMessage = self._on_js_console

        # Bridge + channel
        self._bridge = GlobeBridge()
        self._bridge.globe_ready.connect(self._on_globe_ready)
        self._bridge.station_clicked.connect(self.station_clicked)
        self._bridge.earthquake_clicked.connect(self.earthquake_clicked)
        self._bridge.period_changed.connect(self.period_changed)
        # v0.6 Phase 13
        self._bridge.favorite_toggled.connect(self.favorite_toggled)

        self._channel = QWebChannel(self._view.page())
        self._channel.registerObject("bridge", self._bridge)
        self._view.page().setWebChannel(self._channel)

        # Cargar la página HTML local
        index_path = WEB_GLOBE_DIR / "index.html"
        if not index_path.exists():
            raise FileNotFoundError(f"No se encontró {index_path}")
        self._view.load(QUrl.fromLocalFile(str(index_path)))

    @staticmethod
    def _on_js_console(level, message: str, line_number: int, source_id: str) -> None:
        """Reenvía mensajes de la consola JS al logger Python."""

        # level es un IntEnum: 0=Info, 1=Warning, 2=Error
        try:
            level_int = int(level)
        except Exception:
            level_int = 0
        prefix = ("INFO", "WARN", "ERROR")[min(level_int, 2)]
        short_src = source_id.rsplit("/", 1)[-1] if source_id else "?"
        logger.warning("[Globe JS %s] %s:%s %s",
                       prefix, short_src, line_number, message)

    def _fallback_label(self, reason: str) -> QLabel:
        """Etiqueta mostrada cuando no hay QtWebEngine."""

        label = QLabel(
            "🌍 La vista de globo 3D requiere QtWebEngine.\n\n"
            "Instálalo con:  pip install PySide6-Addons\n\n"
            f"Detalles: {reason}"
        )
        label.setWordWrap(True)
        label.setAlignment(label.alignment().Center)
        label.setStyleSheet(
            f"background-color: {COLOR_PANEL};"
            f" color: {COLOR_TEXT_SECONDARY};"
            f" border: 1px dashed {COLOR_PANEL_BORDER};"
            f" border-radius: 10px; padding: 24px;"
        )
        return label

    @Slot()
    def _on_globe_ready(self) -> None:
        """Marca el globo como listo y vuelca cualquier dato pendiente.

        Además oculta el overlay de carga en cuanto la página JS está
        operativa, sin esperar a que llegue el primer batch USGS. Así
        el usuario ve el globo (aunque vacío) inmediatamente y los
        puntos van apareciendo a medida que llegan los datos.
        """

        self._ready = True
        # Ocultar overlay tan pronto como el motor 3D está vivo.
        if hasattr(self, "_overlay"):
            self._overlay.hide_overlay()
        # Empujar la tabla de i18n al JS y suscribirse a cambios
        # de idioma para mantenerla actualizada en caliente.
        self.push_i18n()
        # v0.7.7 (B1): subscribe() — disconnect en destroyed + guarda.
        subscribe(self, LocaleService.language_changed_signal(),
                  self.push_i18n)
        # ─── Modo visual (día / noche / holográfico) ───
        # Empuja el modo inicial y se suscribe a cambios de Theme y
        # LayerMode para mantenerlo sincronizado. Sin esto, el globo
        # se queda siempre en "night" aunque el usuario alterne tema.
        self.push_visual_mode()
        subscribe(self, ThemeManager.changed_signal(),
                  self.push_visual_mode)  # v0.7.7 (B1)
        try:
            subscribe(self, LayerModeManager.changed_signal(),
                      self.push_visual_mode)  # v0.7.7 (B1)
        except Exception:  # noqa: BLE001
            pass
        if self._pending_stations is not None:
            self.update_stations(self._pending_stations)
            self._pending_stations = None
        if self._pending_quakes is not None:
            self.update_earthquakes(self._pending_quakes)
            self._pending_quakes = None

    def _run_js(self, code: str) -> None:
        """Helper que silencia la advertencia si la página aún no está lista."""

        page = self._view.page() if self._view else None
        if page is None:
            return
        page.runJavaScript(code)
