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

import faulthandler
import logging
import sys
import traceback

# v0.5.2: capturar segfaults C++ (común con Qt + WebEngine) en stderr
# para que el usuario vea POR QUÉ se cuelga, en vez de "splash → nada".
faulthandler.enable()

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication


# Logger module-level (se usa en _after_splash / _show_window_*).
# setup_logging() en main() lo configura con handler stderr + fichero.
_log = logging.getLogger("shakevision.__main__")


def _excepthook(exc_type, exc_value, exc_tb):
    """Captura excepciones no manejadas en cualquier hilo Python.

    Sin esto, una excepción dentro de un slot Qt o de un QTimer.lambda
    se va silenciosamente al void y la UI se queda colgada. Volcamos al
    log para que SIEMPRE veamos el stacktrace.
    """
    _log.error(
        "Excepción no capturada:\n%s",
        "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
    )


sys.excepthook = _excepthook

from shakevision import APP_NAME, __version__
from shakevision.config import DEFAULT_APP_CONFIG
from shakevision.services.usage_tracker import UsageTracker
from shakevision.ui.localizame_view import (
    LocalizameScreen,
    has_been_completed as localizame_completed,
    mark_completed as mark_localizame_completed,
)
from shakevision.ui.main_window import MainWindow
from shakevision.ui.onboarding_wizard import (
    OnboardingWizard,
    has_been_completed as onboarding_completed,
)
from shakevision.ui.splash import SplashScreen
from shakevision.ui.theme_manager import ThemeManager
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

    # Inicializar el manager de temas (v0.4+). Decide entre claro /
    # oscuro / auto según las preferencias guardadas y aplica QSS +
    # QPalette + fuentes empaquetadas en una sola llamada. Tras este
    # punto, cualquier cambio de tema en caliente (botón de la barra,
    # tick automático a la franja diurna) se propaga sin que
    # __main__ tenga que enterarse.
    ThemeManager.init(app)
    logger.info("Tema activo: %s (modo %s)",
                ThemeManager.current_theme(), ThemeManager.mode())

    # Métricas locales (privadas, sin red — v0.5 阶段 I): contamos un
    # arranque y arrancamos el timer de sesión. ``end_session`` se
    # invoca cuando la QApplication emite aboutToQuit, para que el
    # tiempo acumulado se persista incluso si el usuario cierra con
    # ⌘Q en vez del menú.
    UsageTracker.record_launch()
    UsageTracker.start_session()
    app.aboutToQuit.connect(UsageTracker.end_session)

    # Mostrar el splash cuanto antes (incluso antes de construir la
    # ventana principal, que puede tardar ~1 s por QtWebEngine).
    # El splash (v0.5) tiene una barra de progreso determinista que
    # vamos empujando con set_progress() en cada hito del arranque.
    # Los porcentajes son aproximados — lo importante es que el
    # usuario vea avance, no un porcentaje exacto.
    splash = SplashScreen(version=__version__)
    splash.set_status("Inicializando")
    splash.set_progress(0.10)
    splash.show()
    app.processEvents()

    # Permitir que el splash se pinte al menos un frame antes de
    # arrancar la construcción pesada de la ventana.
    splash.set_status("Construyendo interfaz")
    splash.set_progress(0.40)
    app.processEvents()

    _log.info("Construyendo MainWindow…")
    try:
        window = MainWindow(config=DEFAULT_APP_CONFIG)
    except Exception as exc:
        _log.exception("MainWindow() FALLÓ catastróficamente: %s", exc)
        # Sin ventana no hay forma de continuar; salir limpio.
        splash.finish_and_close()
        return 1
    _log.info("MainWindow construido (visible=%s)", window.isVisible())
    splash.set_status("Cargando recursos")
    splash.set_progress(0.85)
    app.processEvents()

    # Pequeño retardo intencional para que el usuario vea el logo
    # animado al menos ~600 ms aunque la inicialización sea rápida.
    # Al cerrar el splash empujamos a 100 % para que la barra termine
    # llena visualmente antes de la fundida.
    #
    # Tras el splash bifurcamos:
    #   * Si es el primer arranque (Localízame no completado): mostramos
    #     la pantalla Localízame, que tarda ~2.5 s con sus halos de
    #     sonar y luego revela MainWindow.
    #   * Si no: revelamos MainWindow directamente.
    QTimer.singleShot(600, lambda: _after_splash(window, splash))

    return app.exec()


