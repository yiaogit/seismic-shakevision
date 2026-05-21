"""
Overlay reutilizable para indicar "cargando" o "error" sobre cualquier
panel. Lo usan los paneles del Globo y Datos mientras esperan al
primer batch de USGS, y se muestran en rojo si la red falla.

Diseño
------
* Frameless ``QFrame`` posicionado dentro del widget padre y movido
  para que ocupe toda su área (se reposiciona en ``resizeEvent``).
* Estado **loading**: anillo giratorio + texto "Cargando…".
* Estado **error**: icono ⚠ + texto + botón "Reintentar".
"""

from __future__ import annotations

import math

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QPainter,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from shakevision.i18n import LocaleService, t
from shakevision.ui.theme import (
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    FONT_STACK_SANS,
)


# Intervalo del temporizador del spinner (ms)
SPIN_INTERVAL_MS: int = 33  # ~30 FPS


class LoadingOverlay(QFrame):
    """Overlay con anillo giratorio o mensaje de error."""

    retry_clicked = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("LoadingOverlay")
        # Capturar clics para que el panel detrás no reciba interacción
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            "QFrame#LoadingOverlay { background-color: rgba(10,10,10,0.78); }"
        )

        self._mode = "loading"      # "loading" | "error" | "hidden"
        self._spin_angle = 0.0
        # v0.7.6: i18n-aware default. Previously hardcoded "Cargando…".
        self._message = t("overlay.loading")

        # Layout vertical centrado (texto + botón opcional)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(12)

        # Espacio para el spinner (lo dibuja paintEvent, no es widget)
        self._spinner_spacer = QLabel(" ")
        self._spinner_spacer.setFixedSize(56, 56)
        self._spinner_spacer.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(self._spinner_spacer, alignment=Qt.AlignCenter)

        self._title = QLabel(self._message)
        self._title.setAlignment(Qt.AlignCenter)
        self._title.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY};"
            f" font-family: {FONT_STACK_SANS};"
            f" font-size: 14px; font-weight: 500;"
        )
        layout.addWidget(self._title)

        self._subtitle = QLabel("")
        self._subtitle.setAlignment(Qt.AlignCenter)
        self._subtitle.setWordWrap(True)
        self._subtitle.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY};"
            f" font-family: {FONT_STACK_SANS};"
            f" font-size: 11px;"
        )
        self._subtitle.hide()
        layout.addWidget(self._subtitle)

        # v0.6: PrimaryButton + objectName → hereda del QSS global de
        # theme.py (fill accent + hover accent_hover dinámico).
        # v0.7.6: texto del botón i18n-able (antes hardcoded "Reintentar").
        self._retry_button = QPushButton(t("overlay.btn_retry"))
        self._retry_button.setObjectName("PrimaryButton")
        self._retry_button.setProperty("primary", True)
        self._retry_button.clicked.connect(self.retry_clicked)
        self._retry_button.hide()
        layout.addWidget(self._retry_button, alignment=Qt.AlignCenter)

        # Temporizador del spinner
        self._timer = QTimer(self)
        self._timer.setInterval(SPIN_INTERVAL_MS)
        self._timer.timeout.connect(self._tick)

        # Cubrir todo el padre desde el inicio
        if parent is not None:
            parent.installEventFilter(self)
            self._reposition()

        # v0.7.6: re-traducir botón y default loading text cuando el
        # usuario cambia el idioma en Ajustes. Sin esto, un overlay
        # construido en español queda con "Reintentar" para siempre
        # aunque el usuario cambie a 中文 / English / Français.
        try:
            LocaleService.language_changed_signal().connect(
                lambda _lang: self._retranslate())
        except Exception:  # noqa: BLE001
            pass

    def _retranslate(self) -> None:
        """Refresca los textos i18n al cambiar el idioma en vivo."""

        self._retry_button.setText(t("overlay.btn_retry"))
        # Si actualmente mostramos el mensaje "loading" por defecto,
        # también lo refrescamos. Si el caller pasó un texto explícito
        # (ej. "Inicializando globo 3D"), respetamos lo que él fijó.
        # Esta heurística: solo refrescamos si _message coincide con el
        # default i18n actual ANTES del cambio — pero como ya cambió,
        # nos arriesgamos a actualizarlo siempre cuando estamos en
        # loading: en la práctica el caller llama show_loading() con
        # su propio texto, no usa el default.
        # → preferimos pecar de no tocar para no pisar mensajes de
        # contexto, así que NO actualizamos _title aquí. Si el usuario
        # cambia idioma con un overlay abierto en estado "error", el
        # subtítulo (que viene de un exception ya formateado) queda en
        # el idioma original — aceptable.

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def show_loading(self, message: str = "",
                     subtitle: str = "") -> None:
        # v0.7.6: default vacío → resolver dinámicamente vía t() en
        # cada llamada, así si el caller no pasa mensaje siempre vemos
        # el texto en el idioma activo (no en español hardcoded).
        if not message:
            message = t("overlay.loading")
        self._mode = "loading"
        self._message = message
        self._title.setText(message)
        self._subtitle.setText(subtitle)
        self._subtitle.setVisible(bool(subtitle))
        self._retry_button.hide()
        self._timer.start()
        self.show()
        self._reposition()
        self.raise_()

    def show_error(self, message: str, subtitle: str = "",
                   show_retry: bool = True) -> None:
        self._mode = "error"
        self._message = message
        self._title.setText("⚠  " + message)
        self._subtitle.setText(subtitle)
        self._subtitle.setVisible(bool(subtitle))
        self._retry_button.setVisible(show_retry)
        self._timer.stop()
        self.update()
        self.show()
        self._reposition()
        self.raise_()

    def hide_overlay(self) -> None:
        self._mode = "hidden"
        self._timer.stop()
        self.hide()

    # ------------------------------------------------------------------
    # Manejo de tamaño + animación
    # ------------------------------------------------------------------
    def eventFilter(self, obj, event):  # noqa: N802 (firma Qt)
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.Resize and obj is self.parent():
            self._reposition()
        return False

    def _reposition(self) -> None:
        parent = self.parent()
        if isinstance(parent, QWidget):
            self.setGeometry(0, 0, parent.width(), parent.height())

    def _tick(self) -> None:
        self._spin_angle = (self._spin_angle + 8.0) % 360.0
        self.update()

    # ------------------------------------------------------------------
    # Pintado del spinner / icono de error
    # ------------------------------------------------------------------
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (firma Qt)
        super().paintEvent(event)
        if self._mode == "hidden":
            return

        # Centro del área del spinner_spacer
        spacer_geo = self._spinner_spacer.geometry()
        cx = spacer_geo.center().x()
        cy = spacer_geo.center().y()

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        # v0.6: leer colores del módulo theme en RUNTIME (no del import
        # cacheado) — así al cambiar de tema el siguiente repaint usa la
        # paleta nueva sin necesidad de reiniciar la app.
        from shakevision.ui import theme as _t

        if self._mode == "loading":
            # Anillo de fondo
            radius = 20
            pen_bg = QPen(QColor(_t.COLOR_PANEL_BORDER), 3)
            painter.setPen(pen_bg)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)

            # Arco animado (3/8 del círculo, gira)
            pen_arc = QPen(QColor(_t.COLOR_ACCENT), 3, Qt.SolidLine, Qt.RoundCap)
            painter.setPen(pen_arc)
            start_angle = int(-self._spin_angle * 16)  # Qt usa 1/16°
            span_angle = int(135 * 16)
            painter.drawArc(
                cx - radius, cy - radius, radius * 2, radius * 2,
                start_angle, span_angle,
            )

        else:  # error
            # Triángulo rojo (no usamos emoji directamente para que se vea
            # idéntico en todas las plataformas)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(_t.COLOR_ALERT)))
            r = 22
            from PySide6.QtCore import QPointF
            from PySide6.QtGui import QPolygonF
            pts = QPolygonF([
                QPointF(cx, cy - r),
                QPointF(cx + r * math.cos(math.radians(30)),
                        cy + r * math.sin(math.radians(30))),
                QPointF(cx - r * math.cos(math.radians(30)),
                        cy + r * math.sin(math.radians(30))),
            ])
            painter.drawPolygon(pts)

            # Signo de exclamación blanco encima
            painter.setPen(QPen(QColor("white"), 3, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(cx, cy - 8, cx, cy + 4)
            painter.drawPoint(cx, cy + 10)

        painter.end()
