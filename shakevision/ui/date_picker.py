"""
Utilidades compartidas de **selección de fecha/hora** para todos los
buscadores temporales (filtro en vivo, búsqueda histórica, replay).

Objetivos (ver petición del usuario):
  * Acotar SIEMPRE el rango seleccionable: tope = ahora (UTC) para tapar
    fechas futuras / sin datos (el calendario las pinta en gris vía el QSS
    ``QCalendarWidget QAbstractItemView:disabled``); piso = 1900 (el catálogo
    ANSS no va más atrás).
  * Un único punto de configuración para que TODAS las áreas se comporten
    igual y sea fácil de mantener.
  * Atajos modernos: ``QuickRangeBar`` con presets (24 h / 7 d / 30 d / 1 a /
    5 a) que rellenan el rango relativo a "ahora", como en apps tipo Google
    Analytics / Grafana.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QDate, QDateTime, Qt, Signal
from PySide6.QtWidgets import QDateTimeEdit, QHBoxLayout, QPushButton, QWidget

from shakevision.i18n import LocaleService, t
from shakevision.ui.signal_safety import subscribe

#: Suelo del catálogo ANSS (no hay datos antes de ~1900).
CATALOG_FLOOR = QDate(1900, 1, 1)


def make_datetime_edit(
    initial: Optional[QDateTime] = None,
    *,
    with_seconds: bool = False,
    fmt: Optional[str] = None,
    minimum_date: Optional[QDate] = CATALOG_FLOOR,
    cap_now: bool = True,
) -> QDateTimeEdit:
    """Crea un ``QDateTimeEdit`` UTC ya configurado y acotado.

    * ``cap_now`` fija ``maximumDateTime`` = ahora (UTC) → no se pueden elegir
      instantes futuros y el calendario los deshabilita.
    * ``minimum_date`` fija el suelo (por defecto 1900).
    * ``fmt`` permite un formato propio (p. ej. replay añade ``'UTC'``).
    """

    ed = QDateTimeEdit()
    ed.setTimeSpec(Qt.TimeSpec.UTC)
    if fmt is None:
        fmt = "yyyy-MM-dd HH:mm:ss" if with_seconds else "yyyy-MM-dd HH:mm"
    ed.setDisplayFormat(fmt)
    ed.setCalendarPopup(True)
    if minimum_date is not None:
        ed.setMinimumDate(minimum_date)
    if cap_now:
        ed.setMaximumDateTime(QDateTime.currentDateTimeUtc())
    if initial is not None:
        ed.setDateTime(initial)
    return ed


def cap_to_now(*edits: QDateTimeEdit) -> None:
    """Refresca el tope a 'ahora' (UTC) — llamar antes de mostrar el popup
    para que el límite no quede obsoleto en sesiones largas."""

    now = QDateTime.currentDateTimeUtc()
    for ed in edits:
        try:
            ed.setMaximumDateTime(now)
        except RuntimeError:
            pass


#: Presets de la barra rápida: ``(clave_i18n, días)``.
_QUICK_PRESETS = (
    ("daterange.24h", 1),
    ("daterange.7d", 7),
    ("daterange.30d", 30),
    ("daterange.1y", 365),
    ("daterange.5y", 365 * 5),
)


class QuickRangeBar(QWidget):
    """Fila de chips de rango relativo a 'ahora'.

    Emite ``range_picked(from_epoch, to_epoch)`` en UTC al pulsar un preset.
    """

    range_picked = Signal(float, float)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("QuickRangeBar")
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self._buttons: list[tuple[QPushButton, str]] = []
        for key, days in _QUICK_PRESETS:
            btn = QPushButton(t(key))
            btn.setObjectName("ChipButton")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, d=days: self._emit(d))
            row.addWidget(btn)
            self._buttons.append((btn, key))
        row.addStretch(1)
        subscribe(self, LocaleService.language_changed_signal(),
                  self._retranslate)

    def _emit(self, days: int) -> None:
        to = QDateTime.currentDateTimeUtc()
        frm = to.addDays(-days)
        self.range_picked.emit(
            float(frm.toSecsSinceEpoch()), float(to.toSecsSinceEpoch()))

    def _retranslate(self) -> None:
        for btn, key in self._buttons:
            try:
                btn.setText(t(key))
            except RuntimeError:
                pass
