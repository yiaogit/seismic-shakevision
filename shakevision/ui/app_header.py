"""
Barra superior unificada de la aplicación.

Visualmente reemplaza al "menú clásico" como fuente principal de
información persistente. La barra de menús del sistema (``Archivo``,
``Ayuda`` …) sigue existiendo, pero esta cabecera personalizada
ofrece a primera vista:

  - Identidad de la app (logo + nombre).
  - Estado de conexión con un LED de tres colores.
  - Estación actualmente seleccionada.
  - Acciones globales (preferencias, cambio de tema — placeholders).

Diseño multiplataforma
----------------------
La cabecera es **completamente Qt** y se ve idéntica en macOS,
Windows y Linux: no usamos artefactos nativos. Las decoraciones
nativas del sistema (botones rojo/amarillo/verde en macOS,
minimizar/maximizar/cerrar en Windows) **se conservan en su lugar
habitual** del título del sistema. Esa elección evita los problemas
clásicos de las ventanas frameless (snap layouts en Windows 11,
fullscreen en macOS, decoraciones GNOME/KDE en Linux).
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from PySide6.QtCore import QSize, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QWidget,
)

from shakevision.i18n import LocaleService, t
from shakevision.ui.animations import clear_opacity_effect, make_pulse_opacity
from shakevision.ui.icons import clear_icon_cache, get_icon, logo_pixmap
from shakevision.ui.layer_mode_manager import LayerModeManager
from shakevision.ui.signal_safety import subscribe
# Las 5 constantes COLOR_ACCENT / COLOR_PANEL / COLOR_PANEL_BORDER /
# COLOR_TEXT_PRIMARY / COLOR_TEXT_SECONDARY se re-importan dentro de
# ``_build_qss`` vía ``from shakevision.ui import theme as _t`` porque
# necesitan leerse en cada cambio de tema (no se cachean al import).
# Solo dejamos arriba las que sí se usan a nivel módulo.
from shakevision.ui.theme import (
    FONT_STACK_MONO,
    FONT_STACK_SANS,
)
from shakevision.ui.theme_manager import ThemeManager


# Orden cíclico del botón de tema. Cada click avanza al siguiente.
# v0.7.6: ``"auto"`` eliminado del ciclo — el modo auto se quitó del
# ThemeManager por ambigüedad (chocaba con la preferencia de OS y
# generaba flips espurios al abrir el wizard durante el día).
_THEME_MODE_CYCLE: tuple[str, ...] = ("light", "dark")

# Emoji + clave i18n del tooltip por modo de tema.
_THEME_MODE_GLYPH: dict[str, str] = {
    "light": "☀",
    "dark":  "🌙",
}
_THEME_MODE_TOOLTIP_KEY: dict[str, str] = {
    "light": "header.theme.tooltip_light",
    "dark":  "header.theme.tooltip_dark",
}


# ============================================================
# Enumeración de estados de conexión
# ============================================================
class ConnectionState(Enum):
    """Posibles estados visibles del LED de conexión."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


# Color asociado a cada estado. El texto se obtiene de i18n en runtime
# para que cambie con el idioma sin recargar la app.
#
# v0.7.7 (B2): el color del LED se resuelve **en tiempo de ejecución**
# leyendo ``theme as _t`` en cada llamada, no al importar el módulo.
# Antes ``_STATE_COLORS`` cacheaba ``COLOR_*`` al import → el LED se
# quedaba con la paleta del arranque y no cambiaba al alternar tema
# (ver CLAUDE.md §4 "leer COLOR_* en paint time, no al import").
def _state_color(state: ConnectionState) -> str:
    """Color del LED para ``state`` leído del tema activo en runtime."""

    from shakevision.ui import theme as _t
    return {
        ConnectionState.DISCONNECTED: _t.COLOR_TEXT_MUTED,
        ConnectionState.CONNECTING:   _t.COLOR_ACCENT_WARM,
        ConnectionState.CONNECTED:    _t.COLOR_OK,
        ConnectionState.ERROR:        "#ef4444",
    }[state]

