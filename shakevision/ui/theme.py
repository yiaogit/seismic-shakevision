"""
Tema visual oscuro de la aplicación.

Define una paleta y una hoja de estilo Qt (QSS) modernas, inspiradas
en sistemas de diseño tipo Vercel Geist y Linear: fondos casi negros
con paneles ligeramente más claros, tipografía Inter y acentos en
azul "eléctrico". Todos los widgets de PyQtGraph reutilizan estos
mismos colores para mantener la coherencia.

El tema se aplica a nivel de ``QApplication`` desde ``__main__`` antes
de construir la ventana principal.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication


# ============================================================
# Paleta de colores (Vercel Geist · dark)
# ============================================================
# Fondos y superficies
COLOR_BACKGROUND      = "#0a0a0a"  # Fondo de la ventana (más profundo)
COLOR_PANEL           = "#111111"  # Tarjetas / paneles laterales
COLOR_PANEL_ELEVATED  = "#171717"  # Hover / estado activo
COLOR_PANEL_BORDER    = "#262626"  # Bordes sutiles
COLOR_PANEL_DIVIDER   = "#1a1a1a"  # Líneas separadoras

# Texto
COLOR_TEXT_PRIMARY    = "#fafafa"  # Alto contraste
COLOR_TEXT_SECONDARY  = "#a1a1aa"  # Etiquetas, captions
COLOR_TEXT_MUTED      = "#71717a"  # Texto deshabilitado

# Acentos / estados
COLOR_ACCENT          = "#3b82f6"  # Azul eléctrico (Tailwind blue-500)
COLOR_ACCENT_HOVER    = "#60a5fa"  # Azul más claro para hover
COLOR_ACCENT_GLOW     = "#1d4ed8"  # Azul profundo para sombras
COLOR_ACCENT_WARM     = "#f59e0b"  # Ámbar (alertas suaves)
COLOR_ALERT           = "#ef4444"  # Rojo (evento sísmico)
COLOR_ALERT_GLOW      = "#7f1d1d"  # Rojo profundo
COLOR_OK              = "#10b981"  # Verde esmeralda (conectado)

# Colores de los tres canales de forma de onda (Tailwind 500s)
WAVEFORM_COLORS = {
    "Z": "#3b82f6",  # Vertical -> azul eléctrico
    "N": "#f97316",  # Norte    -> naranja cálido
    "E": "#10b981",  # Este     -> esmeralda
}


# ============================================================
# Tipografía
# ============================================================
# Cadena de fallbacks elegida para que cada SO use su mejor variante
# moderna disponible aunque Inter no esté instalado.
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

# Tamaños base (en pt; Qt los escala automáticamente al DPI)
FONT_SIZE_DEFAULT = 13   # Antes 12 — Inter respira mejor a 13
FONT_SIZE_LABEL   = 11
FONT_SIZE_VALUE   = 14
FONT_SIZE_TITLE   = 12


# ============================================================
# Hoja de estilo global
# ============================================================
def _build_qss() -> str:
    """Construye el QSS final. Función para que sea fácil de testear."""

    return f"""
    QWidget {{
        background-color: {COLOR_BACKGROUND};
        color: {COLOR_TEXT_PRIMARY};
        font-family: {FONT_STACK_SANS};
        font-size: {FONT_SIZE_DEFAULT}px;
    }}

    QFrame#ControlPanel {{
        background-color: {COLOR_PANEL};
        border: 1px solid {COLOR_PANEL_BORDER};
        border-radius: 10px;
    }}

    QFrame#WaveformPanel {{
        background-color: {COLOR_PANEL};
        border: 1px solid {COLOR_PANEL_BORDER};
        border-radius: 10px;
    }}

    QFrame#WaveformPanel[alert="true"] {{
        border: 2px solid {COLOR_ALERT};
        background-color: {COLOR_PANEL_ELEVATED};
    }}

    QLabel#SectionTitle {{
        color: {COLOR_TEXT_SECONDARY};
        font-weight: 600;
        font-size: {FONT_SIZE_LABEL}px;
        letter-spacing: 0.8px;
        text-transform: uppercase;
        padding: 6px 0px 4px 0px;
    }}

    QLabel#StatusValue {{
        color: {COLOR_TEXT_PRIMARY};
        font-family: {FONT_STACK_MONO};
        font-size: {FONT_SIZE_VALUE}px;
        font-weight: 500;
    }}

    QLabel#StatusOk    {{ color: {COLOR_OK};         font-weight: 600; }}
    QLabel#StatusWarn  {{ color: {COLOR_ACCENT_WARM}; font-weight: 600; }}
    QLabel#StatusAlert {{ color: {COLOR_ALERT};      font-weight: 600; }}

    /* ---------- Inputs ---------- */
    QComboBox, QDoubleSpinBox, QSpinBox, QLineEdit {{
        background-color: {COLOR_BACKGROUND};
        color: {COLOR_TEXT_PRIMARY};
        border: 1px solid {COLOR_PANEL_BORDER};
        border-radius: 6px;
        padding: 6px 8px;
        selection-background-color: {COLOR_ACCENT};
    }}

    QComboBox:hover, QDoubleSpinBox:hover, QSpinBox:hover, QLineEdit:hover {{
        border-color: {COLOR_ACCENT};
    }}

    QComboBox:disabled, QDoubleSpinBox:disabled, QSpinBox:disabled {{
        color: {COLOR_TEXT_MUTED};
        background-color: {COLOR_PANEL};
    }}

    QComboBox::drop-down {{
        border: 0;
        width: 18px;
    }}

    QComboBox QAbstractItemView {{
        background-color: {COLOR_PANEL_ELEVATED};
        border: 1px solid {COLOR_PANEL_BORDER};
        border-radius: 6px;
        padding: 4px;
        selection-background-color: {COLOR_ACCENT};
        selection-color: {COLOR_TEXT_PRIMARY};
    }}

    /* ---------- Botones ---------- */
    QPushButton {{
        background-color: {COLOR_PANEL_ELEVATED};
        color: {COLOR_TEXT_PRIMARY};
        border: 1px solid {COLOR_PANEL_BORDER};
        border-radius: 8px;
        padding: 8px 16px;
        font-weight: 500;
    }}

    QPushButton:hover {{
        border-color: {COLOR_ACCENT};
        background-color: {COLOR_PANEL_ELEVATED};
    }}

    QPushButton:pressed {{
        background-color: {COLOR_ACCENT};
        color: white;
        border-color: {COLOR_ACCENT};
    }}

    QPushButton:disabled {{
        color: {COLOR_TEXT_MUTED};
        background-color: {COLOR_PANEL};
    }}

    /* ---------- Sliders ---------- */
    QSlider::groove:horizontal {{
        height: 4px;
        background: {COLOR_PANEL_BORDER};
        border-radius: 2px;
    }}

    QSlider::sub-page:horizontal {{
        background: {COLOR_ACCENT};
        border-radius: 2px;
    }}

    QSlider::handle:horizontal {{
        background: {COLOR_TEXT_PRIMARY};
        width: 16px;
        height: 16px;
        margin: -7px 0;
        border-radius: 8px;
        border: 2px solid {COLOR_ACCENT};
    }}

    QSlider::handle:horizontal:hover {{
        border-color: {COLOR_ACCENT_HOVER};
    }}

    /* ---------- Checkbox ---------- */
    QCheckBox {{
        spacing: 8px;
        color: {COLOR_TEXT_PRIMARY};
    }}

    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border: 1px solid {COLOR_PANEL_BORDER};
        border-radius: 4px;
        background-color: {COLOR_BACKGROUND};
    }}

    QCheckBox::indicator:hover {{
        border-color: {COLOR_ACCENT};
    }}

    QCheckBox::indicator:checked {{
        background-color: {COLOR_ACCENT};
        border-color: {COLOR_ACCENT};
    }}

    /* ---------- Pestañas ---------- */
    QTabWidget::pane {{
        border: 1px solid {COLOR_PANEL_BORDER};
        border-radius: 10px;
        top: -1px;
        background-color: {COLOR_PANEL};
    }}

    QTabBar::tab {{
        background-color: transparent;
        color: {COLOR_TEXT_SECONDARY};
        padding: 8px 16px;
        border: none;
        margin-right: 4px;
        font-weight: 500;
    }}

    QTabBar::tab:hover {{
        color: {COLOR_TEXT_PRIMARY};
    }}

    QTabBar::tab:selected {{
        color: {COLOR_TEXT_PRIMARY};
        border-bottom: 2px solid {COLOR_ACCENT};
    }}

    /* ---------- Barra de estado ---------- */
    QStatusBar {{
        background: {COLOR_PANEL};
        border-top: 1px solid {COLOR_PANEL_BORDER};
        padding: 4px 8px;
    }}

    QStatusBar QLabel {{
        padding: 0 8px;
    }}

    /* ---------- Splitter ---------- */
    QSplitter::handle {{
        background-color: {COLOR_PANEL_DIVIDER};
    }}

    QSplitter::handle:horizontal {{
        width: 4px;
    }}

    QSplitter::handle:vertical {{
        height: 4px;
    }}

    QSplitter::handle:hover {{
        background-color: {COLOR_ACCENT};
    }}

    /* ---------- Menú ---------- */
    QMenuBar {{
        background-color: {COLOR_BACKGROUND};
        border-bottom: 1px solid {COLOR_PANEL_BORDER};
        padding: 2px;
    }}

    QMenuBar::item {{
        padding: 6px 12px;
        background: transparent;
        border-radius: 4px;
    }}

    QMenuBar::item:selected {{
        background-color: {COLOR_PANEL_ELEVATED};
    }}

    QMenu {{
        background-color: {COLOR_PANEL_ELEVATED};
        border: 1px solid {COLOR_PANEL_BORDER};
        border-radius: 8px;
        padding: 4px;
    }}

    QMenu::item {{
        padding: 6px 24px 6px 12px;
        border-radius: 4px;
    }}

    QMenu::item:selected {{
        background-color: {COLOR_ACCENT};
        color: white;
    }}
    """


# ============================================================
# Carga dinámica de fuentes empaquetadas
# ============================================================
# Directorio donde el usuario puede dejar archivos .ttf/.otf adicionales
# (Inter, JetBrains Mono, etc.). El paquete los registra en arranque.
ASSETS_FONTS_DIR: Path = Path(__file__).resolve().parent.parent / "assets" / "fonts"


def _load_bundled_fonts() -> list[str]:
    """Registra todas las fuentes ``.ttf``/``.otf`` empaquetadas.

    Devuelve la lista de familias cargadas (útil para depuración). Si
    el directorio no existe o está vacío, devuelve una lista vacía y
    el QSS recurre al primer fallback disponible del sistema.
    """

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
def apply_dark_theme(app: QApplication) -> Iterable[str]:
    """Aplica la paleta y la hoja de estilo oscuras a la aplicación.

    Devuelve la lista de familias de fuentes que se cargaron desde el
    directorio ``assets/fonts/`` (puede estar vacía, no es un error).
    """

    # 1. Cargar fuentes empaquetadas (Inter, JetBrains Mono…) si existen
    families = _load_bundled_fonts()

    # 2. Fuente por defecto de la aplicación. Si Inter está disponible,
    #    Qt la usará automáticamente en cualquier widget que no fije
    #    explícitamente otra family.
    default_font = QFont()
    default_font.setPointSize(FONT_SIZE_DEFAULT)
    if "Inter" in families or "Inter Variable" in families:
        default_font.setFamily("Inter")
    elif families:
        default_font.setFamily(families[0])
    app.setFont(default_font)

    # 3. Paleta base (algunos widgets nativos ignoran QSS y usan QPalette)
    palette = QPalette()
    palette.setColor(QPalette.Window,          QColor(COLOR_BACKGROUND))
    palette.setColor(QPalette.WindowText,      QColor(COLOR_TEXT_PRIMARY))
    palette.setColor(QPalette.Base,            QColor(COLOR_BACKGROUND))
    palette.setColor(QPalette.AlternateBase,   QColor(COLOR_PANEL))
    palette.setColor(QPalette.ToolTipBase,     QColor(COLOR_PANEL_ELEVATED))
    palette.setColor(QPalette.ToolTipText,     QColor(COLOR_TEXT_PRIMARY))
    palette.setColor(QPalette.Text,            QColor(COLOR_TEXT_PRIMARY))
    palette.setColor(QPalette.PlaceholderText, QColor(COLOR_TEXT_MUTED))
    palette.setColor(QPalette.Button,          QColor(COLOR_PANEL_ELEVATED))
    palette.setColor(QPalette.ButtonText,      QColor(COLOR_TEXT_PRIMARY))
    palette.setColor(QPalette.BrightText,      QColor(COLOR_ALERT))
    palette.setColor(QPalette.Highlight,       QColor(COLOR_ACCENT))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.Disabled, QPalette.Text,       QColor(COLOR_TEXT_MUTED))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(COLOR_TEXT_MUTED))
    app.setPalette(palette)

    # 4. Hoja de estilo global
    app.setStyleSheet(_build_qss())

    return families
