"""
Pestaña de nivel superior **"Mi colección"** (我的).

Reúne lo que es del usuario, en dos bloques:

* **Favoritos** (``FavoritesStore``):
    - ★ Sismos  → doble clic revisa en Replay (estación cercana + TauP).
    - ★ Estaciones → doble clic la usa (selección en el Workbench).
* **Registros** (disco):
    - Grabaciones del detector STA/LTA — *solo se muestran si hay alguna* (C).
    - Catálogo QuakeML de fases revisadas.

Cada tabla tiene su acción (quitar favorito / eliminar / abrir). Reemplaza a la
antigua pestaña "Local" del Workbench.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from shakevision.i18n import LocaleService, t
from shakevision.processing.recorder import list_recordings
from shakevision.services.catalog_store import CatalogStore
from shakevision.services.favorites_store import FavoritesStore
from shakevision.ui.event_list_panel import _NumericItem
from shakevision.ui.signal_safety import subscribe


def _fmt(ts: float) -> str:
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S")
    except (OSError, OverflowError, ValueError):
        return "—"


class MyDataPanel(QFrame):
    """Favoritos (sismos/estaciones) + registros (grabaciones/catálogo)."""

    review_event = Signal(object)              # FavoriteEvent → revisar
    use_station = Signal(str, str)             # (network, code)
    recording_activated = Signal(str, str, str)  # (path, net, sta)
    review_catalog = Signal(int)               # idx en el catálogo → reabrir

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("WaveformPanel")
        self.setFrameShape(QFrame.NoFrame)

        self._fav_events: list = []

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        bar = QHBoxLayout()
        self._title = QLabel(t("mine.title"))
        self._title.setObjectName("SectionTitle")
        bar.addWidget(self._title)
        bar.addStretch(1)
        self.refresh_btn = QPushButton(t("local.refresh"))
        self.refresh_btn.clicked.connect(self.refresh)
        bar.addWidget(self.refresh_btn)
        root.addLayout(bar)

        outer = QSplitter(Qt.Vertical, parent=self)

        # ───── Bloque 1: Favoritos ─────
        fav = QSplitter(Qt.Horizontal, parent=outer)
        self._ev_table, self._ev_box, self._ev_hdr, self._ev_del, _ = \
            self._make_section(t("mine.fav_events"), t("mine.unfav"), 3)
        self._ev_table.itemDoubleClicked.connect(self._on_event_activated)
        self._ev_del.clicked.connect(self._on_unfav_event)
        fav.addWidget(self._ev_box)
        self._st_table, self._st_box, self._st_hdr, self._st_del, _ = \
            self._make_section(t("mine.fav_stations"), t("mine.unfav"), 2)
        self._st_table.itemDoubleClicked.connect(self._on_station_activated)
        self._st_del.clicked.connect(self._on_unfav_station)
        fav.addWidget(self._st_box)
        outer.addWidget(fav)

        # ───── Bloque 2: Registros ─────
        rec = QSplitter(Qt.Horizontal, parent=outer)
        (self._rec_table, self._rec_box, self._rec_hdr, self._rec_del,
         self._rec_open) = self._make_section(
            t("local.recordings"), t("local.delete"), 3,
            open_btn_text=t("local.open_folder"))
        self._rec_table.itemDoubleClicked.connect(self._on_recording_activated)
        self._rec_del.clicked.connect(self._on_delete_recording)
        self._rec_open.clicked.connect(self._on_open_recordings_folder)
        rec.addWidget(self._rec_box)
        (self._cat_table, self._cat_box, self._cat_hdr, self._cat_del,
         self._cat_open) = self._make_section(
            t("local.catalog"), t("local.delete"), 4,
            open_btn_text=t("local.open_folder"))
        self._cat_table.itemDoubleClicked.connect(self._on_catalog_activated)
        self._cat_del.clicked.connect(self._on_delete_catalog)
        self._cat_open.clicked.connect(self._on_open_catalog_folder)
        rec.addWidget(self._cat_box)
        outer.addWidget(rec)

        root.addWidget(outer, stretch=1)

        self._apply_headers()
        self.refresh()
        subscribe(self, LocaleService.language_changed_signal(),
                  self._retranslate)
        subscribe(self, FavoritesStore.changed_signal(), self.refresh)

    # ------------------------------------------------------------------
    @staticmethod
    def _make_section(title: str, btn_text: str, cols: int,
                      open_btn_text: Optional[str] = None):
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        hdr_row = QHBoxLayout()
        header = QLabel(title)
        header.setObjectName("Caption")
        header.setWordWrap(True)
        hdr_row.addWidget(header, stretch=1)
        open_btn = None
        if open_btn_text is not None:
            open_btn = QPushButton(open_btn_text)
            hdr_row.addWidget(open_btn)
        btn = QPushButton(btn_text)
        hdr_row.addWidget(btn)
        lay.addLayout(hdr_row)
        table = QTableWidget(0, cols)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(table, stretch=1)
        return table, box, header, btn, open_btn

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        # ★ Sismos
        self._fav_events = list(FavoritesStore.list_events())
        self._fav_events.sort(key=lambda e: e.timestamp_unix, reverse=True)
        self._ev_table.setRowCount(len(self._fav_events))
        for r, e in enumerate(self._fav_events):
            it = _NumericItem(_fmt(e.timestamp_unix), e.timestamp_unix)
            it.setData(Qt.UserRole + 1, e.id)
            self._ev_table.setItem(r, 0, it)
            self._ev_table.setItem(r, 1, _NumericItem(f"{e.magnitude:.1f}",
                                                      e.magnitude))
            self._ev_table.setItem(r, 2, QTableWidgetItem(e.place or "—"))

        # ★ Estaciones
        stations = list(FavoritesStore.list_stations())
        self._st_table.setRowCount(len(stations))
        for r, s in enumerate(stations):
            code = QTableWidgetItem(f"{s.network}.{s.code}")
            code.setData(Qt.UserRole + 1, s.network)
            code.setData(Qt.UserRole + 2, s.code)
            self._st_table.setItem(r, 0, code)
            self._st_table.setItem(r, 1, QTableWidgetItem(
                getattr(s, "site_name", "") or "—"))

        # Grabaciones — C: ocultar la sección si no hay ninguna.
        recs = list_recordings()
        self._rec_box.setVisible(bool(recs))
        self._rec_table.setRowCount(len(recs))
        for r, info in enumerate(recs):
            it = QTableWidgetItem(_fmt(info.time_unix))
            it.setData(Qt.UserRole + 1, str(info.path))
            it.setData(Qt.UserRole + 2, info.network)
            it.setData(Qt.UserRole + 3, info.station)
            self._rec_table.setItem(r, 0, it)
            self._rec_table.setItem(r, 1, QTableWidgetItem(
                f"{info.network}.{info.station}"))
            self._rec_table.setItem(r, 2, QTableWidgetItem(info.path.name))

        # Catálogo QuakeML
        try:
            events = CatalogStore().list_events()
        except Exception:  # noqa: BLE001
            events = []
        # C: ocultar la sección si no hay eventos guardados (igual que
        # grabaciones). Es una función de analista; al usuario casual no le
        # interesa ver una tabla vacía.
        self._cat_box.setVisible(bool(events))
        self._cat_table.setRowCount(len(events))
        for r, ev in enumerate(events):
            it = QTableWidgetItem(_fmt(ev["time"]))
            it.setData(Qt.UserRole + 1, int(ev.get("idx", -1)))
            self._cat_table.setItem(r, 0, it)
            self._cat_table.setItem(r, 1, QTableWidgetItem(ev["station"]))
            self._cat_table.setItem(r, 2, QTableWidgetItem(str(ev["n_picks"])))
            self._cat_table.setItem(r, 3, QTableWidgetItem(ev.get("desc", "")))

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def _on_event_activated(self, item: QTableWidgetItem) -> None:
        it = self._ev_table.item(item.row(), 0)
        qid = it.data(Qt.UserRole + 1) if it else None
        fav = next((e for e in self._fav_events if e.id == qid), None)
        if fav is not None:
            self.review_event.emit(fav)

    def _on_unfav_event(self) -> None:
        row = self._ev_table.currentRow()
        if row < 0:
            return
        it = self._ev_table.item(row, 0)
        qid = it.data(Qt.UserRole + 1) if it else None
        if qid:
            FavoritesStore.remove_event(str(qid))
            self.refresh()

    def _on_station_activated(self, item: QTableWidgetItem) -> None:
        it = self._st_table.item(item.row(), 0)
        if it is None:
            return
        net = it.data(Qt.UserRole + 1) or ""
        code = it.data(Qt.UserRole + 2) or ""
        if net and code:
            self.use_station.emit(str(net), str(code))

    def _on_unfav_station(self) -> None:
        row = self._st_table.currentRow()
        if row < 0:
            return
        it = self._st_table.item(row, 0)
        if it is None:
            return
        net = it.data(Qt.UserRole + 1)
        code = it.data(Qt.UserRole + 2)
        if net and code:
            FavoritesStore.remove_station(str(net), str(code))
            self.refresh()

    def _on_recording_activated(self, item: QTableWidgetItem) -> None:
        it = self._rec_table.item(item.row(), 0)
        if it is None:
            return
        path = it.data(Qt.UserRole + 1)
        if path:
            self.recording_activated.emit(
                str(path), str(it.data(Qt.UserRole + 2) or ""),
                str(it.data(Qt.UserRole + 3) or ""))

    def _on_delete_recording(self) -> None:
        row = self._rec_table.currentRow()
        if row < 0:
            return
        it = self._rec_table.item(row, 0)
        path = it.data(Qt.UserRole + 1) if it else None
        if not path:
            return
        from PySide6.QtWidgets import QMessageBox
        from pathlib import Path
        if QMessageBox.question(
                self, t("local.delete"),
                t("local.confirm_delete_rec",
                  name=Path(str(path)).name)) != QMessageBox.Yes:
            return
        try:
            Path(str(path)).unlink(missing_ok=True)
        except OSError:
            pass
        self.refresh()

    def _on_catalog_activated(self, item: QTableWidgetItem) -> None:
        """Doble clic en el catálogo → reabrir esa revisión en Replay."""

        it = self._cat_table.item(item.row(), 0)
        idx = it.data(Qt.UserRole + 1) if it else None
        if idx is not None and int(idx) >= 0:
            self.review_catalog.emit(int(idx))

    def _on_open_recordings_folder(self) -> None:
        from shakevision.processing.recorder import DEFAULT_RECORDINGS_DIR
        self._reveal(DEFAULT_RECORDINGS_DIR)

    def _on_open_catalog_folder(self) -> None:
        self._reveal(CatalogStore().path.parent)

    @staticmethod
    def _reveal(path) -> None:
        """Abre la carpeta en el explorador del sistema (para exportar a otro
        software). Crea la carpeta si aún no existe."""

        from pathlib import Path
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        p = Path(str(path))
        try:
            p.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))

    def _on_delete_catalog(self) -> None:
        row = self._cat_table.currentRow()
        if row < 0:
            return
        it = self._cat_table.item(row, 0)
        idx = it.data(Qt.UserRole + 1) if it else None
        if idx is None or int(idx) < 0:
            return
        from PySide6.QtWidgets import QMessageBox
        if QMessageBox.question(
                self, t("local.delete"),
                t("local.confirm_delete_cat")) != QMessageBox.Yes:
            return
        CatalogStore().remove_event(int(idx))
        self.refresh()

    # ------------------------------------------------------------------
    def _apply_headers(self) -> None:
        self._ev_table.setHorizontalHeaderLabels([
            t("events.col_time"), t("events.col_mag"), t("events.col_place")])
        self._st_table.setHorizontalHeaderLabels([
            t("events.col_station"), t("events.col_site_name")])
        self._rec_table.setHorizontalHeaderLabels([
            t("events.col_time"), t("events.col_station"), t("local.col_file")])
        self._cat_table.setHorizontalHeaderLabels([
            t("events.col_time"), t("events.col_station"),
            t("local.col_picks"), t("local.col_desc")])
        for tbl in (self._ev_table, self._st_table, self._rec_table,
                    self._cat_table):
            tbl.horizontalHeader().setSectionResizeMode(
                0, QHeaderView.ResizeToContents)

    def _retranslate(self) -> None:
        self._title.setText(t("mine.title"))
        self.refresh_btn.setText(t("local.refresh"))
        self._ev_hdr.setText(t("mine.fav_events"))
        self._st_hdr.setText(t("mine.fav_stations"))
        self._rec_hdr.setText(t("local.recordings"))
        self._cat_hdr.setText(t("local.catalog"))
        self._ev_del.setText(t("mine.unfav"))
        self._st_del.setText(t("mine.unfav"))
        self._rec_del.setText(t("local.delete"))
        self._cat_del.setText(t("local.delete"))
        self._rec_open.setText(t("local.open_folder"))
        self._cat_open.setText(t("local.open_folder"))
        self._apply_headers()