_STATE_I18N_KEYS: dict[ConnectionState, str] = {
    ConnectionState.DISCONNECTED: "header.status.disconnected",
    ConnectionState.CONNECTING:   "header.status.connecting",
    ConnectionState.CONNECTED:    "header.status.connected",
    ConnectionState.ERROR:        "header.status.error",
}


# ============================================================
# Widget principal
# ============================================================
class AppHeader(QFrame):
    """Barra superior fija con identidad y estado global."""

    settings_clicked = Signal()
    theme_toggle_clicked = Signal()
    pro_clicked = Signal()
    profile_clicked = Signal()

    HEIGHT_PX: int = 56

    def __init__(self, app_name: str, version: str,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("AppHeader")
        self.setFrameShape(QFrame.NoFrame)
        self.setFixedHeight(self.HEIGHT_PX)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # QSS local: este componente tiene una línea inferior sutil que
        # lo separa del contenido y un fondo ligeramente más oscuro que
        # el del panel para insinuar profundidad.
        self.setStyleSheet(self._build_qss())

        # v0.6: más padding lateral para respiración macOS-style.
        # 20px izquierda (logo), 14px derecha (acciones — más justas
        # porque hay más controles), spacing 14 entre secciones.
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 14, 0)
        layout.setSpacing(14)

        # ---------- Sección izquierda: logo + nombre ----------
        layout.addLayout(self._build_brand_section(app_name))

        # Separador flexible
        layout.addItem(QSpacerItem(16, 0, QSizePolicy.Fixed, QSizePolicy.Fixed))

        # ---------- Sección central: LED + estación ----------
        layout.addLayout(self._build_status_section())

        # Empuja todo lo siguiente al borde derecho
        layout.addStretch(1)

        # ---------- Sección derecha: acciones ----------
        layout.addLayout(self._build_actions_section())

        # Animación de pulso del LED (solo activa durante CONNECTING)
        self._led_pulse_animation = None

        # Estado inicial visible
        self._connection_state = ConnectionState.DISCONNECTED
        self.set_connection_state(ConnectionState.DISCONNECTED)
        self.set_station("—")
        self.set_version_tag(version)

        # Aplicar traducciones iniciales + suscribirse a cambios de idioma
        self._retranslate()
        subscribe(self, LocaleService.language_changed_signal(),
                  self._retranslate)  # v0.7.7 (B1)

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def set_station(self, label: str) -> None:
        """Actualiza el texto de la estación seleccionada."""

        self._station_label.setText(label or "—")

    def set_connection_state(self, state: ConnectionState) -> None:
        """Cambia el LED y el texto del estado de conexión."""

        self._connection_state = state
        color = _state_color(state)
        self._connection_text.setText(t(_STATE_I18N_KEYS[state]))
        # Reescribir solo la regla del LED para no rebuild todo el QSS
        self._led.setStyleSheet(
            f"QLabel#ConnectionLED {{ background-color: {color};"
            f" border-radius: 6px; min-width: 12px; max-width: 12px;"
            f" min-height: 12px; max-height: 12px; }}"
        )

        # Pulso de opacidad mientras estamos en "Conectando…": indica
        # actividad sin necesidad de cambiar el texto.
        if state == ConnectionState.CONNECTING:
            self._start_led_pulse()
        else:
            self._stop_led_pulse()

    def connection_state(self) -> ConnectionState:
        return self._connection_state

    def set_version_tag(self, version: str) -> None:
        """Etiqueta de versión mostrada junto al logo (estilo `v0.1.0`)."""

        self._version_label.setText(f"v{version}")

    # ------------------------------------------------------------------
    # Animación del LED
    # ------------------------------------------------------------------
    def _start_led_pulse(self) -> None:
        """Inicia el pulso de opacidad del LED si no está ya activo."""

        if self._led_pulse_animation is not None:
            return
        anim = make_pulse_opacity(self._led, duration_ms=900, min_opacity=0.25)
        anim.start()
        self._led_pulse_animation = anim

    def _stop_led_pulse(self) -> None:
        """Detiene el pulso y devuelve el LED a opacidad sólida."""

        if self._led_pulse_animation is None:
            return
        self._led_pulse_animation.stop()
        self._led_pulse_animation = None
        clear_opacity_effect(self._led)

    # ------------------------------------------------------------------
    # Construcción de secciones
    # ------------------------------------------------------------------
    def _build_brand_section(self, app_name: str) -> QHBoxLayout:
        """Logo PNG (rebrand v0.5) + etiqueta de versión.

        Antes había un emoji 🌐 + texto. La v0.5 sustituye ambos por
        el PNG real del rebrand SeismicGuard. El logo se cachea como
        QLabel y se reemplaza el pixmap al cambiar de tema (claro
        usa la variante navy, oscuro la blanca).

        Mantenemos un fallback de texto por si el PNG no se encuentra
        (instalación rota / pyinstaller sin --add-data) — así nunca
        se queda la barra superior vacía.
        """

        layout = QHBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)

        # ── Logo PNG ─────────────────────────────────────────────
        self._brand_logo = QLabel()
        self._brand_logo.setObjectName("BrandLogo")
        self._brand_logo.setFixedHeight(self.HEIGHT_PX - 24)   # margen vertical
        layout.addWidget(self._brand_logo)
        # Texto de fallback (oculto si el logo carga bien)
        self._brand_fallback = QLabel(app_name)
        self._brand_fallback.setObjectName("BrandName")
        self._brand_fallback.hide()
        layout.addWidget(self._brand_fallback)

        # Aplicar la imagen inicial según el tema actual.
        self._refresh_brand_logo()

        # Etiqueta de versión sutil al lado
        self._version_label = QLabel("v0.0.0")
        self._version_label.setObjectName("BrandVersion")
        layout.addWidget(self._version_label)

        # Re-pintar logo + iconos al cambiar tema en caliente
        # v0.7.7 (B1): subscribe() en vez de lambda — desconecta en
        # destroyed y no mantiene vivo el widget.
        from shakevision.ui.theme_manager import ThemeManager as _TM
        subscribe(self, _TM.changed_signal(), self._refresh_themed_assets)

        return layout

    def _refresh_brand_logo(self) -> None:
        """Carga el logo PNG correspondiente al tema activo en _brand_logo.

        Si el archivo no existe (o no se puede pintar), muestra el
        fallback de texto.
        """

        from shakevision.ui.theme_manager import ThemeManager as _TM
        theme = _TM.current_theme()
        # En modo claro usamos el logo con texto navy; en oscuro el blanco.
        pm = logo_pixmap(theme=theme, height=self.HEIGHT_PX - 24)
        if pm.isNull():
            self._brand_logo.hide()
            self._brand_fallback.show()
            return
        self._brand_logo.setPixmap(pm)
        self._brand_logo.show()
        self._brand_fallback.hide()

    def _refresh_themed_assets(self) -> None:
        """Re-aplica logo + iconos + QSS de los botones tras cambio de tema.

        v0.5.2: el QSS también se re-aplica para que los colores del
        AppHeader (fondo, borde inferior, segmented control) se
        actualicen al cambiar entre claro y oscuro. Sin esto, el
        AppHeader se quedaba con la paleta del arranque.
        """

        self._refresh_brand_logo()
        self._refresh_button_icons()
        # v0.7.7 (B2): re-pintar el LED de conexión con la paleta nueva.
        # Su color se resuelve en runtime, pero hay que re-aplicar el QSS
        # del LED para que el cambio sea visible sin esperar al próximo
        # cambio de estado de conexión.
        self.set_connection_state(self._connection_state)
        self.setStyleSheet(self._build_qss())

    def _build_status_section(self) -> QHBoxLayout:
        """LED + nombre de estación + estado textual."""

        layout = QHBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)

        # LED circular (12 px). El color se cambia desde set_connection_state.
        self._led = QLabel()
        self._led.setObjectName("ConnectionLED")
        self._led.setFixedSize(12, 12)
        layout.addWidget(self._led)

        # Nombre de la estación seleccionada (mono para que cuadrara fijo)
        self._station_label = QLabel("—")
        self._station_label.setObjectName("HeaderStation")
        layout.addWidget(self._station_label)

        # Pequeño separador "·" entre estación y estado
        sep = QLabel("·")
        sep.setObjectName("HeaderSep")
        layout.addWidget(sep)

        # Texto del estado de conexión
        self._connection_text = QLabel("Desconectado")
        self._connection_text.setObjectName("HeaderStatus")
        layout.addWidget(self._connection_text)

        return layout

    def _build_actions_section(self) -> QHBoxLayout:
        """Botones de acción global.

        Layout v0.5 阶段 N (de izquierda a derecha):
            [Workbench]  [STD|PRO segmented]  ·  [Theme] [Profile] [Settings]
        El " · " es un separador visual sutil (QFrame VLine) que agrupa
        las acciones de capa/modo de la sesión vs. las acciones globales.
        """

        layout = QHBoxLayout()
        layout.setSpacing(4)
        layout.setContentsMargins(0, 0, 0, 0)

        # 🔬 Abrir Pro / Workbench — banco de trabajo profesional.
        # El icono se asigna en _refresh_button_icons() para que cambie
        # con el tema (negro sobre claro, blanco sobre oscuro).
        self._pro_button = QPushButton()
        self._pro_button.setObjectName("HeaderProButton")
        self._pro_button.setMinimumHeight(32)
        self._pro_button.setIconSize(QSize(16, 16))
        self._pro_button.clicked.connect(self.pro_clicked.emit)
        layout.addWidget(self._pro_button)
        layout.addSpacing(4)

        # ── Modo Estándar / Profesional — segmented pill control ──
        # v0.5 阶段 N: en vez de un único toggle ambiguo ahora mostramos
        # AMBAS opciones como una "pildora" segmentada (estilo iOS
        # segmented control). El usuario ve qué modo está activo a
        # primera vista y puede clickear el otro para cambiar.
        self._mode_segment = QFrame()
        self._mode_segment.setObjectName("HeaderModeSegment")
        seg_layout = QHBoxLayout(self._mode_segment)
        seg_layout.setContentsMargins(2, 2, 2, 2)
        seg_layout.setSpacing(0)
        # Mantenemos ``_mode_button`` como ALIAS al botón "professional"
        # para preservar compatibilidad con tests existentes que lo
        # inspeccionan.
        self._mode_std_btn = QPushButton()
        self._mode_std_btn.setObjectName("HeaderModeSegmentBtn")
        self._mode_std_btn.setCheckable(True)
        self._mode_std_btn.setMinimumHeight(28)
        self._mode_std_btn.setProperty("seg_pos", "left")
        self._mode_pro_btn = QPushButton()
        self._mode_pro_btn.setObjectName("HeaderModeSegmentBtn")
        self._mode_pro_btn.setCheckable(True)
        self._mode_pro_btn.setMinimumHeight(28)
        self._mode_pro_btn.setProperty("seg_pos", "right")
        # Grupo exclusivo: solo uno marcado a la vez.
        from PySide6.QtWidgets import QButtonGroup as _QBG_n
        self._mode_seg_group = _QBG_n(self)
        self._mode_seg_group.setExclusive(True)
        self._mode_seg_group.addButton(self._mode_std_btn)
        self._mode_seg_group.addButton(self._mode_pro_btn)
        seg_layout.addWidget(self._mode_std_btn)
        seg_layout.addWidget(self._mode_pro_btn)
        # Alias para compatibilidad
        self._mode_button = self._mode_pro_btn
        # Estado inicial = lo que diga LayerModeManager
        is_pro_initial = LayerModeManager.current_mode() == "professional"
        self._mode_pro_btn.setChecked(is_pro_initial)
        self._mode_std_btn.setChecked(not is_pro_initial)
        # Conectar clicks. Usamos clicked (no toggled) para evitar
        # disparar al inicializar el checked state.
        self._mode_std_btn.clicked.connect(
            lambda: self._set_layer_mode_from_segment("standard"))
        self._mode_pro_btn.clicked.connect(
            lambda: self._set_layer_mode_from_segment("professional"))
        layout.addWidget(self._mode_segment)
        # Mantener el botón sincronizado si LayerModeManager cambia
        # desde otro lugar (p. ej. onboarding wizard).
        subscribe(self, LayerModeManager.changed_signal(),
                  self._on_layer_mode_changed)  # v0.7.7 (B1)

        # Separador visual sutil entre acciones de capa y acciones globales
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setObjectName("HeaderSeparator")
        sep.setFixedHeight(20)
        layout.addSpacing(4)
        layout.addWidget(sep)
        layout.addSpacing(4)

        # ── Cycle de tema: auto → light → dark → auto ─────────────────
        # Sustituye al placeholder ``🌓`` de v0.3. El emoji refleja el
        # modo actual, no el siguiente; el tooltip explica qué pasa al
        # pulsar.
        self._theme_button = QPushButton()
        self._theme_button.setObjectName("HeaderActionButton")
        self._theme_button.setFixedSize(32, 32)
        self._theme_button.clicked.connect(self._on_theme_button_clicked)
        layout.addWidget(self._theme_button)
        # Refresca el botón cuando el tema cambia desde otro lugar
        # (timer auto, onboarding, etc.).
        subscribe(self, ThemeManager.changed_signal(),
                  self._refresh_theme_button)  # v0.7.7 (B1)

        # Settings — abre el diálogo de preferencias.
        # Antes era el emoji "⚙"; ahora se usa el PNG rebranded vía
        # icons.get_icon, que se re-pinta con el tema (claro/oscuro).
        self._settings_button = QPushButton()
        self._settings_button.setObjectName("HeaderActionButton")
        self._settings_button.setFixedSize(32, 32)
        self._settings_button.setIconSize(QSize(18, 18))
        self._settings_button.clicked.connect(self.settings_clicked.emit)
        layout.addWidget(self._settings_button)

        # Profile / Usuario — abre la página personal (v0.5 阶段 L).
        # Si el usuario hizo login con GitHub, muestra su perfil con
        # avatar; si no, muestra "Guest" + botón Sign in.
        self._profile_button = QPushButton()
        self._profile_button.setObjectName("HeaderActionButton")
        self._profile_button.setFixedSize(32, 32)
        self._profile_button.setIconSize(QSize(18, 18))
        self._profile_button.clicked.connect(self.profile_clicked.emit)
        layout.addWidget(self._profile_button)

        # Asignar iconos iniciales según el tema actual.
        # (Después se llaman desde _refresh_themed_assets al cambiar.)
        self._refresh_button_icons()

        # v0.6: micro-animación hover/press macOS-style en todos los
        # botones de acción. Sin esto los QSS :hover son cambios duros
        # de 0 ms — con esto la transición es ~150 ms ease.
        try:
            from shakevision.ui.animations import attach_hover_press
            for btn in (self._pro_button, self._theme_button,
                        self._settings_button, self._profile_button):
                attach_hover_press(btn)
        except Exception:  # noqa: BLE001
            pass

        return layout

    # ------------------------------------------------------------------
    # Iconos de botones — sensibles al tema
    # ------------------------------------------------------------------
    def _refresh_button_icons(self) -> None:
        """Re-pinta los iconos de los botones de acción según el tema.

        Se invoca al construir la cabecera y cada vez que
        ``ThemeManager`` emite ``theme_changed``. Limpia la caché del
        módulo ``icons`` para que el recolor se haga con la paleta
        correcta (los QIcon están cacheados por color).
        """

        theme = ThemeManager.current_theme()
        # La caché está parametrizada por color, no por modo; al
        # cambiar de tema queremos forzar el repintado con el color
        # nuevo. clear_icon_cache es barato.
        clear_icon_cache()

        if hasattr(self, "_settings_button"):
            self._settings_button.setIcon(
                get_icon("settings", theme=theme, size=64)
            )
        if hasattr(self, "_pro_button"):
            self._pro_button.setIcon(
                get_icon("workbench", theme=theme, size=64)
            )
        if hasattr(self, "_profile_button"):
            self._profile_button.setIcon(
                get_icon("user", theme=theme, size=64)
            )

    # ------------------------------------------------------------------
    # Slots de los nuevos botones (theme cycle + mode toggle)
    # ------------------------------------------------------------------
    def _on_theme_button_clicked(self) -> None:
        """Avanza al siguiente modo del cycle (v0.7.6: solo light↔dark)."""

        current = ThemeManager.mode()
        try:
            idx = _THEME_MODE_CYCLE.index(current)
        except ValueError:
            idx = 0
        next_mode = _THEME_MODE_CYCLE[(idx + 1) % len(_THEME_MODE_CYCLE)]
        ThemeManager.set_mode(next_mode)         # type: ignore[arg-type]
        # No es necesario refrescar el botón aquí: la señal
        # ``theme_changed`` lo hace.
        # Reemitir señal de compatibilidad (algún test/código viejo
        # podría seguir suscrito).
        self.theme_toggle_clicked.emit()

    def _on_mode_button_clicked(self) -> None:
        """Toggle entre estándar y profesional (legacy — sustituido por
        el segmented control)."""

        next_mode = "professional" if self._mode_button.isChecked() else "standard"
        LayerModeManager.set_mode(next_mode)     # type: ignore[arg-type]

    def _set_layer_mode_from_segment(self, target: str) -> None:
        """Aplicado al click en uno de los dos botones del segmented.

        El QButtonGroup exclusivo se encarga del estado visual; aquí
        solo propagamos al manager si el modo cambia realmente.
        """

        if target == LayerModeManager.current_mode():
            return
        LayerModeManager.set_mode(target)         # type: ignore[arg-type]

    def _on_layer_mode_changed(self, mode: str) -> None:
        """Refresca el segmented control cuando LayerModeManager cambia
        desde otro lugar (onboarding wizard, atajo de teclado, etc.)."""

        is_pro = (mode == "professional")
        # blockSignals para evitar reentradas; el grupo es exclusivo
        if hasattr(self, "_mode_std_btn"):
            self._mode_std_btn.blockSignals(True)
            self._mode_pro_btn.blockSignals(True)
            self._mode_std_btn.setChecked(not is_pro)
            self._mode_pro_btn.setChecked(is_pro)
            self._mode_std_btn.blockSignals(False)
            self._mode_pro_btn.blockSignals(False)
        self._refresh_mode_button_text()

    def _refresh_theme_button(self) -> None:
        """Re-pinta emoji + tooltip del botón de tema."""

        mode = ThemeManager.mode()
        # v0.7.6: fallback al emoji/tooltip de "dark" (era "🌓"/"auto"
        # antes de quitar el modo auto).
        glyph = _THEME_MODE_GLYPH.get(mode, "🌙")
        self._theme_button.setText(glyph)
        self._theme_button.setToolTip(
            t(_THEME_MODE_TOOLTIP_KEY.get(mode, "header.theme.tooltip_dark"))
        )

    def _refresh_mode_button_text(self) -> None:
        """Re-pinta etiquetas + tooltips del segmented control.

        En v0.5 阶段 N AMBOS botones del segmented muestran su nombre
        siempre (no solo el activo). El tooltip describe a qué cambias
        al pulsar — así el usuario sabe que es un toggle de "qué quieres",
        no un toggle de "alterna".
        """

        if hasattr(self, "_mode_std_btn"):
            self._mode_std_btn.setText(t("header.mode.standard"))
            self._mode_pro_btn.setText(t("header.mode.professional"))
            self._mode_std_btn.setToolTip(t("header.mode.tooltip_standard"))
            self._mode_pro_btn.setToolTip(t("header.mode.tooltip_professional"))

    # ------------------------------------------------------------------
    # Re-traducción al cambiar de idioma
    # ------------------------------------------------------------------
    def _retranslate(self) -> None:
        """Aplica las cadenas traducidas. Re-ejecutable en caliente."""

        self._pro_button.setText(t("header.action.pro"))
        self._pro_button.setToolTip(t("header.action.pro_tooltip"))
        self._settings_button.setToolTip(t("header.action.settings_tooltip"))
        if hasattr(self, "_profile_button"):
            self._profile_button.setToolTip(
                t("header.action.profile_tooltip"))
        # Botones nuevos (v0.4): theme cycle + std/pro toggle
        self._refresh_theme_button()
        self._refresh_mode_button_text()
        # Re-pintar el texto del estado de conexión actual
        self.set_connection_state(self._connection_state)

    # ------------------------------------------------------------------
    # Estilos locales
    # ------------------------------------------------------------------
    @staticmethod
    def _build_qss() -> str:
        """Hoja de estilo específica de la cabecera.

        v0.5.2: leemos los colores del módulo theme **en tiempo de
        ejecución** (no de imports cacheados al cargar el módulo).
        Esto es lo que permite que ``setStyleSheet(self._build_qss())``
        después de un cambio de tema use la paleta nueva.
        """

        from shakevision.ui import theme as _t
        COLOR_PANEL          = _t.COLOR_PANEL
        COLOR_PANEL_ELEVATED = _t.COLOR_PANEL_ELEVATED
        COLOR_PANEL_BORDER   = _t.COLOR_PANEL_BORDER
        COLOR_TEXT_PRIMARY   = _t.COLOR_TEXT_PRIMARY
        COLOR_TEXT_SECONDARY = _t.COLOR_TEXT_SECONDARY
        COLOR_TEXT_MUTED     = _t.COLOR_TEXT_MUTED
        COLOR_ACCENT         = _t.COLOR_ACCENT

        return f"""
        QFrame#AppHeader {{
            background-color: {COLOR_PANEL};
            border-bottom: 1px solid {COLOR_PANEL_BORDER};
        }}

        QLabel#BrandName {{
            color: {COLOR_TEXT_PRIMARY};
            font-family: {FONT_STACK_SANS};
            font-size: 14px;
            font-weight: 600;
            letter-spacing: 0.2px;
        }}

        /* v0.6: BrandVersion como un "chip" sutil panel_elevated */
        QLabel#BrandVersion {{
            color: {COLOR_TEXT_MUTED};
            background-color: {COLOR_PANEL_ELEVATED};
            border: 1px solid {COLOR_PANEL_BORDER};
            font-family: {FONT_STACK_MONO};
            font-size: 10px;
            font-weight: 500;
            padding: 2px 7px;
            border-radius: 5px;
            margin-bottom: 0;
        }}

        QLabel#HeaderStation {{
            color: {COLOR_TEXT_PRIMARY};
            font-family: {FONT_STACK_MONO};
            font-size: 12px;
            font-weight: 600;
        }}

        QLabel#HeaderSep {{
            color: {COLOR_TEXT_MUTED};
            font-size: 12px;
        }}

        QLabel#HeaderStatus {{
            color: {COLOR_TEXT_SECONDARY};
            font-family: {FONT_STACK_SANS};
            font-size: 11px;
            font-weight: 500;
        }}

        /* Header icon-only buttons (theme / profile / settings).
           v0.6: hover usa panel_elevated dinámico (antes rgba blanco
           hardcoded sólo funcionaba en oscuro). Sin font-size hack
           porque ahora son icon-only (setIcon + setIconSize). */
        QPushButton#HeaderActionButton {{
            background-color: transparent;
            border: 1px solid transparent;
            border-radius: 8px;
            color: {COLOR_TEXT_SECONDARY};
            padding: 0;
        }}
        QPushButton#HeaderActionButton:hover {{
            background-color: {COLOR_PANEL_ELEVATED};
            border-color: {COLOR_PANEL_BORDER};
            color: {COLOR_TEXT_PRIMARY};
        }}
        QPushButton#HeaderActionButton:pressed {{
            background-color: {COLOR_ACCENT};
            color: white;
            border-color: {COLOR_ACCENT};
        }}

        /* Workbench — botón secundario macOS-style. v0.6: dejamos de
           usar rgba hardcoded (#3b82f6) que chocaba con el nuevo
           accent #0a84ff y delegamos en panel_elevated dinámico. */
        QPushButton#HeaderProButton {{
            background-color: {COLOR_PANEL};
            border: 1px solid {COLOR_PANEL_BORDER};
            border-radius: 8px;
            color: {COLOR_TEXT_PRIMARY};
            font-family: {FONT_STACK_SANS};
            font-size: 12px;
            font-weight: 500;
            padding: 0 14px;
        }}
        QPushButton#HeaderProButton:hover {{
            background-color: {COLOR_ACCENT};
            color: white;
            border-color: {COLOR_ACCENT};
        }}
        QPushButton#HeaderProButton:pressed {{
            background-color: {COLOR_ACCENT};
            color: white;
        }}

        /* ── Toggle STD / PRO LEGACY (no usado pero conservado) ──── */
        QPushButton#HeaderModeButton {{
            background-color: transparent;
            border: 1px solid {COLOR_PANEL_BORDER};
            border-radius: 8px;
            color: {COLOR_TEXT_SECONDARY};
            font-family: {FONT_STACK_SANS};
            font-size: 11px;
            font-weight: 600;
            letter-spacing: 0.6px;
            padding: 0 10px;
            min-width: 64px;
        }}
        QPushButton#HeaderModeButton:hover {{
            color: {COLOR_TEXT_PRIMARY};
            border-color: {COLOR_ACCENT};
        }}
        QPushButton#HeaderModeButton:checked {{
            background-color: {COLOR_ACCENT};
            color: white;
            border-color: {COLOR_ACCENT};
        }}

        /* ── Segmented STD | PRO (v0.5 阶段 N) ──────────────────────
           Contenedor con borde redondeado; los dos botones internos
           comparten ese borde virtual y el seleccionado se llena con
           accent. El truco visual: bordes left/right cero en cada
           botón y radio solo en el extremo correspondiente. */
        QFrame#HeaderModeSegment {{
            background-color: {COLOR_PANEL};
            border: 1px solid {COLOR_PANEL_BORDER};
            border-radius: 9px;
        }}
        QPushButton#HeaderModeSegmentBtn {{
            background-color: transparent;
            border: none;
            color: {COLOR_TEXT_SECONDARY};
            font-family: {FONT_STACK_SANS};
            font-size: 11px;
            font-weight: 600;
            letter-spacing: 0.6px;
            padding: 0 12px;
            min-width: 52px;
            border-radius: 7px;
        }}
        QPushButton#HeaderModeSegmentBtn:hover {{
            color: {COLOR_TEXT_PRIMARY};
        }}
        QPushButton#HeaderModeSegmentBtn:checked {{
            background-color: {COLOR_ACCENT};
            color: white;
        }}

        /* ── Separador vertical sutil entre grupos de acciones ───── */
        QFrame#HeaderSeparator {{
            color: {COLOR_PANEL_BORDER};
            background-color: {COLOR_PANEL_BORDER};
            max-width: 1px;
        }}
        """
