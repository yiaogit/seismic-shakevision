"""
Sistema de temas (claro / oscuro) de SeismicGuard.

Histórico
---------
La v0.4 introduce un **sistema dual**: light + dark. Antes solo había
un tema oscuro hardcoded. Para no romper imports existentes:

  * Los símbolos ``COLOR_*`` siguen siendo accesibles a nivel módulo.
  * Su VALOR puede cambiar al vuelo cuando ``apply_theme()`` se ejecuta.
  * Las widgets que ya usaban ``from shakevision.ui.theme import
    COLOR_X`` siguen recibiendo el valor del tema activo en el momento
    de IMPORT, lo que basta para la mayoría de cosas (stylesheet de
    QApplication se reaplica al cambiar tema y cascadea a todos los
    QWidget hijos).

Limitación conocida
-------------------
pyqtgraph guarda los pen colors en el __init__ del PlotWidget; tras un
cambio de tema en caliente los plots existentes seguirán pintando los
colores antiguos. Está marcado como TODO v0.6 — la solución correcta
es que cada widget pyqtgraph se subscriba a ThemeManager.theme_changed
y rebuild su pen. Para v0.5 el usuario verá los plots actualizar al
reiniciar.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Literal

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication


logger = logging.getLogger(__name__)


ThemeName = Literal["dark", "light"]


# ============================================================
# Paletas — v0.6 rediseño inspirado en macOS Sonoma + ChromeOS M3
# ============================================================
#
# Filosofía
# ---------
# Las paletas se construyen como sistemas tonales, no como colores
# sueltos. Cada paleta tiene:
#
#   * 3 niveles de **surface** (background / panel / elevated) que
#     forman jerarquía de elevación visual.
#   * 3 niveles de **label** (primary / secondary / muted) que
#     comunican prioridad de información.
#   * Borde y divisor en **rgba** (no hex), lo que produce
#     "hairlines" iOS-style en lugar de líneas opacas duras.
#   * Accent azul sistema (macOS `#0a84ff`), reemplaza el dorado
#     anterior que se sentía "amateur".
#
# La estructura es ESPEJO entre dark y light — mismas keys, valores
# análogos. Esto hace trivial el cambio de tema en caliente.

# DARK — basado en macOS dark mode (#000000 desktop, #1C1C1E cards).
#
# NOTA sobre los bordes: usamos solid hex (no rgba) porque QColor en
# algunas versiones de PySide6 no parsea rgba() strings de forma
# fiable. Los valores elegidos aproximan visualmente al "hairline"
# semi-transparente de macOS (~8% de la inversa del fondo):
#   * Dark:  rgba(255,255,255,0.08) ≈ #2c2c2e sobre #1a1a1f
#   * Light: rgba(0,0,0,0.08)       ≈ #e5e5ea sobre #ffffff
# Son los `systemGray5` de macOS — coincidencia conveniente.
DARK_PALETTE: dict[str, str] = {
    # Surfaces (3 niveles de elevación)
    "background":     "#0d0d10",
    "panel":          "#1a1a1f",
    "panel_elevated": "#26262d",
    "panel_border":   "#2c2c2e",   # macOS systemGray5 (dark)
    "panel_divider":  "#1f1f24",
    # Labels (3 niveles de contraste de texto)
    "text_primary":   "#fafafa",
    "text_secondary": "#a1a1aa",
    "text_muted":     "#71717a",
    # Accent — macOS system blue (uniforme dark/light)
    "accent":         "#0a84ff",
    "accent_hover":   "#3395ff",
    "accent_glow":    "#0040c4",
    "accent_warm":    "#ff9f0a",
    "alert":          "#ff453a",
    "alert_glow":     "#5e1e1c",
    "ok":             "#30d158",
}

# LIGHT — basado en macOS light mode (#F5F5F7 background, #ffffff
# cards, labels gris oscuro). v0.6: drop del dorado anterior; el
# accent ahora es system blue — se siente más "producto serio" y
# menos "tema de Bootstrap 2012".
LIGHT_PALETTE: dict[str, str] = {
    # Surfaces — gradación suave (fondo gris → cards blancas)
    "background":     "#f2f2f7",   # macOS systemGray6 (fondo ventana)
    "panel":          "#ffffff",   # tarjetas / sheets
    "panel_elevated": "#fafafd",   # hover / popover
    # Hairlines aproximadas con solid hex (ver nota arriba)
    "panel_border":   "#e5e5ea",   # macOS systemGray5
    "panel_divider":  "#efeff4",   # más sutil aún para divisores
    # Labels — neutrales (NO navy), grises de macOS
    "text_primary":   "#1d1d1f",   # macOS label primary
    "text_secondary": "#6e6e73",   # macOS label secondary
    "text_muted":     "#8e8e93",   # macOS label tertiary
    # Accent — system blue (mismo que dark mode para coherencia)
    "accent":         "#0a84ff",
    "accent_hover":   "#3395ff",
    "accent_glow":    "#0040c4",
    "accent_warm":    "#ff9500",   # macOS systemOrange
    "alert":          "#ff3b30",   # macOS systemRed
    "alert_glow":     "#ffe5e3",
    "ok":             "#34c759",   # macOS systemGreen
}

_PALETTES: dict[ThemeName, dict[str, str]] = {
    "dark":  DARK_PALETTE,
    "light": LIGHT_PALETTE,
}


# ============================================================
# Constantes "vivas" (mutadas por apply_theme)
# ============================================================
# Estas variables se inicializan al módulo con el dark palette para
# que cualquier import existente siga compilando. Cuando se aplica un
# tema nuevo via ``apply_theme()`` reasignamos sus valores; los códigos
# que hacen ``from shakevision.ui.theme import COLOR_BACKGROUND`` en
# el momento de carga del módulo recibirán EL VALOR ACTUAL.

COLOR_BACKGROUND      = DARK_PALETTE["background"]
COLOR_PANEL           = DARK_PALETTE["panel"]
COLOR_PANEL_ELEVATED  = DARK_PALETTE["panel_elevated"]
COLOR_PANEL_BORDER    = DARK_PALETTE["panel_border"]
COLOR_PANEL_DIVIDER   = DARK_PALETTE["panel_divider"]

COLOR_TEXT_PRIMARY    = DARK_PALETTE["text_primary"]
COLOR_TEXT_SECONDARY  = DARK_PALETTE["text_secondary"]
COLOR_TEXT_MUTED      = DARK_PALETTE["text_muted"]

COLOR_ACCENT          = DARK_PALETTE["accent"]
COLOR_ACCENT_HOVER    = DARK_PALETTE["accent_hover"]
COLOR_ACCENT_GLOW     = DARK_PALETTE["accent_glow"]
COLOR_ACCENT_WARM     = DARK_PALETTE["accent_warm"]
COLOR_ALERT           = DARK_PALETTE["alert"]
COLOR_ALERT_GLOW      = DARK_PALETTE["alert_glow"]
COLOR_OK              = DARK_PALETTE["ok"]

# Tema actual (escrito por apply_theme).
_active_theme: ThemeName = "dark"


def current_palette() -> dict[str, str]:
    """Devuelve el dict de la paleta activa (referencia, no copia)."""
    return _PALETTES[_active_theme]


def current_theme() -> ThemeName:
    return _active_theme


# Colores de los tres canales de forma de onda. Estos NO cambian con
# el tema porque son señal de información (Z / N / E) y deben ser
# inmediatamente reconocibles independiente del fondo.
WAVEFORM_COLORS = {
    "Z": "#3b82f6",
    "N": "#f97316",
    "E": "#10b981",
}


# ============================================================
# Tipografía (no cambia con el tema)
# ============================================================
FONT_STACK_SANS = (
    '"Inter Variable", "Inter", '
    '"-apple-system", "SF Pro Text", '
    '"Segoe UI Variable", "Segoe UI", '
    '"PingFang SC", "Microsoft YaHei", '
    '"Helvetica Neue", sans-serif'
)
FONT_STACK_MONO = (
    '"JetBrains Mono", "SF Mono", "Monaco", '
    '"Cascadia Code", "Consolas", "Menlo", monospace'
)
FONT_SIZE_DEFAULT = 13
FONT_SIZE_LABEL   = 11
FONT_SIZE_VALUE   = 14
FONT_SIZE_TITLE   = 12


# ============================================================
# QSS generado dinámicamente desde la paleta activa
# ============================================================
def _build_qss(p: dict[str, str]) -> str:
    """Construye el QSS leyendo la paleta ``p``.

    v0.6 redesign — inspirado en macOS Sonoma + Material 3:

      * Botones primarios FILL con accent, secundarios con surface_elevated.
      * Inputs: pill rounded (8px) + focus halo accent.
      * Sliders: track delgado + handle blanco con sombra accent (iOS).
      * Tabs: capsule highlight para selección, no solo underline.
      * Cards: hairline + radius 12, sin sombra dura.
      * ComboBox dropdown: popup elevado con radius 10.
      * Spacing: 8px base — todos los paddings múltiplos de 4.
    """

    return f"""
    /* ── BASE ─────────────────────────────────────────────── */
    QWidget {{
        background-color: {p["background"]};
        color: {p["text_primary"]};
        font-family: {FONT_STACK_SANS};
        font-size: {FONT_SIZE_DEFAULT}px;
    }}

    /* ── CARDS / PANELS ──────────────────────────────────── */
    QFrame#ControlPanel, QFrame#WaveformPanel {{
        background-color: {p["panel"]};
        border: 1px solid {p["panel_border"]};
        border-radius: 12px;
    }}
    QFrame#WaveformPanel[alert="true"] {{
        border: 2px solid {p["alert"]};
        background-color: {p["panel_elevated"]};
    }}

    /* ── TÍTULOS / TEXTO ────────────────────────────────── */
    QLabel#SectionTitle {{
        color: {p["text_secondary"]};
        font-weight: 600;
        font-size: {FONT_SIZE_LABEL}px;
        letter-spacing: 0.6px;
        text-transform: uppercase;
        padding: 8px 0px 6px 0px;
    }}
    QLabel#StatusValue {{
        color: {p["text_primary"]};
        font-family: {FONT_STACK_MONO};
        font-size: {FONT_SIZE_VALUE}px;
        font-weight: 500;
    }}
    QLabel#StatusOk    {{ color: {p["ok"]};          font-weight: 600; }}
    QLabel#StatusWarn  {{ color: {p["accent_warm"]}; font-weight: 600; }}
    QLabel#StatusAlert {{ color: {p["alert"]};       font-weight: 600; }}

    /* ── INPUTS (ComboBox, SpinBox, LineEdit, DateTime) ──
       Estilo "pill" macOS: rounded 8px, padding cómodo, focus
       con halo accent en lugar de border duro. */
    QComboBox, QDoubleSpinBox, QSpinBox, QLineEdit, QDateTimeEdit {{
        background-color: {p["panel"]};
        color: {p["text_primary"]};
        border: 1px solid {p["panel_border"]};
        border-radius: 8px;
        padding: 7px 12px;
        selection-background-color: {p["accent"]};
        selection-color: white;
        min-height: 18px;
    }}
    QComboBox:hover, QDoubleSpinBox:hover, QSpinBox:hover,
    QLineEdit:hover, QDateTimeEdit:hover {{
        background-color: {p["panel_elevated"]};
    }}
    QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus,
    QLineEdit:focus, QDateTimeEdit:focus {{
        border: 2px solid {p["accent"]};
        padding: 6px 11px;   /* compensa el +1px de border */
    }}
    QComboBox:disabled, QDoubleSpinBox:disabled, QSpinBox:disabled,
    QLineEdit:disabled, QDateTimeEdit:disabled {{
        color: {p["text_muted"]};
        background-color: {p["panel"]};
    }}
    QComboBox::drop-down {{ border: 0; width: 22px; }}
    QComboBox QAbstractItemView {{
        background-color: {p["panel_elevated"]};
        color: {p["text_primary"]};
        border: 1px solid {p["panel_border"]};
        border-radius: 10px;
        padding: 6px;
        selection-background-color: {p["accent"]};
        selection-color: white;
        outline: 0;
    }}

    /* ── BUTTONS ──────────────────────────────────────────
       Estilo macOS: secundarios suaves (surface_elevated),
       primarios FILL con accent. La diferenciación se hace por
       objectName, no por modal — los botones marcados como
       PrimaryButton llevan fill, el resto van secundarios. */
    QPushButton {{
        background-color: {p["panel_elevated"]};
        color: {p["text_primary"]};
        border: 1px solid {p["panel_border"]};
        border-radius: 8px;
        padding: 8px 18px;
        font-weight: 500;
        min-height: 18px;
    }}
    QPushButton:hover {{
        background-color: {p["panel"]};
        border-color: {p["text_muted"]};
    }}
    QPushButton:pressed {{
        background-color: {p["panel_divider"]};
    }}
    QPushButton:disabled {{
        color: {p["text_muted"]};
        background-color: {p["panel"]};
    }}
    QPushButton:focus {{
        border: 2px solid {p["accent"]};
        padding: 7px 17px;
    }}
    QPushButton[primary="true"], QPushButton#PrimaryButton {{
        background-color: {p["accent"]};
        color: white;
        border: 1px solid {p["accent"]};
        font-weight: 600;
    }}
    QPushButton[primary="true"]:hover, QPushButton#PrimaryButton:hover {{
        background-color: {p["accent_hover"]};
        border-color: {p["accent_hover"]};
    }}
    QPushButton[primary="true"]:pressed, QPushButton#PrimaryButton:pressed {{
        background-color: {p["accent_glow"]};
    }}

    /* ── SLIDERS (iOS-style) ───────────────────────────── */
    QSlider::groove:horizontal {{
        height: 4px;
        background: {p["panel_border"]};
        border-radius: 2px;
    }}
    QSlider::sub-page:horizontal {{
        background: {p["accent"]};
        border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        background: #ffffff;
        width: 20px; height: 20px;
        margin: -9px 0;
        border-radius: 10px;
        border: 1px solid {p["panel_border"]};
    }}
    QSlider::handle:horizontal:hover {{
        background: {p["panel_elevated"]};
    }}

    /* ── CHECKBOX / RADIO ──────────────────────────────── */
    QCheckBox, QRadioButton {{
        spacing: 8px;
        color: {p["text_primary"]};
    }}
    QCheckBox::indicator, QRadioButton::indicator {{
        width: 18px; height: 18px;
        border: 1px solid {p["panel_border"]};
        background-color: {p["panel"]};
    }}
    QCheckBox::indicator {{ border-radius: 5px; }}
    QRadioButton::indicator {{ border-radius: 9px; }}
    QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
        border-color: {p["accent"]};
    }}
    QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
        background-color: {p["accent"]};
        border-color: {p["accent"]};
    }}

    /* ── TABS (capsule highlight v0.6) ─────────────────── */
    QTabWidget::pane {{
        border: 1px solid {p["panel_border"]};
        border-radius: 12px;
        top: -1px;
        background-color: {p["panel"]};
    }}
    QTabBar::tab {{
        background-color: transparent;
        color: {p["text_secondary"]};
        padding: 8px 16px;
        border: none;
        margin: 4px 2px 4px 0;
        font-weight: 500;
        min-height: 22px;
        border-radius: 8px;
    }}
    QTabBar::tab:hover {{
        color: {p["text_primary"]};
        background-color: {p["panel_elevated"]};
    }}
    QTabBar::tab:selected {{
        color: {p["accent"]};
        background-color: {p["panel_elevated"]};
        font-weight: 600;
    }}

    /* ── STATUS BAR (hairline footer) ──────────────────── */
    QStatusBar {{
        background: {p["background"]};
        border-top: 1px solid {p["panel_border"]};
        padding: 4px 12px;
        color: {p["text_secondary"]};
    }}
    QStatusBar QLabel {{ padding: 0 8px; color: {p["text_secondary"]}; }}

    /* ── SPLITTER ─────────────────────────────────────── */
    QSplitter::handle              {{ background-color: {p["panel_divider"]}; }}
    QSplitter::handle:horizontal   {{ width: 3px; }}
    QSplitter::handle:vertical     {{ height: 3px; }}
    QSplitter::handle:hover        {{ background-color: {p["accent"]}; }}

    /* ── MENUS (macOS-style popovers) ──────────────────── */
    QMenuBar {{
        background-color: {p["background"]};
        border-bottom: 1px solid {p["panel_border"]};
        padding: 2px 6px;
    }}
    QMenuBar::item {{
        padding: 6px 12px;
        background: transparent;
        border-radius: 6px;
    }}
    QMenuBar::item:selected {{
        background-color: {p["panel_elevated"]};
    }}
    QMenu {{
        background-color: {p["panel_elevated"]};
        border: 1px solid {p["panel_border"]};
        border-radius: 10px;
        padding: 6px;
    }}
    QMenu::item {{
        padding: 7px 28px 7px 16px;
        border-radius: 6px;
    }}
    QMenu::item:selected {{
        background-color: {p["accent"]};
        color: white;
    }}

    /* ── SCROLLBARS (sutiles, macOS-style) ────────────── */
    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {p["text_muted"]};
        border-radius: 4px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {p["text_secondary"]};
    }}
    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 10px;
        margin: 2px;
    }}
    QScrollBar::handle:horizontal {{
        background: {p["text_muted"]};
        border-radius: 4px;
        min-width: 30px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {p["text_secondary"]};
    }}
    QScrollBar::add-line:horizontal,
    QScrollBar::sub-line:horizontal {{ width: 0; }}

    /* ── TOOLTIPS (macOS-style chip) ──────────────────── */
    QToolTip {{
        background-color: {p["panel_elevated"]};
        color: {p["text_primary"]};
        border: 1px solid {p["panel_border"]};
        border-radius: 6px;
        padding: 6px 10px;
        font-size: {FONT_SIZE_LABEL}px;
    }}

    /* ── DIALOG ──────────────────────────────────────── */
    QDialog {{
        background-color: {p["background"]};
    }}
    /* v0.6 unified dialog hint/empty/separator selectors — usados
       en SettingsDialog y otros para no hardcodear rgba en cada
       label individual. */
    QLabel#DialogHint {{
        color: {p["text_muted"]};
        font-size: {FONT_SIZE_LABEL}px;
    }}
    QLabel#DialogEmpty {{
        color: {p["text_muted"]};
        font-size: {FONT_SIZE_DEFAULT}px;
        padding: 24px;
    }}
    QFrame#DialogSeparator {{
        color: {p["panel_border"]};
        background-color: {p["panel_border"]};
        max-height: 1px;
    }}
    QLabel#SettingsSectionTitle {{
        color: {p["text_primary"]};
        font-weight: 600;
        font-size: {FONT_SIZE_VALUE}px;
        padding: 4px 0 2px 0;
    }}
    """


# ============================================================
# Carga de fuentes empaquetadas (sin cambio respecto a v0.3)
# ============================================================
ASSETS_FONTS_DIR: Path = Path(__file__).resolve().parent.parent / "assets" / "fonts"


def _load_bundled_fonts() -> list[str]:
    families: list[str] = []
    if not ASSETS_FONTS_DIR.exists():
        return families
    for path in ASSETS_FONTS_DIR.iterdir():
        if path.suffix.lower() not in {".ttf", ".otf"}:
            continue
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id == -1:
            continue
        families.extend(QFontDatabase.applicationFontFamilies(font_id))
    return families


# ============================================================
# API pública
# ============================================================
def apply_theme(app: QApplication, theme: ThemeName = "dark") -> Iterable[str]:
    """Aplica la paleta y la hoja de estilo del tema indicado.

    Re-asigna las constantes COLOR_* del módulo (para que código que
    haga ``from theme import COLOR_X`` después de este punto reciba el
    valor nuevo) y reaplica QPalette + QSS sobre la QApplication.

    Esto se puede llamar muchas veces durante la vida del proceso
    (cuando ThemeManager hace switch a auto/light/dark).

    Devuelve la lista de familias de fuentes cargadas en disco
    (solo es relevante en la primera llamada; subsiguientes no
    re-registran fuentes).
    """

    global _active_theme
    global COLOR_BACKGROUND, COLOR_PANEL, COLOR_PANEL_ELEVATED
    global COLOR_PANEL_BORDER, COLOR_PANEL_DIVIDER
    global COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY, COLOR_TEXT_MUTED
    global COLOR_ACCENT, COLOR_ACCENT_HOVER, COLOR_ACCENT_GLOW
    global COLOR_ACCENT_WARM, COLOR_ALERT, COLOR_ALERT_GLOW, COLOR_OK

    if theme not in _PALETTES:
        logger.warning("Tema desconocido %r — usando 'dark'", theme)
        theme = "dark"

    p = _PALETTES[theme]
    _active_theme = theme

    # Re-asignar constantes a nivel módulo
    COLOR_BACKGROUND     = p["background"]
    COLOR_PANEL          = p["panel"]
    COLOR_PANEL_ELEVATED = p["panel_elevated"]
    COLOR_PANEL_BORDER   = p["panel_border"]
    COLOR_PANEL_DIVIDER  = p["panel_divider"]
    COLOR_TEXT_PRIMARY   = p["text_primary"]
    COLOR_TEXT_SECONDARY = p["text_secondary"]
    COLOR_TEXT_MUTED     = p["text_muted"]
    COLOR_ACCENT         = p["accent"]
    COLOR_ACCENT_HOVER   = p["accent_hover"]
    COLOR_ACCENT_GLOW    = p["accent_glow"]
    COLOR_ACCENT_WARM    = p["accent_warm"]
    COLOR_ALERT          = p["alert"]
    COLOR_ALERT_GLOW     = p["alert_glow"]
    COLOR_OK             = p["ok"]

    # 1. Cargar fuentes (solo la primera vez tiene efecto real)
    families = _load_bundled_fonts()

    # 2. Fuente por defecto
    default_font = QFont()
    default_font.setPointSize(FONT_SIZE_DEFAULT)
    if "Inter" in families or "Inter Variable" in families:
        default_font.setFamily("Inter")
    elif families:
        default_font.setFamily(families[0])
    app.setFont(default_font)

    # 3. QPalette nativa
    palette = QPalette()
    palette.setColor(QPalette.Window,          QColor(p["background"]))
    palette.setColor(QPalette.WindowText,      QColor(p["text_primary"]))
    palette.setColor(QPalette.Base,            QColor(p["background"]))
    palette.setColor(QPalette.AlternateBase,   QColor(p["panel"]))
    palette.setColor(QPalette.ToolTipBase,     QColor(p["panel_elevated"]))
    palette.setColor(QPalette.ToolTipText,     QColor(p["text_primary"]))
    palette.setColor(QPalette.Text,            QColor(p["text_primary"]))
    palette.setColor(QPalette.PlaceholderText, QColor(p["text_muted"]))
    palette.setColor(QPalette.Button,          QColor(p["panel_elevated"]))
    palette.setColor(QPalette.ButtonText,      QColor(p["text_primary"]))
    palette.setColor(QPalette.BrightText,      QColor(p["alert"]))
    palette.setColor(QPalette.Highlight,       QColor(p["accent"]))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.Disabled, QPalette.Text,       QColor(p["text_muted"]))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(p["text_muted"]))
    app.setPalette(palette)

    # 4. QSS global — se cascadea automáticamente a todos los widgets
    #    hijos. Plots de pyqtgraph requerirán reinicio (TODO v0.6).
    app.setStyleSheet(_build_qss(p))

    return families


# ============================================================
# Compatibilidad: alias para el código v0.3 que llamaba apply_dark_theme
# ============================================================
def apply_dark_theme(app: QApplication) -> Iterable[str]:
    """Alias legacy → ``apply_theme(app, 'dark')``.

    Conservado para que ``__main__.py`` y los tests no necesiten
    cambiar en el mismo PR del refactor.
    """

    return apply_theme(app, "dark")
