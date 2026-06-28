"""
``RangeSlider`` — selector de **rango temporal de doble manija** (estilo brush).

Sustituye a los calendarios/QDateTimeEdit para elegir una ventana de tiempo:
una pista horizontal con dos manijas arrastrables y la ventana seleccionada
resaltada en medio. Se puede arrastrar cada manija o la ventana entera.

* Eje **no lineal** (más resolución a lo reciente) vía ``utils.timescale``.
* Valores en **epoch UTC**; emite ``range_changed(lo, hi)``.
* Colores leídos del tema en tiempo de pintado (claro/oscuro).
* Sin texto traducible: las etiquetas son fechas formateadas.
"""

from __future__ import annotations

import datetime as _dt
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath
from PySide6.QtWidgets import QWidget

from shakevision.utils import timescale as _ts

_PAD = 14          # margen lateral para que las manijas no se corten
_TRACK_H = 6       # grosor de la pista
_HANDLE_R = 8      # radio de la manija
_MIN_GAP_S = 3600.0  # ventana mínima: 1 h
_FLOOR_EPOCH = _dt.datetime(1900, 1, 1, tzinfo=_dt.timezone.utc).timestamp()


def _fmt(epoch: float) -> str:
    try:
        return _dt.datetime.fromtimestamp(
            epoch, tz=_dt.timezone.utc).strftime("%Y-%m-%d")
    except (OSError, OverflowError, ValueError):
        return "—"


