"""
Panel de **lista de eventos** (catálogo USGS) — Workbench sub-tab.

Muestra los sismos del feed USGS en una tabla ordenable (hora / magnitud /
profundidad / lugar). Hacer doble clic (o seleccionar + Enter) en una fila
abre ese evento en la pestaña Replay para revisarlo (misma ruta dirigida por
evento que el clic en el globo, pero más práctica para elegir uno concreto de
la lista — patrón EEV de SeisAn / lista de eventos de scolv).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from shakevision.i18n import LocaleService, t
from shakevision.ui.signal_safety import subscribe


class _NumericItem(QTableWidgetItem):
    """Item de tabla que ordena por un valor numérico (no por texto)."""

    def __init__(self, text: str, value: float) -> None:
        super().__init__(text)
        self.setData(Qt.UserRole, float(value))
        self.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)

    def __lt__(self, other) -> bool:  # noqa: D105
        try:
            return self.data(Qt.UserRole) < other.data(Qt.UserRole)
        except (TypeError, AttributeError):
            return super().__lt__(other)


class EventListPanel(QFrame):
    """Tabla del catálogo de sismos; doble clic → revisar en Replay."""

    #: Emite el id del sismo a revisar (doble clic / Enter en una fila).
    event_activated = Signal(str)
    #: Emite el id al SELECCIONAR una fila (clic simple) — para el centro de
    #: eventos, que muestra las estaciones cercanas al seleccionado.
    event_selected = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("WaveformPanel")
        self.setFrameShape(QFrame.NoFrame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self._header = QLabel(t("events.title"))
        self._header.setObjectName("SectionTitle")
        layout.addWidget(self._header)

        self._loaded_once = False
        self._has_data = False
        self._hint = QLabel("")
        self._hint.setObjectName("Caption")
        layout.addWidget(self._hint)

        self._table = QTableWidget(0, 4)
        self._table.setObjectName("EventTable")
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setSortingEnabled(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents)
        self._table.itemDoubleClicked.connect(self._on_double_clicked)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._table, stretch=1)

        self._apply_headers()
        self._update_hint()
        subscribe(self, LocaleService.language_changed_signal(),
                  self._retranslate)

    # ------------------------------------------------------------------
    def _update_hint(self) -> None:
        """Estado del listado: cargando / sin eventos / instrucción."""

        if not self._loaded_once:
            self._hint.setText(t("events.loading"))
        elif not self._has_data:
            self._hint.setText(t("events.empty"))
        else:
            self._hint.setText(t("events.hint"))

    def set_events(self, quakes) -> None:
        """Rellena la tabla con la lista de ``Earthquake`` (recientes primero)."""

        rows = sorted(quakes, key=lambda q: q.timestamp_unix, reverse=True)
        self._loaded_once = True
        self._has_data = len(rows) > 0
        self._update_hint()
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(rows))
        for r, q in enumerate(rows):
            when = datetime.fromtimestamp(q.timestamp_unix, tz=timezone.utc)
            time_item = _NumericItem(
                when.strftime("%Y-%m-%d %H:%M:%S"), q.timestamp_unix)
            # El id del sismo viaja en la columna 0 para recuperarlo al activar.
            time_item.setData(Qt.UserRole + 1, q.id)
            mag_item = _NumericItem(f"{q.magnitude:.1f}", q.magnitude)
            depth_item = _NumericItem(f"{q.depth_km:.0f}", q.depth_km)
            place_item = QTableWidgetItem(q.place or "—")
            place_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            for c, item in enumerate(
                    (time_item, mag_item, depth_item, place_item)):
                self._table.setItem(r, c, item)
        self._table.setSortingEnabled(True)

    def _on_double_clicked(self, item: QTableWidgetItem) -> None:
        row = item.row()
        id_item = self._table.item(row, 0)
        if id_item is None:
            return
        quake_id = id_item.data(Qt.UserRole + 1)
        if quake_id:
            self.event_activated.emit(str(quake_id))

    def _on_selection_changed(self) -> None:
        items = self._table.selectedItems()
        if not items:
            return
        id_item = self._table.item(items[0].row(), 0)
        if id_item is not None:
            qid = id_item.data(Qt.UserRole + 1)
            if qid:
                self.event_selected.emit(str(qid))

    def reset(self) -> None:
        self._table.setRowCount(0)

    # ------------------------------------------------------------------
    def _apply_headers(self) -> None:
        self._table.setHorizontalHeaderLabels([
            t("events.col_time"), t("events.col_mag"),
            t("events.col_depth"), t("events.col_place"),
        ])

    def _retranslate(self) -> None:
        self._header.setText(t("events.title"))
        self._update_hint()
        self._apply_headers()
