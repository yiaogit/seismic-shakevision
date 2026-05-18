"""
Acceso centralizado a los iconos y al logo de SeismicGuard.

Por qué un módulo dedicado
--------------------------
Los iconos vienen como PNG en negro sólido (línea fina, ~512×512). Si
los usamos tal cual quedan invisibles en un tema oscuro y feos en uno
claro. Este módulo:

  * Localiza los PNG dentro del paquete (``shakevision/assets/icons/``).
  * Aplica un **re-coloreo** rápido vía QPainter+CompositionMode_SourceIn:
    en lugar de buscar y reemplazar píxeles uno a uno (lento), usa la
    capa alpha del PNG original como máscara para pintar el color
    nuevo. Sub-milisegundo por icono incluso a 512×512.
  * Cachea los QIcon resultantes para no repintar en cada paint event.
  * Selecciona automáticamente la variante "para tema claro" /
    "para tema oscuro" cuando el caller pasa ``theme="auto"`` (lo
    que en la práctica significa el tema actual del usuario).

Logo
----
``logo_pixmap(theme)`` devuelve el PNG completo del rebrand:
  * ``theme="dark"``  → texto blanco (para pintar sobre fondos oscuros)
  * ``theme="light"`` → texto azul marino (para fondos claros)
Sin recolor; los PNG vienen ya pintados con la paleta correcta.

Convención de nombres
---------------------
Los iconos están en ``assets/icons/<name>.png``. Para añadir uno
nuevo basta con dejar el PNG en esa carpeta (alpha en negro) y
llamarlo con ese mismo ``<name>``. No hace falta tocar este módulo.

Ejemplo de uso
--------------
    from shakevision.ui.icons import get_icon, logo_pixmap

    btn = QPushButton()
    btn.setIcon(get_icon("globe", color="#fafafa"))
    # o, vinculado al tema actual:
    btn.setIcon(get_icon("globe", theme="dark"))

    splash_label = QLabel()
    splash_label.setPixmap(logo_pixmap(theme="dark", width=420))
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Final, Literal, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap


logger = logging.getLogger(__name__)


# ============================================================
# Rutas
# ============================================================
_ASSETS_DIR: Final[Path] = Path(__file__).resolve().parent.parent / "assets"
_ICONS_DIR: Final[Path] = _ASSETS_DIR / "icons"
_BRANDING_DIR: Final[Path] = _ASSETS_DIR / "branding"


# Paleta por defecto para los dos temas. Los callers pueden
# sobrescribir el color a mano (``color="#ffaa00"``).
DEFAULT_ICON_COLOR_DARK_THEME: Final[str] = "#fafafa"      # casi blanco
DEFAULT_ICON_COLOR_LIGHT_THEME: Final[str] = "#1a2b4a"     # azul marino

# Tamaño "nativo" del QIcon (el caller suele escalar al pintar).
_DEFAULT_RENDER_SIZE: Final[int] = 64


Theme = Literal["dark", "light"]


# ============================================================
# Caché en memoria
# ============================================================
# Clave: (icon_name, hex_color, render_size).  Valor: QIcon.
_icon_cache: Dict[tuple, QIcon] = {}


# ============================================================
# API pública — iconos UI
# ============================================================
def get_icon(
    name: str,
    *,
    color: Optional[str] = None,
    theme: Optional[Theme] = None,
    size: int = _DEFAULT_RENDER_SIZE,
) -> QIcon:
    """Devuelve un QIcon recoloreado.

    Parámetros
    ----------
    name
        Nombre del icono (sin extensión) — debe existir
        ``assets/icons/<name>.png``.
    color
        Color hex explícito (``"#fafafa"``). Tiene prioridad sobre
        ``theme``. Si ambos son None se usa blanco.
    theme
        ``"dark"`` o ``"light"``. Si se da y ``color`` es None, se
        elige el color por defecto del tema.
    size
        Lado del QPixmap (px). 64 px suele bastar para botones de
        toolbar — Qt escala automáticamente al pintar.
    """

    # Resolver el color final
    if color is None:
        if theme == "dark":
            color = DEFAULT_ICON_COLOR_DARK_THEME
        elif theme == "light":
            color = DEFAULT_ICON_COLOR_LIGHT_THEME
        else:
            color = DEFAULT_ICON_COLOR_DARK_THEME

    cache_key = (name, color.lower(), int(size))
    cached = _icon_cache.get(cache_key)
    if cached is not None:
        return cached

    source_path = _ICONS_DIR / f"{name}.png"
    if not source_path.is_file():
        logger.warning("Icono no encontrado: %s (devolviendo QIcon vacío)",
                       source_path)
        empty = QIcon()
        _icon_cache[cache_key] = empty
        return empty

    pixmap = _recolor_png(source_path, QColor(color), size)
    icon = QIcon(pixmap)
    _icon_cache[cache_key] = icon
    return icon


def get_icon_path(name: str) -> Optional[Path]:
    """Devuelve la ruta absoluta del PNG fuente, o None si no existe.

    Útil cuando se necesita un Path para QSS (``url(...)``) o para
    embeber en HTML local del WebView. No aplica recolor.
    """

    p = _ICONS_DIR / f"{name}.png"
    return p if p.is_file() else None


def available_icon_names() -> list[str]:
    """Lista de nombres válidos (debug / tests)."""

    if not _ICONS_DIR.is_dir():
        return []
    return sorted(p.stem for p in _ICONS_DIR.glob("*.png"))


# ============================================================
# API pública — logo
# ============================================================
def logo_pixmap(
    theme: Theme = "dark",
    *,
    width: Optional[int] = None,
    height: Optional[int] = None,
) -> QPixmap:
    """Devuelve el QPixmap del logo de SeismicGuard para el tema dado.

    Pasa ``width`` o ``height`` para escalar manteniendo proporción;
    si ambos son None, devuelve el PNG en su tamaño nativo
    (≈ 1000 × 250 px).
    """

    fname = "logo_for_dark.png" if theme == "dark" else "logo_for_light.png"
    path = _BRANDING_DIR / fname
    if not path.is_file():
        logger.warning("Logo no encontrado: %s", path)
        return QPixmap()

    pm = QPixmap(str(path))
    if pm.isNull():
        return pm
    if width is not None and height is None:
        pm = pm.scaledToWidth(width, Qt.SmoothTransformation)
    elif height is not None and width is None:
        pm = pm.scaledToHeight(height, Qt.SmoothTransformation)
    elif width is not None and height is not None:
        pm = pm.scaled(width, height,
                       Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return pm


def logo_path(theme: Theme = "dark") -> Optional[Path]:
    """Ruta absoluta del logo (para QSS ``url(...)`` o HTML)."""

    fname = "logo_for_dark.png" if theme == "dark" else "logo_for_light.png"
    p = _BRANDING_DIR / fname
    return p if p.is_file() else None


# ============================================================
# Limpieza de caché (la usan los tests; en producción rara vez hace falta)
# ============================================================
def clear_icon_cache() -> None:
    """Vacía la caché de QIcon. Útil al cambiar de tema en caliente."""

    _icon_cache.clear()


# ============================================================
# Internos
# ============================================================
def _recolor_png(source_path: Path, color: QColor, size: int) -> QPixmap:
    """Aplica ``color`` al PNG usando su alpha como máscara.

    Pipeline:
      1. Cargar el PNG (negro sobre transparente).
      2. Escalar a ``size × size`` (los PNG vienen en 512×512 — Qt
         lo hace con bicubic así que no perdemos nitidez).
      3. Crear un QPixmap del color sólido del mismo tamaño.
      4. Pintar el color usando ``CompositionMode_SourceIn`` con la
         alpha del PNG como máscara → resultado: el dibujo original
         pero pintado del color elegido, manteniendo bordes anti-alias.
    """

    src = QPixmap(str(source_path))
    if src.isNull():
        return src
    src = src.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    result = QPixmap(src.size())
    result.fill(Qt.transparent)

    painter = QPainter(result)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    # Paso 1: pintar el icono original (negro + alpha)
    painter.drawPixmap(0, 0, src)
    # Paso 2: usar SourceIn para reemplazar el negro por el color
    # nuevo manteniendo la alpha intacta.
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(result.rect(), color)
    painter.end()
    return result
