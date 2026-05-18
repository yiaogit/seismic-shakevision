"""
Pantalla "Localízame" — transición tras el splash en el primer arranque.

Propósito
---------
La primera vez que el usuario abre SeismicGuard mostramos una pantalla
de bienvenida corta (~2.5 s) que:

  1. Detecta la zona horaria del sistema (sin red — la lógica vive en
     ``TimezoneService.detect_system_timezone``) y la enseña al usuario
     como "te hemos ubicado en {zone}".
  2. Anima 5 anillos concéntricos expandiéndose desde el centro como
     pulsos de sonar — el "halo de localización" que pide el rebrand.
  3. Al terminar emite ``finished`` para que ``__main__`` muestre la
     ventana principal y persista una bandera en QSettings para que
     **no vuelva a aparecer** en arranques posteriores.

Diseño visual
-------------
* Frameless + WindowStaysOnTopHint (igual que SplashScreen).
* Fondo gradient navy → deep black, bordes redondeados.
* Logo SeismicGuard arriba (variante para fondo oscuro).
* Halos centrados: 5 anillos cyan, periodo 3 s, opacidad cae con r².
* Texto de estado en dos líneas: encabezado + valor detectado.

Privacidad
----------
NO hacemos llamadas de red. Solo usamos ``detect_system_timezone()``,
que lee ``/etc/localtime``, ``$TZ`` o el registro de Windows. El usuario
podrá refinar su ubicación en Ajustes; este paso es informativo, no
verificatorio.

Persistencia
------------
``QSettings("SeismicGuard"/"Onboarding")`` clave
``localizame/completed`` = ``True`` tras la primera ejecución. La
fachada ``LocalizameScreen.has_been_completed()`` la consulta para
que el caller decida si saltarse la pantalla.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPaintEvent,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import QApplication, QFrame, QWidget

from shakevision.ui.icons import logo_pixmap


logger = logging.getLogger(__name__)


# ============================================================
# Persistencia (QSettings)
# ============================================================
_QSETTINGS_ORG: str = "SeismicGuard"
_QSETTINGS_APP: str = "Onboarding"
_QSETTINGS_KEY_DONE: str = "localizame/completed"


def has_been_completed() -> bool:
    """¿Ya pasó el usuario por Localízame alguna vez?"""

    try:
        from PySide6.QtCore import QSettings
        settings = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
        val = settings.value(_QSETTINGS_KEY_DONE, False, type=bool)
        return bool(val)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Localízame: leer QSettings falló (%s)", exc)
        return False


def mark_completed() -> None:
    """Persiste la bandera "ya hecho" para que no se repita."""

    try:
        from PySide6.QtCore import QSettings
        settings = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
        settings.setValue(_QSETTINGS_KEY_DONE, True)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Localízame: persistir falló (%s)", exc)


def _reset_for_tests() -> None:
    """Borra la bandera de completado — solo tests."""

    try:
        from PySide6.QtCore import QSettings
        settings = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
        settings.remove(_QSETTINGS_KEY_DONE)
    except Exception:  # noqa: BLE001
        pass


# ============================================================
# Constantes visuales
# ============================================================
SCREEN_WIDTH: int = 560
SCREEN_HEIGHT: int = 400

LOGO_WIDTH_PX: int = 260

# Halo: cuántos anillos simultáneos, radio máximo y periodo.
HALO_RING_COUNT: int = 5
HALO_MAX_RADIUS_PX: float = 180.0
HALO_PERIOD_S: float = 3.0
HALO_START_RADIUS_PX: float = 6.0

# Duración total antes de emitir ``finished``. v0.5.2: subido a 4s
# (antes 2.5s) — el usuario reportaba "una pasada y desaparece";
# ahora se ven al menos 1.3 ciclos completos de halos.
AUTO_DISMISS_MS: int = 4000

REFRESH_FPS: int = 30

# Colores (mismas tonalidades que splash)
COLOR_BG_TOP    = "#0a1226"
COLOR_BG_BOTTOM = "#02030a"
COLOR_BORDER    = "#1a2b4a"
COLOR_PRIMARY   = "#fafafa"
COLOR_SECONDARY = "#a1a1aa"
COLOR_MUTED     = "#71717a"
COLOR_HALO      = "#22d3ee"   # cyan brillante, distingue de splash (azul)
COLOR_CENTER    = "#67e8f9"


# ============================================================
# Widget
# ============================================================
class LocalizameScreen(QFrame):
    """Pantalla de transición de localización.

    Emite ``finished`` tras ``AUTO_DISMISS_MS`` milisegundos. El caller
    debe conectar la señal para mostrar la siguiente vista y, si lo
    desea, llamar a ``mark_completed()`` para no volver a mostrar
    esta pantalla.
    """

    finished = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        # v0.5.2: NO usar Qt.SplashScreen — en macOS ese flag hace que
        # la pantalla se descarte automáticamente al abrirse OTRA
        # ventana (lo que rompía nuestros halos: aparecían y un instante
        # después se cerraban porque el wizard/MainWindow asomaba). Con
        # solo Qt.Tool + Qt.FramelessWindowHint + StaysOnTop tenemos un
        # overlay top-level estable.
        self.setWindowFlags(
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        # Permitir al usuario saltar la pantalla con un click — mejora
        # UX en re-arranques rápidos cuando ya se entiende lo que hace.
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setFixedSize(SCREEN_WIDTH, SCREEN_HEIGHT)

        # Estado de animación
        self._phase = 0.0  # 0..1 cíclico

        # Texto detectado — se rellena tras llamar a detect_and_show().
        self._heading = "Localizándote"
        self._detected = "…"

        # Logo PNG; cae a texto si falta
        self._logo = logo_pixmap(theme="dark", width=LOGO_WIDTH_PX)

        # Animación: temporizador único a 30 FPS
        self._timer = QTimer(self)
        self._timer.setInterval(int(1000 / REFRESH_FPS))
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        # Auto-cierre tras ~2.5 s
        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self._on_auto_dismiss)
        self._dismiss_timer.start(AUTO_DISMISS_MS)

        self._center_on_screen()

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def detect_and_show(self) -> None:
        """Detecta la zona horaria del sistema y la pinta como resultado.

        Idempotente: si la detección falla muestra "Desconocida …" en
        el idioma actual (sin error técnico — el usuario no debería
        ver tracebacks en una pantalla de bienvenida).

        También vuelca el ``heading`` traducido para evitar tener que
        llamar manualmente a set_heading desde el caller.
        """

        # i18n: cargar el encabezado en el idioma actual; cae a inglés
        # si el sistema i18n aún no está inicializado.
        try:
            from shakevision.i18n import t
            self._heading = t("localizame.heading")
            prefix = t("localizame.detected_prefix")
            unknown = t("localizame.detected_unknown")
        except Exception:  # noqa: BLE001
            prefix = "Time zone: "
            unknown = "Unknown — using UTC"

        # Detección de la zona horaria (privada, sin red)
        try:
            from shakevision.services.timezone_service import (
                detect_system_timezone,
            )
            iana = detect_system_timezone()
        except Exception as exc:  # noqa: BLE001
            logger.debug("Localízame: detección falló (%s)", exc)
            iana = None

        self._detected = (prefix + iana) if iana else unknown
        self.update()

    def set_heading(self, text: str) -> None:
        """Permite traducir el texto principal antes de mostrar."""

        self._heading = text or self._heading
        self.update()

    def set_detected_label(self, text: str) -> None:
        """Sobrescribe el valor detectado (útil para tests)."""

        self._detected = text or self._detected
        self.update()

    def finish_now(self) -> None:
        """Cierra inmediatamente — útil para tests o saltos."""

        if self._dismiss_timer.isActive():
            self._dismiss_timer.stop()
        self._on_auto_dismiss()

    # Click anywhere → skip — v0.5.2: aumenta interactividad ahora que
    # la pantalla dura 4s. Si el usuario ya vio una vez la animación,
    # un click la salta.
    def mousePressEvent(self, event) -> None:  # noqa: N802
        self.finish_now()
        super().mousePressEvent(event)

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------
    def _tick(self) -> None:
        step = 1.0 / (HALO_PERIOD_S * REFRESH_FPS)
        self._phase = (self._phase + step) % 1.0
        self.update()

    def _on_auto_dismiss(self) -> None:
        self._timer.stop()
        self.finished.emit()
        self.close()

    def _center_on_screen(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geom = screen.availableGeometry()
        x = geom.x() + (geom.width() - self.width()) // 2
        y = geom.y() + (geom.height() - self.height()) // 2
        self.move(x, y)

    # ------------------------------------------------------------------
    # Pintado
    # ------------------------------------------------------------------
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        # 1) Fondo con gradiente vertical
        bg_grad = QLinearGradient(0, 0, 0, self.height())
        bg_grad.setColorAt(0.0, QColor(COLOR_BG_TOP))
        bg_grad.setColorAt(1.0, QColor(COLOR_BG_BOTTOM))
        painter.setBrush(QBrush(bg_grad))
        painter.setPen(QPen(QColor(COLOR_BORDER), 1))
        painter.drawRoundedRect(
            self.rect().adjusted(0, 0, -1, -1), 18, 18
        )

        # 2) Centro de los halos: ligeramente arriba para dejar espacio
        # al bloque de texto.
        cx = self.width() / 2.0
        cy = self.height() / 2.0 - 14

        # 3) Halos sonar — 5 anillos escalonados expandiéndose
        for i in range(HALO_RING_COUNT):
            local_phase = (self._phase + i / HALO_RING_COUNT) % 1.0
            radius = HALO_START_RADIUS_PX + local_phase * (
                HALO_MAX_RADIUS_PX - HALO_START_RADIUS_PX
            )
            # Alpha cae cuadráticamente — más rápido al final
            alpha = int(255 * 0.70 * (1.0 - local_phase) ** 1.8)
            color = QColor(COLOR_HALO)
            color.setAlpha(alpha)
            painter.setPen(QPen(color, 1.6))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(
                int(cx - radius), int(cy - radius),
                int(radius * 2), int(radius * 2),
            )

        # 4) Punto central luminoso (epicentro de las ondas)
        glow = QRadialGradient(cx, cy, 22)
        glow.setColorAt(0.0, QColor(255, 255, 255, 240))
        glow.setColorAt(0.4, QColor(COLOR_CENTER))
        c_transp = QColor(COLOR_HALO)
        c_transp.setAlpha(0)
        glow.setColorAt(1.0, c_transp)
        painter.setBrush(QBrush(glow))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(int(cx - 22), int(cy - 22), 44, 44)

        # 5) Logo pequeño arriba (si está disponible)
        if self._logo is not None and not self._logo.isNull():
            lw = self._logo.width()
            lx = int((self.width() - lw) / 2)
            painter.drawPixmap(lx, 36, self._logo)

        # 6) Bloque de texto debajo de los halos
        # Encabezado (más grande, blanco)
        head_font = QFont("Inter Variable", 13, QFont.Weight.DemiBold)
        head_font.setStyleHint(QFont.StyleHint.SansSerif)
        painter.setFont(head_font)
        painter.setPen(QColor(COLOR_PRIMARY))
        text_y = int(cy + HALO_MAX_RADIUS_PX + 18)
        painter.drawText(
            self.rect().adjusted(0, text_y, 0, 0),
            Qt.AlignHCenter | Qt.AlignTop,
            self._heading,
        )

        # Valor detectado (mono, cyan)
        val_font = QFont("JetBrains Mono", 11)
        val_font.setStyleHint(QFont.StyleHint.Monospace)
        painter.setFont(val_font)
        painter.setPen(QColor(COLOR_CENTER))
        painter.drawText(
            self.rect().adjusted(0, text_y + 26, 0, 0),
            Qt.AlignHCenter | Qt.AlignTop,
            self._detected,
        )

        painter.end()
