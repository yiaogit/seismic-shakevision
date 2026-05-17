"""
Pantalla de carga (splash) inicial.

Diseño visual
-------------
* Fondo deep navy con un gradiente radial sutil.
* Centro: símbolo "epicentro" — un punto luminoso azul rodeado de
  tres anillos que se expanden y desvanecen, evocando ondas P
  emanando del foco sísmico.
* Debajo: nombre de la app, versión, y una línea de texto de estado
  que la app puede actualizar mientras inicializa
  ("Cargando fuentes…", "Construyendo interfaz…", etc.).
* Bordes redondeados, sin marco de sistema.

La animación se hace con un único QTimer a 30 FPS que avanza una
fase compartida; el ``paintEvent`` consume esa fase para dibujar los
anillos. Es ligero (~0.1 ms/frame) y no requiere QPropertyAnimation.
"""

from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import Qt, QTimer
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


# ============================================================
# Constantes de aspecto
# ============================================================
SPLASH_WIDTH: int = 480
SPLASH_HEIGHT: int = 320

EPICENTER_RADIUS_PX: float = 9.0
RING_COUNT: int = 3
RING_MAX_RADIUS_PX: float = 96.0
RING_PERIOD_S: float = 2.4   # un anillo nuevo cada 2.4 / 3 ≈ 0.8 s

REFRESH_FPS: int = 30


# Colores (coherentes con el resto del tema)
COLOR_BG_TOP    = "#0a1226"
COLOR_BG_BOTTOM = "#02030a"
COLOR_PANEL     = "#0d1226"
COLOR_BORDER    = "#1a2b4a"
COLOR_PRIMARY   = "#fafafa"
COLOR_SECONDARY = "#a1a1aa"
COLOR_MUTED     = "#71717a"
COLOR_ACCENT    = "#3b82f6"
COLOR_GLOW      = "#60a5fa"


# ============================================================
# Widget
# ============================================================
class SplashScreen(QFrame):
    """Pantalla de carga sin marco con animación de ondas sísmicas."""

    def __init__(self, version: str = "0.0.0",
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        # Sin marco + transparencia + arriba de todo
        self.setWindowFlags(
            Qt.SplashScreen
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(SPLASH_WIDTH, SPLASH_HEIGHT)

        self._version = version
        self._status = "Inicializando…"
        self._phase = 0.0  # 0..1 cíclico para la animación

        # Temporizador de redibujado
        self._timer = QTimer(self)
        self._timer.setInterval(int(1000 / REFRESH_FPS))
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        # Centrar en la pantalla
        self._center_on_screen()

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def set_status(self, text: str) -> None:
        """Actualiza la línea de estado mostrada bajo el logo."""

        if text != self._status:
            self._status = text
            self.update()

    def finish_and_close(self) -> None:
        """Detiene la animación y cierra el splash de forma limpia."""

        self._timer.stop()
        self.close()

    # ------------------------------------------------------------------
    # Animación
    # ------------------------------------------------------------------
    def _tick(self) -> None:
        # Avanzamos la fase 1 / (RING_PERIOD_S * REFRESH_FPS) por frame
        step = 1.0 / (RING_PERIOD_S * REFRESH_FPS)
        self._phase = (self._phase + step) % 1.0
        self.update()

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
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (firma Qt)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        # 1) Fondo redondeado con gradiente vertical
        bg_grad = QLinearGradient(0, 0, 0, self.height())
        bg_grad.setColorAt(0.0, QColor(COLOR_BG_TOP))
        bg_grad.setColorAt(1.0, QColor(COLOR_BG_BOTTOM))
        painter.setBrush(QBrush(bg_grad))
        painter.setPen(QPen(QColor(COLOR_BORDER), 1))
        painter.drawRoundedRect(
            self.rect().adjusted(0, 0, -1, -1), 18, 18
        )

        # 2) Halo radial sutil detrás del logo
        cx = self.width() / 2.0
        cy = self.height() / 2.0 - 32  # ligeramente arriba para hacer hueco al texto
        halo = QRadialGradient(cx, cy, 140)
        halo.setColorAt(0.0, QColor(59, 130, 246, 56))
        halo.setColorAt(1.0, QColor(59, 130, 246, 0))
        painter.setBrush(QBrush(halo))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(int(cx - 140), int(cy - 140), 280, 280)

        # 3) Anillos sísmicos: tres ondas escalonadas en fase
        for i in range(RING_COUNT):
            local_phase = (self._phase + i / RING_COUNT) % 1.0
            radius = EPICENTER_RADIUS_PX + local_phase * (
                RING_MAX_RADIUS_PX - EPICENTER_RADIUS_PX
            )
            # Opacidad cae desde 0.85 al inicio hasta 0 al final
            alpha = int(255 * 0.85 * (1.0 - local_phase) ** 1.6)
            color = QColor(COLOR_GLOW)
            color.setAlpha(alpha)
            pen = QPen(color, 1.6)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(
                int(cx - radius), int(cy - radius),
                int(radius * 2), int(radius * 2),
            )

        # 4) Epicentro: punto luminoso central
        center_color = QColor(COLOR_GLOW)
        glow = QRadialGradient(cx, cy, EPICENTER_RADIUS_PX * 2.5)
        glow.setColorAt(0.0, QColor(255, 255, 255, 230))
        glow.setColorAt(0.4, center_color)
        center_color2 = QColor(COLOR_ACCENT); center_color2.setAlpha(0)
        glow.setColorAt(1.0, center_color2)
        painter.setBrush(QBrush(glow))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(
            int(cx - EPICENTER_RADIUS_PX * 2.5),
            int(cy - EPICENTER_RADIUS_PX * 2.5),
            int(EPICENTER_RADIUS_PX * 5),
            int(EPICENTER_RADIUS_PX * 5),
        )

        # 5) Tipografía: nombre + versión
        title_font = QFont(
            "Inter Variable", 22, QFont.Weight.DemiBold
        )
        # Fallback si Inter no está cargada todavía
        title_font.setStyleHint(QFont.StyleHint.SansSerif)
        painter.setFont(title_font)
        painter.setPen(QColor(COLOR_PRIMARY))

        title_y = int(cy + RING_MAX_RADIUS_PX + 18)
        painter.drawText(
            self.rect().adjusted(0, title_y, 0, 0),
            Qt.AlignHCenter | Qt.AlignTop,
            "ShakeVision",
        )

        # Versión más pequeña, monoespaciada
        version_font = QFont("JetBrains Mono", 10)
        version_font.setStyleHint(QFont.StyleHint.Monospace)
        painter.setFont(version_font)
        painter.setPen(QColor(COLOR_MUTED))
        painter.drawText(
            self.rect().adjusted(0, title_y + 32, 0, 0),
            Qt.AlignHCenter | Qt.AlignTop,
            f"v{self._version}",
        )

        # 6) Estado dinámico + 3 puntos animados
        status_font = QFont(
            "Inter Variable", 11, QFont.Weight.Normal
        )
        status_font.setStyleHint(QFont.StyleHint.SansSerif)
        painter.setFont(status_font)
        painter.setPen(QColor(COLOR_SECONDARY))

        # Animar los puntos de la estela ("…")
        n_dots = 1 + int(self._phase * 3) % 3
        dots = "·" * n_dots + " " * (3 - n_dots)
        painter.drawText(
            self.rect().adjusted(0, title_y + 56, 0, 0),
            Qt.AlignHCenter | Qt.AlignTop,
            f"{self._status} {dots}",
        )

        painter.end()
