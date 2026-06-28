"""
Barra de **búsqueda histórica** (catálogo completo USGS fdsnws-event).

Formulario: rango temporal (UTC, admite años pasados) · magnitud mín/máx ·
preset de región · orden · límite · botón Buscar. Emite ``search_requested``
con el dict de parámetros listo para ``FDSNEventClient.query``. La lógica de
red vive en ``services/fdsn_worker.py``; aquí solo está la UI.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QDateTime, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from shakevision.i18n import LocaleService, t
from shakevision.services import region_presets
from shakevision.ui.combo_utils import fit_combo
from shakevision.ui.date_picker import QuickRangeBar
from shakevision.ui.range_slider import RangeSlider
from shakevision.ui.signal_safety import subscribe

#: ``orderby`` de fdsnws → clave i18n de etiqueta.
_SORTS = (
    ("time", "hist.sort_time_desc"),
    ("time-asc", "hist.sort_time_asc"),
    ("magnitude", "hist.sort_mag_desc"),
    ("magnitude-asc", "hist.sort_mag_asc"),
)
_LIMITS = (100, 500, 2000, 20000)


class HistoricalSearchBar(QWidget):
    """Formulario de consulta al catálogo histórico."""

    search_requested = Signal(dict)
    clear_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("HistoricalSearchBar")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        # ── Fila 1: atajos relativos + slider de rango (sustituye calendarios) ──
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        self._quick = QuickRangeBar()
        self._quick.range_picked.connect(self._on_quick_range)
        row1.addWidget(self._quick)
        now = QDateTime.currentDateTimeUtc()
        self.time_slider = RangeSlider()
        self.time_slider.set_window(
            float(now.addYears(-1).toSecsSinceEpoch()),
            float(now.toSecsSinceEpoch()))
        row1.addWidget(self.time_slider, stretch=1)
        root.addLayout(row1)

        # ── Fila 2: magnitud · región · orden · límite · buscar ──
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        self._lbl_min = QLabel(t("hist.min_mag"))
        row2.addWidget(self._lbl_min)
        self.min_mag = self._make_mag(default=4.5)
        row2.addWidget(self.min_mag)
        self._lbl_max = QLabel(t("hist.max_mag"))
        row2.addWidget(self._lbl_max)
        self.max_mag = self._make_mag(default=10.0)
        row2.addWidget(self.max_mag)

        self._lbl_region = QLabel(t("hist.region"))
        row2.addWidget(self._lbl_region)
        self.region_combo = QComboBox()
        self._fill_regions()
        row2.addWidget(self.region_combo)

        self._lbl_sort = QLabel(t("hist.sort"))
        row2.addWidget(self._lbl_sort)
        self.sort_combo = QComboBox()
        for key, _lbl in _SORTS:
            self.sort_combo.addItem("", userData=key)
        row2.addWidget(self.sort_combo)

        self._lbl_limit = QLabel(t("hist.limit"))
        row2.addWidget(self._lbl_limit)
        self.limit_combo = QComboBox()
        for lim in _LIMITS:
            self.limit_combo.addItem(str(lim), userData=lim)
        self.limit_combo.setCurrentIndex(1)  # 500 por defecto
        fit_combo(self.limit_combo)
        row2.addWidget(self.limit_combo)

        row2.addStretch(1)
        self.clear_btn = QPushButton(t("hist.clear"))
        self.clear_btn.clicked.connect(self.clear_requested)
        row2.addWidget(self.clear_btn)
        self.search_btn = QPushButton(t("hist.search"))
        self.search_btn.setObjectName("PrimaryButton")
        self.search_btn.clicked.connect(self._emit_search)
        row2.addWidget(self.search_btn)
        root.addLayout(row2)

        self._hint = QLabel(t("hist.hint"))
        self._hint.setObjectName("Caption")
        self._hint.setWordWrap(True)
        root.addWidget(self._hint)

        self._apply_sort_texts()
        fit_combo(self.sort_combo, i18n_keys=[lbl for _k, lbl in _SORTS])
        subscribe(self, LocaleService.language_changed_signal(),
                  self._retranslate)

    # ------------------------------------------------------------------
    def _on_quick_range(self, from_epoch: float, to_epoch: float) -> None:
        # Encuadra el slider en la ventana del atajo (eje lineal, proporcional).
        self.time_slider.set_window(float(from_epoch), float(to_epoch))

    @staticmethod
    def _make_mag(default: float) -> QDoubleSpinBox:
        sp = QDoubleSpinBox()
        sp.setRange(0.0, 10.0)
        sp.setSingleStep(0.5)
        sp.setDecimals(1)
        sp.setValue(default)
        return sp

    def _fill_regions(self) -> None:
        loc = LocaleService.current_language() or "en"
        self.region_combo.blockSignals(True)
        self.region_combo.clear()
        for key, name in region_presets.presets(loc):
            self.region_combo.addItem(name, userData=key)
        self.region_combo.blockSignals(False)
        _samples = [n for lng in LocaleService.available_languages()
                    for _k, n in region_presets.presets(lng)]
        fit_combo(self.region_combo, extra=_samples)

    # ------------------------------------------------------------------
    def _emit_search(self) -> None:
        params = self.build_params()
        self.search_requested.emit(params)

    def build_params(self) -> dict:
        """Traduce el formulario a parámetros de ``FDSNEventClient.query``."""

        lo, hi = self.time_slider.values()
        params: dict = {
            "starttime": float(lo),
            "endtime": float(hi),
            "min_magnitude": float(self.min_mag.value()),
            "max_magnitude": float(self.max_mag.value()),
            "orderby": self.sort_combo.currentData() or "time",
            "limit": int(self.limit_combo.currentData() or 500),
        }
        bbox = region_presets.bbox_for(self.region_combo.currentData())
        if bbox is not None:
            params.update(
                min_latitude=bbox[0], max_latitude=bbox[1],
                min_longitude=bbox[2], max_longitude=bbox[3])
        return params

    # ------------------------------------------------------------------
    def set_searching(self, busy: bool) -> None:
        self.search_btn.setEnabled(not busy)
        self.search_btn.setText(t("hist.searching") if busy else t("hist.search"))

    def _apply_sort_texts(self) -> None:
        self.sort_combo.blockSignals(True)
        for i in range(self.sort_combo.count()):
            key = self.sort_combo.itemData(i)
            label = next((lbl for k, lbl in _SORTS if k == key), "")
            self.sort_combo.setItemText(i, t(label))
        self.sort_combo.blockSignals(False)

    def _retranslate(self) -> None:
        self._lbl_min.setText(t("hist.min_mag"))
        self._lbl_max.setText(t("hist.max_mag"))
        self._lbl_region.setText(t("hist.region"))
        self._lbl_sort.setText(t("hist.sort"))
        self._lbl_limit.setText(t("hist.limit"))
        self.search_btn.setText(t("hist.search"))
        self.clear_btn.setText(t("hist.clear"))
        self._hint.setText(t("hist.hint"))
        self._apply_sort_texts()
        self._fill_regions()