def _after_splash(window: MainWindow, splash: SplashScreen) -> None:
    """Cierra splash y decide si meter Localízame antes de la app.

    v0.5.2: cada paso loggeado + try/except defensivo. Si CUALQUIER cosa
    falla en este flujo, hacemos fallback duro a window.show() — la
    prioridad es que el usuario VEA la app aunque pierda el onboarding.
    """

    _log.info("_after_splash: arrancando (splash → window flow)")
    try:
        splash.set_progress(1.0)
        splash.set_status("Listo")
        splash.finish_and_close()
        _log.info("_after_splash: splash cerrado")
    except Exception as exc:  # noqa: BLE001
        _log.exception("_after_splash: error cerrando splash (%s)", exc)

    try:
        loc_done = localizame_completed()
        _log.info("_after_splash: localizame_completed=%s", loc_done)
    except Exception as exc:  # noqa: BLE001
        _log.exception("_after_splash: error leyendo localizame flag (%s)", exc)
        loc_done = True   # fallback: tratar como hecho para no quedar atascado

    if loc_done:
        _log.info("_after_splash: Localízame ya hecho — al window")
        _show_window_with_optional_onboarding(window)
        return

    _log.info("_after_splash: PRIMERA vez — mostrando Localízame")
    try:
        localizame = LocalizameScreen()
        localizame.detect_and_show()

        def _on_localizame_finished():
            _log.info("Localízame: finished disparado")
            try:
                mark_localizame_completed()
            except Exception as exc:  # noqa: BLE001
                _log.exception("mark_localizame_completed falló: %s", exc)
            _show_window_with_optional_onboarding(window)

        localizame.finished.connect(_on_localizame_finished)
        localizame.show()
        # Mantener referencia para que el GC no se lo lleve mientras
        # el _dismiss_timer aún corre.
        window._localizame_ref = localizame   # type: ignore[attr-defined]
        _log.info("_after_splash: Localízame mostrado, esperando timer 2.5s")
    except Exception as exc:  # noqa: BLE001
        _log.exception("_after_splash: Localízame FALLÓ (%s) — fallback "
                       "directo al window.show()", exc)
        _show_window_with_optional_onboarding(window)


def _show_window_with_optional_onboarding(window: MainWindow) -> None:
    """Muestra la ventana principal y, si toca, el wizard de onboarding.

    v0.5.2 (defensivo):
      * window.show() es lo PRIMERO — y va envuelto en try/except.
        Si window.show() falla por alguna razón inesperada, sigue
        siendo mejor loggear la excepción que dejar la UI congelada.
      * Tras window.show(), si onboarding no se ha completado,
        intentamos crear el wizard. Si la creación o show del wizard
        falla, la ventana principal sigue visible — peor caso es que
        el usuario pierde el onboarding, pero NO se queda mirando
        a un splash que nunca abrió la app.
    """

    _log.info("_show_window_with_optional_onboarding: entrando")
    try:
        window.show()
        window.raise_()
        window.activateWindow()
        _log.info("window.show() OK — visible=%s, geom=%dx%d",
                  window.isVisible(), window.width(), window.height())
    except Exception as exc:  # noqa: BLE001
        _log.exception("window.show() FALLÓ: %s", exc)
        return

    try:
        ob_done = onboarding_completed()
        _log.info("onboarding_completed=%s", ob_done)
    except Exception as exc:  # noqa: BLE001
        _log.exception("onboarding_completed lectura falló: %s", exc)
        ob_done = True   # fallback: saltar wizard

    if ob_done:
        return

    _log.info("Lanzando OnboardingWizard")
    try:
        wizard = OnboardingWizard(parent=window)
        wizard.show()
        wizard.raise_()
        wizard.activateWindow()
        # Mantener referencia explícita: si el lambda parent=window
        # garbage-collecta el wizard antes de exec, se cierra solo.
        window._onboarding_ref = wizard   # type: ignore[attr-defined]
        _log.info("OnboardingWizard mostrado correctamente")
    except Exception as exc:  # noqa: BLE001
        _log.exception("OnboardingWizard FALLÓ (%s) — siguiendo sin él", exc)


def _reveal_main_window(window: MainWindow, splash: SplashScreen) -> None:
    """Compatibilidad — algunos tests pueden importar esto.

    El flujo real ahora vive en _after_splash; mantenemos esta función
    como wrapper trivial que solo revela la ventana, sin lógica.
    """

    splash.set_progress(1.0)
    splash.set_status("Listo")
    window.show()
    splash.finish_and_close()


if __name__ == "__main__":
    sys.exit(main())
