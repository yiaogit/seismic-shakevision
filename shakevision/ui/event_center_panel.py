"""
**Centro de eventos** (pestaña de nivel superior, junto a Globo y Datos).

Combina:
  * la tabla de catálogo USGS (``EventListPanel``) a la izquierda;
  * un panel de **estaciones cercanas** al evento seleccionado, a la derecha.

Flujo: el usuario selecciona un sismo → se listan las estaciones IRIS/Shake
más cercanas (Δ en grados, calculado en local, sin red) → doble clic en una
estación → ``review_requested(quake_id, station)`` para abrirlo en Replay con
ESA estación (cercana ⇒ ventana razonable ⇒ P/S dentro del dato).

Así se separa limpiamente del flujo en vivo: revisar un evento NO conecta
SeedLink ni toca el combo de la barra lateral; descarga del archivo IRIS.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
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
from shakevision.processing.measurements import great_circle_degrees
from shakevision.services.favorites_store import FavoritesStore
from shakevision.ui.event_list_panel import EventListPanel, _NumericItem
from shakevision.ui.signal_safety import subscribe


def _distance_category(dist_deg: float) -> str:
    """Etiqueta legible de la distancia epicentral (i18n)."""

    if dist_deg < 1.5:
        return t("events.cat_local")
    if dist_deg < 10.0:
        return t("events.cat_regional")
    return t("events.cat_teleseism")


def nearest_stations(lat: float, lon: float, stations, k: int = 8):
    """Devuelve las ``k`` estaciones más cercanas como ``[(station, Δ°), …]``."""

    scored = [
        (s, great_circle_degrees(lat, lon, s.latitude, s.longitude))
        for s in stations
    ]
    scored.sort(key=lambda it: it[1])
    return scored[:k]


class EventCenterPanel(QFrame):
    """Tabla de eventos + estaciones cercanas → revisar en Replay."""

    #: (quake_id, station_obj) al elegir una estación para revisar el evento.
    review_requested = Signal(str, object)
    #: Cambió la ventana del feed USGS (all_day / all_week / all_month).
    period_changed = Signal(str)
    #: El usuario pidió refrescar el catálogo ahora.
    refresh_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("WaveformPanel")
        self.setFrameShape(QFrame.NoFrame)

        self._stations: list = []
        self._quakes: list = []
        self._current_quake_id: Optional[str] = None
        self._current_latlon: Optional[tuple] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # ── Barra de frescura: periodo + refrescar + última actualización ──
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self._lbl_period = QLabel(t("events.period"))
        bar.addWidget(self._lbl_period)
        self.period_combo = QComboBox()
        for key in ("all_day", "all_week", "all_month"):
            self.period_combo.addItem(key, userData=key)
        self.period_combo.currentIndexChanged.connect(self._on_period_changed)
        bar.addWidget(self.period_combo)
        self.refresh_btn = QPushButton(t("events.refresh"))
        self.refresh_btn.clicked.connect(self.refresh_requested.emit)
        bar.addWidget(self.refresh_btn)
        # ☆ Favoritear el evento seleccionado (alternativa al click-derecho del
        # globo, que QWebEngine suele interceptar).
        self.fav_event_btn = QPushButton(t("events.fav_event"))
        self.fav_event_btn.clicked.connect(self._on_fav_event)
        bar.addWidget(self.fav_event_btn)
        bar.addStretch(1)
        self._updated_lbl = QLabel("")
        self._updated_lbl.setObjectName("Caption")
        bar.addWidget(self._updated_lbl)
        root.addLayout(bar)

        splitter = QSplitter(Qt.Horizontal, parent=self)

        # ── Izquierda: catálogo de eventos ──
        self.event_list = EventListPanel(parent=splitter)
        self.event_list.event_selected.connect(self._on_event_selected)
        # Clic simple → listar estaciones cercanas (elegir a mano).
        # Doble clic → revisar YA con la estación MÁS cercana (atajo, igual que
        # la lista del Workbench), sin tener que pasar por la tabla de estaciones.
        self.event_list.event_activated.connect(self._on_event_activated)
        splitter.addWidget(self.event_list)

        # ── Derecha: estaciones cercanas al evento seleccionado ──
        right = QWidget(splitter)
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(0, 0, 0, 0)
        right_l.setSpacing(6)

        sta_hdr = QHBoxLayout()
        self._sta_header = QLabel(t("events.nearest_title"))
        self._sta_header.setObjectName("SectionTitle")
        sta_hdr.addWidget(self._sta_header, stretch=1)
        self.fav_station_btn = QPushButton(t("events.fav_station"))
        self.fav_station_btn.clicked.connect(self._on_fav_station)
        sta_hdr.addWidget(self.fav_station_btn)
        right_l.addLayout(sta_hdr)
        self._sta_hint = QLabel(t("events.nearest_hint"))
        self._sta_hint.setObjectName("Caption")
        self._sta_hint.setWordWrap(True)
        right_l.addWidget(self._sta_hint)

        self._sta_table = QTableWidget(0, 4)
        self._sta_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._sta_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._sta_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._sta_table.verticalHeader().setVisible(False)
        self._sta_table.horizontalHeader().setStretchLastSection(True)
        self._sta_table.itemDoubleClicked.connect(self._on_station_activated)
        self._sta_table.itemSelectionChanged.connect(self._refresh_fav_labels)
        right_l.addWidget(self._sta_table, stretch=1)
        splitter.addWidget(right)

        splitter.setStretchFactor(0, 62)
        splitter.setStretchFactor(1, 38)
        # stretch=1: el splitter (tablas) ocupa TODO el alto restante; antes
        # quedaba a su tamaño mínimo con un gran hueco vacío arriba.
        root.addWidget(splitter, stretch=1)

        self._apply_headers()
        self._apply_period_texts()
        subscribe(self, LocaleService.language_changed_signal(),
                  self._retranslate)

    # ------------------------------------------------------------------
    def _on_period_changed(self, _idx: int) -> None:
        self.period_changed.emit(self.period_combo.currentData() or "all_day")

    def set_last_updated(self) -> None:
        """Marca la hora de la última actualización del catálogo (local)."""

        from datetime import datetime
        self._updated_lbl.setText(
            t("events.updated", time=datetime.now().strftime("%H:%M:%S")))

    def _apply_period_texts(self) -> None:
        labels = {
            "all_day": t("events.period_day"),
            "all_week": t("events.period_week"),
            "all_month": t("events.period_month"),
        }
        self.period_combo.blockSignals(True)
        for i in range(self.period_combo.count()):
            self.period_combo.setItemText(
                i, labels.get(self.period_combo.itemData(i), ""))
        self.period_combo.blockSignals(False)

    def set_events(self, quakes) -> None:
        # Guardar el catálogo ANTES de poblar la tabla: rellenarla podría
        # disparar event_selected y _on_event_selected lo necesita.
        self._quakes = list(quakes)
        self.event_list.set_events(quakes)

    def set_stations(self, stations) -> None:
        # Solo estaciones con coordenadas válidas Y **reproducibles**: la
        # revisión descarga del archivo IRIS dataselect, que sirve las redes
        # profesionales (IU/US…), NO las Raspberry Shake (AM). Por eso filtramos
        # a provider="usgs": recomendar un AM que no se puede descargar engaña.
        # Dedup por (red, código): el catálogo IRIS puede traer la misma
        # estación repetida (varias épocas/canales) → no duplicar filas.
        seen = set()
        self._stations = []
        for s in stations:
            if (getattr(s, "latitude", None) is None
                    or getattr(s, "longitude", None) is None
                    or getattr(s, "provider", "") != "usgs"):
                continue
            key = (s.network, s.code)
            if key in seen:
                continue
            seen.add(key)
            self._stations.append(s)
        # Si ya hay un evento seleccionado, recomputar.
        if self._current_latlon is not None:
            self._refresh_nearest()

    def _on_event_selected(self, quake_id: str) -> None:
        self._current_quake_id = quake_id
        q = next((x for x in getattr(self, "_quakes", []) if x.id == quake_id),
                 None)
        self._current_latlon = (q.latitude, q.longitude) if q else None
        self._refresh_nearest()
        self._refresh_fav_labels()

    def _on_event_activated(self, quake_id: str) -> None:
        """Doble clic en un evento → revisar con la estación más cercana."""

        q = next((x for x in self._quakes if x.id == quake_id), None)
        if q is None or not self._stations:
            return
        rows = nearest_stations(q.latitude, q.longitude, self._stations, k=1)
        if rows:
            self.review_requested.emit(quake_id, rows[0][0])

    def _refresh_nearest(self) -> None:
        self._sta_table.setRowCount(0)
        if self._current_latlon is None or not self._stations:
            return
        lat, lon = self._current_latlon
        rows = nearest_stations(lat, lon, self._stations, k=8)
        self._sta_table.setRowCount(len(rows))
        for r, (s, dist) in enumerate(rows):
            code_item = QTableWidgetItem(f"{s.network}.{s.code}")
            code_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            code_item.setData(Qt.UserRole + 1, s)        # guardamos la estación
            dist_item = _NumericItem(f"{dist:.1f}", dist)
            km = dist * 111.195
            km_item = _NumericItem(f"{km:,.0f}", km)
            cat_item = QTableWidgetItem(_distance_category(dist))
            cat_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self._sta_table.setItem(r, 0, code_item)
            self._sta_table.setItem(r, 1, dist_item)
            self._sta_table.setItem(r, 2, km_item)
            self._sta_table.setItem(r, 3, cat_item)

    def _on_fav_event(self) -> None:
        """Añade/quita de favoritos el sismo seleccionado."""

        q = next((x for x in self._quakes
                  if x.id == self._current_quake_id), None)
        if q is None:
            return
        if FavoritesStore.is_favorite_event(q.id):
            FavoritesStore.remove_event(q.id)
        else:
            FavoritesStore.add_event(
                id=q.id, magnitude=float(q.magnitude), place=q.place or "",
                timestamp_unix=float(q.timestamp_unix),
                latitude=float(q.latitude), longitude=float(q.longitude),
                depth_km=float(q.depth_km))
        self._refresh_fav_labels()

    def _on_fav_station(self) -> None:
        """Añade/quita de favoritos la estación cercana seleccionada."""

        row = self._sta_table.currentRow()
        if row < 0:
            return
        code_item = self._sta_table.item(row, 0)
        s = code_item.data(Qt.UserRole + 1) if code_item else None
        if s is None:
            return
        if FavoritesStore.is_favorite_station(s.network, s.code):
            FavoritesStore.remove_station(s.network, s.code)
        else:
            FavoritesStore.add_station(
                s.network, s.code, site_name=getattr(s, "site_name", "") or "",
                provider=getattr(s, "provider", "") or "")
        self._refresh_fav_labels()

    def _refresh_fav_labels(self) -> None:
        """Refleja en los botones si lo seleccionado ya es favorito."""

        q = next((x for x in self._quakes
                  if x.id == self._current_quake_id), None)
        ev_fav = bool(q and FavoritesStore.is_favorite_event(q.id))
        self.fav_event_btn.setText(
            t("events.unfav_event") if ev_fav else t("events.fav_event"))
        st_fav = False
        row = self._sta_table.currentRow()
        if row >= 0:
            it = self._sta_table.item(row, 0)
            s = it.data(Qt.UserRole + 1) if it else None
            st_fav = bool(s and FavoritesStore.is_favorite_station(
                s.network, s.code))
        self.fav_station_btn.setText(
            t("events.unfav_station") if st_fav else t("events.fav_station"))

    def _on_station_activated(self, item: QTableWidgetItem) -> None:
        if self._current_quake_id is None:
            return
        code_item = self._sta_table.item(item.row(), 0)
        if code_item is None:
            return
        station = code_item.data(Qt.UserRole + 1)
        if station is not None:
            self.review_requested.emit(self._current_quake_id, station)

    # ------------------------------------------------------------------
    def _apply_headers(self) -> None:
        self._sta_table.setHorizontalHeaderLabels([
            t("events.col_station"), t("events.col_dist"),
            t("events.col_km"), t("events.col_category"),
        ])
        self._sta_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents)

    def _retranslate(self) -> None:
        self._sta_header.setText(t("events.nearest_title"))
        self._sta_hint.setText(t("events.nearest_hint"))
        self._lbl_period.setText(t("events.period"))
        self.refresh_btn.setText(t("events.refresh"))
        self._apply_period_texts()
        self._apply_headers()
        self._refresh_fav_labels()
