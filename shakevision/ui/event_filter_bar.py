"""
Barra de filtros reutilizable para listas de sismos (Centro de eventos / Mi
colección).

Ofrece: magnitud mínima, **selector de rango temporal** (con calendario
emergente, en UTC) activable por casilla, y búsqueda por lugar. Emite
``filter_changed`` en cada cambio; el contenedor consulta ``min_mag()`` /
``time_range()`` / ``query()`` y refiltra con ``processing.event_filter``.

La lógica de filtrado vive en ``processing/event_filter.py`` (puro, sin Qt);
aquí solo está la UI.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QDateTime, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from shakevision.i18n import LocaleService, t
from shakevision.ui.combo_utils import fit_combo
from shakevision.ui.range_slider import RangeSlider
from shakevision.ui.signal_safety import subscribe

#: Umbrales del combo de magnitud mínima (None = todas).
_MAG_THRESHOLDS = (None, 2.0, 3.0, 4.0, 5.0, 6.0)

#: Rangos de profundidad (km) — clave i18n → (min, max). Categorías sísmicas
#: estándar: somero <70, intermedio 70–300, profundo >300.
_DEPTH_RANGES = (
    ("any", (None, None)),
    ("shallow", (None, 70.0)),
    ("intermediate", (70.0, 300.0)),
    ("deep", (300.0, None)),
)


class EventFilterBar(QWidget):
    """Fila de filtros: magnitud · rango temporal (calendario) · búsqueda."""

    filter_changed = Signal()

    def __init__(self, parent: Optional[QWidget] = None,
                 show_magnitude: bool = True,
                 show_reset: bool = True) -> None:
        super().__init__(parent)
        self.setObjectName("EventFilterBar")
        self._show_magnitude = bool(show_magnitude)
        self._show_reset = bool(show_reset)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        # ── Magnitud mínima (oculta cuando no aplica, p. ej. en "Mi colección") ──
        self._lbl_mag = QLabel(t("events.filter_mag"))
        row.addWidget(self._lbl_mag)
        self.mag_combo = QComboBox()
        for thr in _MAG_THRESHOLDS:
            self.mag_combo.addItem("", userData=thr)
        self.mag_combo.currentIndexChanged.connect(self._emit_changed)
        row.addWidget(self.mag_combo)
        if not self._show_magnitude:
            self._lbl_mag.setVisible(False)
            self.mag_combo.setVisible(False)

        # ── Profundidad (oculta junto con la magnitud: solo aplica a sismos) ──
        self._lbl_depth = QLabel(t("events.filter_depth"))
        row.addWidget(self._lbl_depth)
        self.depth_combo = QComboBox()
        for key, rng in _DEPTH_RANGES:
            self.depth_combo.addItem("", userData=(key, rng))
        self.depth_combo.currentIndexChanged.connect(self._emit_changed)
        row.addWidget(self.depth_combo)
        if not self._show_magnitude:
            self._lbl_depth.setVisible(False)
            self.depth_combo.setVisible(False)

        # ── Rango temporal (UTC), activable → slider en la 2.ª fila ──
        self.time_check = QCheckBox(t("events.filter_time"))
        self.time_check.toggled.connect(self._on_time_toggled)
        row.addWidget(self.time_check)

        # ── Búsqueda por lugar ──
        self.search_edit = QLineEdit()
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setPlaceholderText(t("events.filter_search"))
        self.search_edit.textChanged.connect(self._emit_changed)
        row.addWidget(self.search_edit, stretch=1)

        # ── Contador + reset ──
        self.count_lbl = QLabel("")
        self.count_lbl.setObjectName("Caption")
        row.addWidget(self.count_lbl)
        # Botón "Restablecer" OPCIONAL: el Centro de eventos lo quita (causaba
        # confusión / recargas pesadas); "Mi colección" lo conserva.
        self.reset_btn = None
        if self._show_reset:
            self.reset_btn = QPushButton(t("events.filter_reset"))
            self.reset_btn.clicked.connect(self.reset)
            row.addWidget(self.reset_btn)

        outer.addLayout(row)
        # Slider de rango temporal (2.ª fila, oculto hasta activar la casilla).
        _now = QDateTime.currentDateTimeUtc()
        _lo = float(_now.addDays(-30).toSecsSinceEpoch())
        _hi = float(_now.toSecsSinceEpoch())
        self.time_slider = RangeSlider()
        self.time_slider.set_bounds(_lo, _hi)
        self.time_slider.set_values(_lo, _hi)
        self.time_slider.range_changed.connect(lambda *_a: self._emit_changed())
        self.time_slider.setVisible(False)
        outer.addWidget(self.time_slider)

        self._set_time_enabled(False)
        self._apply_mag_texts()
        self._apply_depth_texts()
        # Ancho de combos = texto más largo entre TODOS los idiomas (el popup
        # ya no recorta "全部" / "Any" / etc. al cambiar de idioma).
        fit_combo(self.mag_combo, i18n_keys=["events.filter_mag_any"],
                  extra=[f"≥ {thr:.0f}" for thr in _MAG_THRESHOLDS if thr])
        fit_combo(self.depth_combo,
                  i18n_keys=[f"events.filter_depth_{k}" for k, _ in _DEPTH_RANGES])
        subscribe(self, LocaleService.language_changed_signal(),
                  self._retranslate)

    # ------------------------------------------------------------------
    def _on_time_toggled(self, on: bool) -> None:
        self._set_time_enabled(on)
        self._emit_changed()

    def _set_time_enabled(self, on: bool) -> None:
        # El slider de rango solo se muestra cuando el filtro temporal está on.
        self.time_slider.setVisible(bool(on))

    def set_time_bounds(self, t_min: float, t_max: float) -> None:
        """Ajusta el rango del slider al span real de los datos cargados.

        Si el filtro temporal NO está activo, alinea también la ventana al span
        completo; si SÍ está activo (el usuario está filtrando), respeta su
        selección (``set_bounds`` la recorta al nuevo rango)."""

        if t_max <= t_min:
            return
        self.time_slider.set_bounds(float(t_min), float(t_max))
        if not self.time_check.isChecked():
            self.time_slider.set_values(float(t_min), float(t_max))

    def _emit_changed(self, *_a) -> None:
        self.filter_changed.emit()

    # ── API que consulta el contenedor ────────────────────────────────
    def min_mag(self) -> Optional[float]:
        if not self._show_magnitude:
            return None
        return self.mag_combo.currentData()

    def time_range(self):
        """Devuelve ``(t_from, t_to)`` en epoch UTC, o ``(None, None)`` si el
        rango temporal está desactivado."""

        if not self.time_check.isChecked():
            return (None, None)
        return self.time_slider.values()

    def depth_range(self):
        """Devuelve ``(min_depth, max_depth)`` en km, o ``(None, None)``."""

        if not self._show_magnitude:
            return (None, None)
        data = self.depth_combo.currentData()
        if not data:
            return (None, None)
        return data[1]

    def query(self) -> str:
        return self.search_edit.text()

    def set_count(self, shown: int, total: int) -> None:
        self.count_lbl.setText(
            t("events.filter_count", shown=shown, total=total))

    def reset(self) -> None:
        self.mag_combo.blockSignals(True)
        self.mag_combo.setCurrentIndex(0)
        self.mag_combo.blockSignals(False)
        self.depth_combo.blockSignals(True)
        self.depth_combo.setCurrentIndex(0)
        self.depth_combo.blockSignals(False)
        self.search_edit.blockSignals(True)
        self.search_edit.clear()
        self.search_edit.blockSignals(False)
        self.time_check.blockSignals(True)
        self.time_check.setChecked(False)
        self.time_check.blockSignals(False)
        self._set_time_enabled(False)
        self._emit_changed()

    # ------------------------------------------------------------------
    def _apply_mag_texts(self) -> None:
        self.mag_combo.blockSignals(True)
        for i in range(self.mag_combo.count()):
            thr = self.mag_combo.itemData(i)
            self.mag_combo.setItemText(
                i, t("events.filter_mag_any") if thr is None else f"≥ {thr:.0f}")
        self.mag_combo.blockSignals(False)

    def _apply_depth_texts(self) -> None:
        self.depth_combo.blockSignals(True)
        for i in range(self.depth_combo.count()):
            data = self.depth_combo.itemData(i)
            key = data[0] if data else "any"
            self.depth_combo.setItemText(i, t(f"events.filter_depth_{key}"))
        self.depth_combo.blockSignals(False)

    def _retranslate(self) -> None:
        self._lbl_mag.setText(t("events.filter_mag"))
        self._lbl_depth.setText(t("events.filter_depth"))
        self.time_check.setText(t("events.filter_time"))
        self.search_edit.setPlaceholderText(t("events.filter_search"))
        if self.reset_btn is not None:
            self.reset_btn.setText(t("events.filter_reset"))
        self._apply_mag_texts()
        self._apply_depth_texts()
