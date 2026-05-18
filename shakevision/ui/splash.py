"""
Pantalla de carga (splash) inicial.

Diseño visual (v0.5 — rebrand SeismicGuard)
-------------------------------------------
* Fondo deep navy con un gradiente radial sutil.
* Arriba: el logo PNG de SeismicGuard (logo_for_dark — texto blanco
  pensado para fondo oscuro). Si el PNG no se encuentra, fallback a
  texto "SeismicGuard" en sans-serif demi-bold.
* Centro: símbolo "epicentro" — un punto luminoso azul rodeado de
  tres anillos que se expanden y desvanecen, evocando ondas P
  emanando del foco sísmico.
* Debajo: línea de texto de estado actualizable
  ("Cargando fuentes…", "Construyendo interfaz…", etc.).
* Al pie: **barra de progreso determinista** (0–100 %) con fondo
  apagado y trazo cyan en la parte completada. La app decide cuánto
  empuja el progreso en cada etapa (set_progress).
* Bordes redondeados, sin marco de sistema.

La animación se hace con un único QTimer a 30 FPS que avanza una
fase compartida; el ``paintEvent`` consume esa fase para dibujar los
anillos. Es ligero (~0.1 ms/frame) y no requiere QPropertyAnimation.
"""

from __future__ import annotations

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

from shakevision.ui.icons import logo_pixmap


# ============================================================
# Constantes de aspecto
# ============================================================
SPLASH_WIDTH: int = 520
SPLASH_HEIGHT: int = 360

# El logo se renderiza a esta anchura (manteniendo proporciones).
# 320 px da una presencia clara sin dominar la pantalla pequeña.
LOGO_WIDTH_PX: int = 320

EPICENTER_RADIUS_PX: float = 8.0
RING_COUNT: int = 3
RING_MAX_RADIUS_PX: float = 78.0
RING_PERIOD_S: float = 2.4   # un anillo nuevo cada 2.4 / 3 ≈ 0.8 s