class RangeSlider(QWidget):
    """Slider de rango temporal (doble manija)."""

    range_changed = Signal(float, float)   # (lo, hi) epoch UTC

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        now = _dt.datetime.now(tz=_dt.timezone.utc).timestamp()
        self._t_min = now - 10 * 365 * 86400.0
        self._t_max = now
        self._lo = now - 365 * 86400.0
        self._hi = now
        # Eje LINEAL (1.0): la posición es proporcional al tiempo (las marcas se
        # ven a escala). Para que lo reciente no quede apretado, los presets
        # acercan el rango del slider con ``set_window`` en vez de deformar el eje.
        self._warp = 1.0
        self._drag: Optional[str] = None   # "lo" | "hi" | "span" | None
        self._drag_x0 = 0.0
        self._lo0 = self._hi0 = 0.0
        self.setMinimumHeight(48)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)

    # ── API pública ──────────────────────────────────────────────────
    def set_bounds(self, t_min: float, t_max: float) -> None:
        self._t_min, self._t_max = float(t_min), float(t_max)
        self._lo, self._hi = _ts.clamp_range(
            self._lo, self._hi, self._t_min, self._t_max, _MIN_GAP_S)
        self.update()

    def set_values(self, lo: float, hi: float, *, emit: bool = False) -> None:
        self._lo, self._hi = _ts.clamp_range(
            lo, hi, self._t_min, self._t_max, _MIN_GAP_S)
        self.update()
        if emit:
            self.range_changed.emit(self._lo, self._hi)

    def set_window(self, lo: float, hi: float, pad: float = 0.6) -> None:
        """Encuadra el slider en la ventana ``[lo, hi]``: ajusta los LÍMITES con
        un margen proporcional y selecciona ``[lo, hi]``. Así la ventana elegida
        ocupa buena parte de la pista (no queda apretada en un extremo)."""

        lo, hi = float(lo), float(hi)
        span = max(1.0, hi - lo)
        t_min = max(_FLOOR_EPOCH, lo - pad * span)
        self.set_bounds(t_min, hi)
        self.set_values(lo, hi)

    def values(self) -> tuple[float, float]:
        return (self._lo, self._hi)

    # ── Geometría ────────────────────────────────────────────────────
    def _track_w(self) -> float:
        return max(1.0, self.width() - 2 * _PAD)

    def _x_for(self, value: float) -> float:
        f = _ts.frac_for_value(value, self._t_min, self._t_max, self._warp)
        return _PAD + f * self._track_w()

    def _value_for(self, x: float) -> float:
        f = (x - _PAD) / self._track_w()
        return _ts.value_for_frac(f, self._t_min, self._t_max, self._warp)

    def _track_y(self) -> float:
        return self.height() / 2.0 - 4

    # ── Pintado ──────────────────────────────────────────────────────
    def paintEvent(self, _ev) -> None:  # noqa: N802
        from shakevision.ui import theme as _t
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        y = self._track_y()
        x_lo, x_hi = self._x_for(self._lo), self._x_for(self._hi)

        track = QColor(_t.COLOR_PANEL_DIVIDER)
        accent = QColor(_t.COLOR_ACCENT)
        text = QColor(_t.COLOR_TEXT_SECONDARY)
        muted = QColor(_t.COLOR_TEXT_MUTED)

        # Pista de fondo.
        path = QPainterPath()
        path.addRoundedRect(QRectF(_PAD, y, self._track_w(), _TRACK_H), 3, 3)
        p.fillPath(path, track)
        # Ventana seleccionada.
        sel = QPainterPath()
        sel.addRoundedRect(QRectF(x_lo, y, max(0.0, x_hi - x_lo), _TRACK_H),
                           3, 3)
        p.fillPath(sel, accent)

        # Marcas a intervalos iguales (eje lineal → proporcionales al tiempo).
        # Etiqueta: año si el rango es largo, año-mes si es corto.
        f = QFont(self.font())
        f.setPointSizeF(8.0)
        p.setFont(f)
        p.setPen(muted)
        span = self._t_max - self._t_min
        fmt = "%Y" if span > 3 * 365 * 86400 else "%Y-%m"
        for k in range(6):
            frac = k / 5.0
            xv = self._t_min + frac * span          # lineal en el tiempo
            tx = _PAD + frac * self._track_w()
            label = _dt.datetime.fromtimestamp(
                xv, tz=_dt.timezone.utc).strftime(fmt)
            p.drawText(QRectF(tx - 24, y + 10, 48, 12),
                       Qt.AlignHCenter, label)

        # Manijas.
        for xh in (x_lo, x_hi):
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#ffffff"))
            p.drawEllipse(QPointF(xh, y + _TRACK_H / 2.0), _HANDLE_R, _HANDLE_R)
            p.setBrush(accent)
            p.drawEllipse(QPointF(xh, y + _TRACK_H / 2.0),
                          _HANDLE_R - 3, _HANDLE_R - 3)

        # Etiquetas lo/hi (fechas) arriba.
        f.setPointSizeF(9.0)
        p.setFont(f)
        p.setPen(text)
        p.drawText(QRectF(_PAD, 2, self._track_w() / 2.0, 14),
                   Qt.AlignLeft, _fmt(self._lo))
        p.drawText(QRectF(_PAD + self._track_w() / 2.0, 2,
                          self._track_w() / 2.0, 14),
                   Qt.AlignRight, _fmt(self._hi))
        p.end()

    # ── Interacción ──────────────────────────────────────────────────
    def mousePressEvent(self, ev) -> None:  # noqa: N802
        x = ev.position().x()
        x_lo, x_hi = self._x_for(self._lo), self._x_for(self._hi)
        if abs(x - x_lo) <= _HANDLE_R + 4:
            self._drag = "lo"
        elif abs(x - x_hi) <= _HANDLE_R + 4:
            self._drag = "hi"
        elif x_lo < x < x_hi:
            self._drag = "span"
            self._drag_x0 = x
            self._lo0, self._hi0 = self._lo, self._hi
        else:
            # Click fuera → mueve la manija más cercana.
            self._drag = "lo" if abs(x - x_lo) < abs(x - x_hi) else "hi"
            self._apply_handle(x)

    def mouseMoveEvent(self, ev) -> None:  # noqa: N802
        if self._drag is None:
            return
        x = ev.position().x()
        if self._drag == "span":
            dx = x - self._drag_x0
            x_lo0 = self._x_for(self._lo0) + dx
            x_hi0 = self._x_for(self._hi0) + dx
            lo, hi = self._value_for(x_lo0), self._value_for(x_hi0)
            self._lo, self._hi = _ts.clamp_range(
                lo, hi, self._t_min, self._t_max, _MIN_GAP_S)
            self.update()
            self.range_changed.emit(self._lo, self._hi)
        else:
            self._apply_handle(x)

    def mouseReleaseEvent(self, _ev) -> None:  # noqa: N802
        self._drag = None

    def _apply_handle(self, x: float) -> None:
        v = self._value_for(x)
        if self._drag == "lo":
            self._lo = v
        else:
            self._hi = v
        self._lo, self._hi = _ts.clamp_range(
            self._lo, self._hi, self._t_min, self._t_max, _MIN_GAP_S)
        self.update()
        self.range_changed.emit(self._lo, self._hi)
