"""
Mejoras nativas exclusivas de macOS.

En macOS los usuarios esperan:

  - Botones de tráfico (rojo / amarillo / verde) en su sitio habitual
    de la esquina superior izquierda.
  - Una barra de título translúcida que se funde con el contenido (es
    el aspecto "vibrante" de Big Sur en adelante).
  - Idealmente un fondo con efecto de cristal (NSVisualEffectView).

Este módulo aplica esas mejoras **solo si estamos en macOS**, **sin
romper nada** en otros sistemas. Si ``pyobjc`` no está instalado,
caemos en una mejora menos vistosa pero aún válida usando solo Qt
(``setUnifiedTitleAndToolBarOnMac``).

Política de dependencias
------------------------
``pyobjc-framework-Cocoa`` se declara como **extra opcional** en
``pyproject.toml`` bajo el grupo ``macos``. El usuario puede
instalarlo con:

    pip install ".[macos]"

Si no lo instala, la aplicación sigue funcionando — solo deja de
beneficiarse del título transparente.
"""

from __future__ import annotations

import logging
import sys
from typing import Optional

from PySide6.QtWidgets import QMainWindow

logger = logging.getLogger(__name__)


def is_macos() -> bool:
    """Devuelve ``True`` si el SO actual es macOS."""

    return sys.platform == "darwin"


def enhance_macos_window(window: QMainWindow) -> str:
    """Aplica las mejoras nativas de macOS a la ventana indicada.

    Returns
    -------
    str
        Una cadena describiendo qué nivel de mejora se aplicó:
        ``"native_full"``  → pyobjc disponible, título transparente activo.
        ``"qt_unified"``   → fallback solo con Qt (toolbar unificada).
        ``"skipped"``      → no es macOS, no se hace nada.
        ``"failed"``       → algo falló durante la aplicación.
    """

    if not is_macos():
        return "skipped"

    # Intento 1: pyobjc + AppKit (lo mejor)
    try:
        return _apply_native_titlebar(window)
    except ImportError:
        logger.info(
            "pyobjc no instalado; usando fallback Qt para macOS. "
            "Para activar la barra de título translúcida ejecuta "
            "'pip install \".[macos]\"'."
        )
    except Exception as exc:  # pragma: no cover - red de seguridad
        logger.warning("Mejora macOS pyobjc falló: %s", exc)

    # Intento 2: solo Qt (más limitado pero sin dependencias)
    try:
        window.setUnifiedTitleAndToolBarOnMac(True)
        return "qt_unified"
    except Exception as exc:  # pragma: no cover
        logger.warning("Mejora macOS Qt falló: %s", exc)
        return "failed"


def _apply_native_titlebar(window: QMainWindow) -> str:
    """Aplica la barra de título transparente vía AppKit.

    Levanta ``ImportError`` si pyobjc no está disponible.
    """

    # Importación tardía: solo en macOS y solo si pyobjc existe.
    import objc  # type: ignore[import-not-found]
    from AppKit import (  # type: ignore[import-not-found]
        NSColor,
        NSWindow,
        NSWindowStyleMaskFullSizeContentView,
    )

    # Convertir el winId() de Qt (puntero a NSView) en un objeto Cocoa
    native_view_ptr = window.winId()
    if not native_view_ptr:
        raise RuntimeError("La ventana aún no tiene NSView nativo")

    ns_view = objc.objc_object(c_void_p=int(native_view_ptr))
    ns_window: NSWindow = ns_view.window()
    if ns_window is None:
        raise RuntimeError("La ventana NSView no tiene NSWindow asociada")

    # 1. Permitir que el contenido se extienda detrás de la barra de
    #    título. Los semáforos se mantienen flotando encima.
    style_mask = ns_window.styleMask()
    ns_window.setStyleMask_(style_mask | NSWindowStyleMaskFullSizeContentView)

    # 2. Hacer la barra de título transparente.
    ns_window.setTitlebarAppearsTransparent_(True)

    # 3. Color de fondo de la ventana coherente con nuestro tema oscuro
    #    (#0a0a0a) — evita un parpadeo blanco al arrancar.
    bg = NSColor.colorWithCalibratedRed_green_blue_alpha_(
        0x0A / 255.0, 0x0A / 255.0, 0x0A / 255.0, 1.0
    )
    ns_window.setBackgroundColor_(bg)

    logger.info("Barra de título nativa transparente activada.")
    return "native_full"


def title_bar_inset_pixels() -> int:
    """Píxeles que ocupa la barra de título nativa de macOS.

    Útil para que el contenido superior de la ventana añada un margen
    cuando el título es transparente y se solapa con el contenido.
    """

    if not is_macos():
        return 0
    # macOS usa una barra de 28 px (estándar) o 22 px (compacta). Damos
    # un margen seguro de 28 para evitar que los semáforos pisen el
    # contenido.
    return 28


def title_bar_inset_for(window: QMainWindow) -> int:
    """Variante que devuelve 0 si no se ha aplicado la mejora nativa.

    Permite a la UI consultar dinámicamente: "¿necesito reservar
    espacio extra arriba?".
    """

    return title_bar_inset_pixels() if is_macos() else 0


def macos_dependency_hint() -> Optional[str]:
    """Sugerencia para mostrar al usuario si está en macOS sin pyobjc."""

    if not is_macos():
        return None
    try:
        import objc  # noqa: F401
        return None
    except ImportError:
        return (
            "Para una experiencia visual completa en macOS, instala el "
            "extra opcional con: pip install \".[macos]\""
        )
