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

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
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
from shakevision.ui.theme import (
    COLOR_ACCENT,
    COLOR_ACCENT_WARM,
    COLOR_OK,
    COLOR_PANEL,
    COLOR_PANEL_BORDER,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    FONT_STACK_MONO,
    FONT_STACK_SANS,
)


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
_STATE_COLORS: dict[ConnectionState, str] = {
    ConnectionState.DISCONNECTED: COLOR_TEXT_MUTED,
    ConnectionState.CONNECTING:   COLOR_ACCENT_WARM,
    ConnectionState.CONNECTED:    COLOR_OK,
    ConnectionState.ERROR:        "#ef4444",
}

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

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(16)

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
        LocaleService.language_changed_signal().connect(self._retranslate)

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def set_station(self, label: str) -> None:
        """Actualiza el texto de la estación seleccionada."""

        self._station_label.setText(label or "—")

    def set_connection_state(self, state: ConnectionState) -> None:
        """Cambia el LED y el texto del estado de conexión."""

        self._connection_state = state
        color = _STATE_COLORS[state]
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
        """Logo emoji + nombre + tag de versión."""

        layout = QHBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)

        # Emoji como "logo": funciona en cualquier sistema sin assets
        logo = QLabel("🌐")
        logo_font = QFont()
        logo_font.setPointSize(18)
        logo.setFont(logo_font)
        logo.setObjectName("BrandLogo")
        layout.addWidget(logo)

        name = QLabel(app_name)
        name.setObjectName("BrandName")
        layout.addWidget(name)

        # Etiqueta de versión sutil al lado
        self._version_label = QLabel("v0.0.0")
        self._version_label.setObjectName("BrandVersion")
        layout.addWidget(self._version_label)

        return layout

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
        """Botones de acción global."""

        layout = QHBoxLayout()
        layout.setSpacing(6)
        layout.setContentsMargins(0, 0, 0, 0)

        # 🔬 Abrir Pro — banco de trabajo profesional (ventana flotante).
        # Es el primer botón porque es la acción más frecuente para
        # usuarios avanzados. Texto + emoji ayudan al descubrimiento.
        self._pro_button = QPushButton()
        self._pro_button.setObjectName("HeaderProButton")
        self._pro_button.setMinimumHeight(32)
        self._pro_button.clicked.connect(self.pro_clicked.emit)
        layout.addWidget(self._pro_button)

        # Toggle de tema (placeholder — implementación futura)
        self._theme_button = QPushButton("🌓")
        self._theme_button.setObjectName("HeaderActionButton")
        self._theme_button.setFixedSize(32, 32)
        self._theme_button.clicked.connect(self.theme_toggle_clicked.emit)
        layout.addWidget(self._theme_button)

        # Settings — abre el diálogo de preferencias
        self._settings_button = QPushButton("⚙")
        self._settings_button.setObjectName("HeaderActionButton")
        self._settings_button.setFixedSize(32, 32)
        self._settings_button.clicked.connect(self.settings_clicked.emit)
        layout.addWidget(self._settings_button)

        return layout

    # ------------------------------------------------------------------
    # Re-traducción al cambiar de idioma
    # ------------------------------------------------------------------
    def _retranslate(self) -> None:
        """Aplica las cadenas traducidas. Re-ejecutable en caliente."""

        self._pro_button.setText(t("header.action.pro"))
        self._pro_button.setToolTip(t("header.action.pro_tooltip"))
        self._theme_button.setToolTip(t("header.action.theme_tooltip"))
        self._settings_button.setToolTip(t("header.action.settings_tooltip"))
        # Re-pintar el texto del estado de conexión actual
        self.set_connection_state(self._connection_state)

    # ------------------------------------------------------------------
    # Estilos locales
    # ------------------------------------------------------------------
    @staticmethod
    def _build_qss() -> str:
        """Hoja de estilo específica de la cabecera."""

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

        QLabel#BrandVersion {{
            color: {COLOR_TEXT_MUTED};
            font-family: {FONT_STACK_MONO};
            font-size: 10px;
            padding-bottom: 2px;
        }}

        QLabel#HeaderStation {{
            color: {COLOR_TEXT_PRIMARY};
            font-family: {FONT_STACK_MONO};
            font-size: 13px;
            font-weight: 500;
        }}

        QLabel#HeaderSep {{
            color: {COLOR_TEXT_MUTED};
            font-size: 13px;
        }}

        QLabel#HeaderStatus {{
            color: {COLOR_TEXT_SECONDARY};
            font-family: {FONT_STACK_SANS};
            font-size: 12px;
        }}

        QPushButton#HeaderActionButton {{
            background-color: transparent;
            border: 1px solid transparent;
            border-radius: 8px;
            color: {COLOR_TEXT_SECONDARY};
            font-size: 16px;
            padding: 0;
        }}

        QPushButton#HeaderActionButton:hover {{
            background-color: rgba(255,255,255,0.04);
            border-color: {COLOR_PANEL_BORDER};
            color: {COLOR_TEXT_PRIMARY};
        }}

        QPushButton#HeaderActionButton:pressed {{
            background-color: {COLOR_ACCENT};
            color: white;
            border-color: {COLOR_ACCENT};
        }}

        QPushButton#HeaderProButton {{
            background-color: rgba(59,130,246,0.12);
            border: 1px solid {COLOR_ACCENT};
            border-radius: 8px;
            color: {COLOR_TEXT_PRIMARY};
            font-family: {FONT_STACK_SANS};
            font-size: 12px;
            font-weight: 500;
            padding: 0 12px;
        }}

        QPushButton#HeaderProButton:hover {{
            background-color: rgba(59,130,246,0.22);
        }}

        QPushButton#HeaderProButton:pressed {{
            background-color: {COLOR_ACCENT};
            color: white;
        }}
        """