# Barra de progreso (proporcional al ancho del splash).
PROGRESS_BAR_HEIGHT: int = 4
PROGRESS_BAR_MARGIN_X: int = 64
PROGRESS_BAR_MARGIN_BOTTOM: int = 28

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
COLOR_PROGRESS_TRACK = "#1a2b4a"
COLOR_PROGRESS_FILL  = "#60a5fa"


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

        # Progreso determinista 0..1. La app empuja con set_progress();
        # el splash interpola visualmente con _progress_target para que
        # los saltos grandes (0.0 → 0.7) se vean como una animación
        # suave en lugar de un teletransporte instantáneo.
        self._progress = 0.0
        self._progress_target = 0.0

        # Cargar el logo PNG una sola vez (el splash es de corta vida).
        # logo_pixmap puede devolver QPixmap nulo si el asset falta
        # (instalación rota) — el paintEvent lo detecta y cae al
        # fallback de texto.
        self._logo = logo_pixmap(theme="dark", width=LOGO_WIDTH_PX)

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

    def set_progress(self, value: float) -> None:
        """Fija el progreso objetivo (0.0 – 1.0).

        El splash anima la transición desde el valor actual hasta el
        objetivo en ``_tick`` para que el usuario perciba "avance"
        en lugar de saltos discretos. Llamarla con un valor fuera de
        rango se clampea sin error.
        """

        clamped = max(0.0, min(1.0, float(value)))
        if clamped != self._progress_target:
            self._progress_target = clamped
            # No llamamos update() aquí: _tick repintará en el próximo
            # frame al avanzar la interpolación.

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

        # Interpolación lineal del progreso visual hacia el objetivo.
        # Damos un mínimo de ~0.4 % por frame (≈ 12 %/s a 30 FPS) +
        # un 20 % adicional del delta restante para que los saltos
        # grandes se vean rápidos al inicio y suaves al final.
        delta = self._progress_target - self._progress
        if abs(delta) > 1e-3:
            speed = 0.004 + 0.20 * abs(delta)
            if delta > 0:
                self._progress = min(self._progress + speed, self._progress_target)
            else:
                self._progress = max(self._progress - speed, self._progress_target)
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
        center_color2 = QColor(COLOR_ACCENT)
        center_color2.setAlpha(0)
        glow.setColorAt(1.0, center_color2)
        painter.setBrush(QBrush(glow))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(
            int(cx - EPICENTER_RADIUS_PX * 2.5),
            int(cy - EPICENTER_RADIUS_PX * 2.5),
            int(EPICENTER_RADIUS_PX * 5),
            int(EPICENTER_RADIUS_PX * 5),
        )

        # 5) Logo SeismicGuard (PNG si existe, sino fallback de texto).
        # Pintamos por encima de la zona del epicentro porque el logo
        # ya incorpora la marca; los anillos quedan visualmente "bajo"
        # él gracias al orden de pintado.
        title_y = int(cy + RING_MAX_RADIUS_PX + 22)
        if self._logo is not None and not self._logo.isNull():
            lw = self._logo.width()
            lh = self._logo.height()
            lx = int((self.width() - lw) / 2)
            painter.drawPixmap(lx, title_y, self._logo)
            text_block_y = title_y + lh + 14
        else:
            # Fallback: texto si el PNG no se encontró.
            title_font = QFont("Inter Variable", 22, QFont.Weight.DemiBold)
            title_font.setStyleHint(QFont.StyleHint.SansSerif)
            painter.setFont(title_font)
            painter.setPen(QColor(COLOR_PRIMARY))
            painter.drawText(
                self.rect().adjusted(0, title_y, 0, 0),
                Qt.AlignHCenter | Qt.AlignTop,
                "SeismicGuard",
            )
            text_block_y = title_y + 32

        # Versión más pequeña, monoespaciada (junto al logo / texto)
        version_font = QFont("JetBrains Mono", 10)
        version_font.setStyleHint(QFont.StyleHint.Monospace)
        painter.setFont(version_font)
        painter.setPen(QColor(COLOR_MUTED))
        painter.drawText(
            self.rect().adjusted(0, text_block_y, 0, 0),
            Qt.AlignHCenter | Qt.AlignTop,
            f"v{self._version}",
        )

        # 6) Estado dinámico + 3 puntos animados
        status_font = QFont("Inter Variable", 11, QFont.Weight.Normal)
        status_font.setStyleHint(QFont.StyleHint.SansSerif)
        painter.setFont(status_font)
        painter.setPen(QColor(COLOR_SECONDARY))

        # Animar los puntos de la estela ("…")
        n_dots = 1 + int(self._phase * 3) % 3
        dots = "·" * n_dots + " " * (3 - n_dots)
        painter.drawText(
            self.rect().adjusted(0, text_block_y + 22, 0, 0),
            Qt.AlignHCenter | Qt.AlignTop,
            f"{self._status} {dots}",
        )

        # 7) Barra de progreso al pie (track + relleno)
        self._draw_progress_bar(painter)

        painter.end()

    # ------------------------------------------------------------------
    # Sub-pintado: barra de progreso
    # ------------------------------------------------------------------
    def _draw_progress_bar(self, painter: QPainter) -> None:
        """Dibuja la barra de progreso en la zona inferior del splash.

        Estilo: pista oscura semi-transparente con bordes redondeados,
        relleno cyan con un leve degradé hacia un blanco fantasmal en
        la cabeza para sugerir "luz puntera".
        """

        bar_w = self.width() - 2 * PROGRESS_BAR_MARGIN_X
        bar_h = PROGRESS_BAR_HEIGHT
        bar_x = PROGRESS_BAR_MARGIN_X
        bar_y = self.height() - PROGRESS_BAR_MARGIN_BOTTOM - bar_h

        # Pista (background)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(COLOR_PROGRESS_TRACK)))
        painter.drawRoundedRect(bar_x, bar_y, bar_w, bar_h,
                                bar_h / 2, bar_h / 2)

        # Relleno proporcional al progreso interpolado
        fill_w = int(bar_w * self._progress)
        if fill_w > 0:
            grad = QLinearGradient(bar_x, 0, bar_x + fill_w, 0)
            grad.setColorAt(0.0, QColor(COLOR_PROGRESS_FILL))
            # Cabeza más brillante para sugerir "luz puntera"
            head = QColor(255, 255, 255, 220)
            grad.setColorAt(1.0, head)
            painter.setBrush(QBrush(grad))
            painter.drawRoundedRect(bar_x, bar_y, fill_w, bar_h,
                                    bar_h / 2, bar_h / 2)

        # Porcentaje numérico discreto a la derecha (solo si > 0)
        if self._progress > 0:
            pct_font = QFont("JetBrains Mono", 8)
            pct_font.setStyleHint(QFont.StyleHint.Monospace)
            painter.setFont(pct_font)
            painter.setPen(QColor(COLOR_MUTED))
            painter.drawText(
                bar_x, bar_y - 6,
                bar_w, 14,
                Qt.AlignRight | Qt.AlignVCenter,
                f"{int(self._progress * 100)}%",
            )
