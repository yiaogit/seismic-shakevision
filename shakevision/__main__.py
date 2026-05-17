"""
Punto de entrada ejecutable del paquete.

Permite arrancar la aplicación con:
    python -m shakevision
o, si se ha instalado con ``pip install -e .``, simplemente:
    shakevision

Orden de arranque
-----------------
1. Crear QApplication + cargar tema y fuentes.
2. Mostrar SplashScreen con el logo animado.
3. Construir MainWindow (puede tardar 1-2 s la primera vez por la
   carga de QtWebEngine).
4. Mostrar la ventana y cerrar el splash.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from shakevision import APP_NAME, __version__
from shakevision.config import DEFAULT_APP_CONFIG
from shakevision.ui.main_window import MainWindow
from shakevision.ui.splash import SplashScreen
from shakevision.ui.theme import apply_dark_theme
from shakevision.utils.logging import setup_logging


def main() -> int:
    """Inicializa la aplicación Qt y muestra la ventana principal."""

    # Configurar el sistema de logs antes de crear cualquier objeto Qt
    logger = setup_logging()
    logger.info("Iniciando %s v%s", APP_NAME, __version__)

    # Crear la aplicación Qt
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)

    # Aplicar el tema oscuro a nivel global. Devuelve las familias de
    # fuentes empaquetadas que se han registrado (puede estar vacía).
    loaded_fonts = list(apply_dark_theme(app))
    if loaded_fonts:
        logger.info("Fuentes empaquetadas cargadas: %s", ", ".join(loaded_fonts))
    else:
        logger.info(
            "Sin fuentes empaquetadas; usando fallback del sistema. "
            "Para una mejor estética instala Inter en assets/fonts/."
        )

    # Mostrar el splash cuanto antes (incluso antes de construir la
    # ventana principal, que puede tardar ~1 s por QtWebEngine).
    splash = SplashScreen(version=__version__)
    splash.set_status("Inicializando")
    splash.show()
    app.processEvents()

    # Permitir que el splash se pinte al menos un frame antes de
    # arrancar la construcción pesada de la ventana.
    splash.set_status("Construyendo interfaz")
    app.processEvents()

    window = MainWindow(config=DEFAULT_APP_CONFIG)

    # Pequeño retardo intencional para que el usuario vea el logo
    # animado al menos ~600 ms aunque la inicialización sea rápida.
    QTimer.singleShot(600, lambda: _reveal_main_window(window, splash))

    return app.exec()


def _reveal_main_window(window: MainWindow, splash: SplashScreen) -> None:
    """Muestra la ventana principal y cierra el splash."""

    window.show()
    splash.finish_and_close()


if __name__ == "__main__":
    sys.exit(main())
