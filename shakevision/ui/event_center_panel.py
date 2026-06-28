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
from shakevision.processing.event_filter import filter_quakes
from shakevision.processing.magnitude_color import magnitude_scale_legend
from shakevision.processing.measurements import great_circle_degrees
from shakevision.services.favorites_store import FavoritesStore
from shakevision.ui.combo_utils import fit_combo
from shakevision.ui.event_filter_bar import EventFilterBar
from shakevision.ui.event_list_panel import _MAX_ROWS, EventListPanel, _NumericItem
from shakevision.ui.historical_search_bar import HistoricalSearchBar
from shakevision.ui.icons import get_icon
from shakevision.ui.signal_safety import subscribe

#: Modos del Centro de eventos.
MODE_LIVE = 0
MODE_REPLAY = 1   # "histórico" (consulta fdsnws-event)

#: Centinela para distinguir "no cacheado" de "cacheado como None".
_MISSING = object()

#: Tope de eventos para construir el índice de búsqueda LOCALIZADO (geocod.
#: inversa + FE por evento). Por encima, la búsqueda cae a ``place`` EN para no
#: bloquear la UI con el feed all_month (miles de eventos).
LOCALIZED_SEARCH_MAX = 2500


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

    #: (quake_obj, station_obj) al elegir una estación para revisar el evento.
    #: Emitimos el Earthquake COMPLETO (no solo el id) para que funcione también
    #: con eventos HISTÓRICOS (fdsnws), que no están en el feed en vivo y por
    #: tanto ``main_window._find_quake`` no los encontraría.
    review_requested = Signal(object, object)
    #: Cambió la ventana del feed USGS (all_day / all_week / all_month).
    period_changed = Signal(str)
    #: El usuario pidió refrescar el catálogo ahora.
    refresh_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("WaveformPanel")
        self.setFrameShape(QFrame.NoFrame)

        self._stations: list = []
        self._all_quakes: list = []   # dataset activo (sin filtrar)
        self._quakes: list = []       # lo que se MUESTRA (tras filtros)
        self._live_quakes: list = []  # último feed en vivo
        self._hist_quakes: list = []  # último resultado histórico
        self._search_index = None     # id → campos buscables localizados (lazy)
        self._cat_cache: dict = {}    # id → (etiqueta, Δ°) cacheado (rendimiento)
        self._worker = None           # FDSNQueryWorker (lazy)
        self._current_quake_id: Optional[str] = None
        self._current_latlon: Optional[tuple] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # ── Conmutador de modo: En vivo / Histórico ──
        self._mode = MODE_LIVE
        mode_row = QHBoxLayout()
        mode_row.setSpacing(0)
        self._btn_live = QPushButton(t("hist.mode_live"))
        self._btn_hist = QPushButton(t("hist.mode_historical"))
        for b in (self._btn_live, self._btn_hist):
            b.setCheckable(True)
            b.setObjectName("SegmentButton")
        self._btn_live.setChecked(True)
        self._btn_live.clicked.connect(lambda: self.set_mode(MODE_LIVE))
        self._btn_hist.clicked.connect(lambda: self.set_mode(MODE_REPLAY))
        mode_row.addWidget(self._btn_live)
        mode_row.addWidget(self._btn_hist)
        mode_row.addStretch(1)
        # ☆ Favoritear el evento seleccionado — visible en AMBOS modos (antes
        # vivía en la barra "en vivo" y desaparecía en histórico).
        self.fav_event_btn = QPushButton(t("events.fav_event"))
        self.fav_event_btn.clicked.connect(self._on_fav_event)
        mode_row.addWidget(self.fav_event_btn)
        root.addLayout(mode_row)

        # ── Barra de frescura: periodo + refrescar + última actualización ──
        self._live_bar = QWidget()
        bar = QHBoxLayout(self._live_bar)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(8)
        self._lbl_period = QLabel(t("events.period"))
        bar.addWidget(self._lbl_period)
        self.period_combo = QComboBox()
        for key in ("all_day", "all_week", "all_month"):
            self.period_combo.addItem(key, userData=key)
        self.period_combo.currentIndexChanged.connect(self._on_period_changed)
        fit_combo(self.period_combo, i18n_keys=[
            "events.period_day", "events.period_week", "events.period_month"])
        bar.addWidget(self.period_combo)
        self.refresh_btn = QPushButton(t("events.refresh"))
        self.refresh_btn.clicked.connect(self.refresh_requested.emit)
        bar.addWidget(self.refresh_btn)
        bar.addStretch(1)
        self._updated_lbl = QLabel("")
        self._updated_lbl.setObjectName("Caption")
        bar.addWidget(self._updated_lbl)
        root.addWidget(self._live_bar)

        # ── Barra de filtros (modo vivo): magnitud · tiempo · búsqueda ──
        # Sin botón "Restablecer" (causaba confusión / recargas pesadas). El
        # histórico ofrece "Limpiar" en su propia barra.
        self.filter_bar = EventFilterBar(parent=self, show_reset=False)
        self.filter_bar.filter_changed.connect(self._apply_filters)
        root.addWidget(self.filter_bar)

        # ── Barra de búsqueda histórica (oculta hasta cambiar de modo) ──
        self.hist_bar = HistoricalSearchBar(parent=self)
        self.hist_bar.search_requested.connect(self._on_historical_search)
        self.hist_bar.clear_requested.connect(self._on_hist_clear)
        self.hist_bar.setVisible(False)
        root.addWidget(self.hist_bar)

        # ── Leyenda de color por magnitud ──
        root.addWidget(self._build_mag_legend())

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
        self._sta_table.setAlternatingRowColors(True)
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
        # v0.8.0: iconos ★ vectoriales se recolorean al cambiar de tema.
        from shakevision.ui.theme_manager import ThemeManager as _TM
        subscribe(self, _TM.changed_signal(), self._refresh_fav_labels)
        self._refresh_fav_labels()

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
        # Feed en vivo. Guardamos el snapshot y, si estamos en modo vivo, lo
        # mostramos (filtrado). En modo histórico no pisamos la tabla.
        self._live_quakes = list(quakes)
        if self._mode == MODE_LIVE:
            self._all_quakes = self._live_quakes
            self._search_index = None
            self._update_time_bounds()
            self._apply_filters()

    # ------------------------------------------------------------------
    # Conmutación de modo + búsqueda histórica
    # ------------------------------------------------------------------
    def set_mode(self, mode: int) -> None:
        """Cambia entre En vivo (feed) e Histórico (consulta fdsnws)."""

        self._mode = mode
        is_live = (mode == MODE_LIVE)
        self._btn_live.setChecked(is_live)
        self._btn_hist.setChecked(not is_live)
        self._live_bar.setVisible(is_live)      # selector de periodo: solo vivo
        self.hist_bar.setVisible(not is_live)   # consulta servidor: solo histór.
        # La barra de filtro CLIENTE (palabra clave / magnitud / profundidad) se
        # mantiene en AMBOS modos: así el histórico también tiene búsqueda por
        # texto y el refinado es consistente entre vivo e histórico.
        self.filter_bar.setVisible(True)
        # Cambiar de modo descarta la selección previa: si no, el panel de
        # estaciones cercanas seguía mostrando las del último evento en vivo al
        # entrar en histórico ("aparecían台站 sin haber buscado").
        self._clear_selection()
        # El dataset activo cambia de fuente según el modo; el refinado cliente
        # (_apply_filters) es el MISMO en los dos.
        self._all_quakes = self._live_quakes if is_live else self._hist_quakes
        self._search_index = None
        self._update_time_bounds()
        self._apply_filters()

    def _clear_selection(self) -> None:
        """Olvida el evento seleccionado y vacía el panel de cercanas."""

        self._current_quake_id = None
        self._current_latlon = None
        self._sta_table.setRowCount(0)
        self._refresh_fav_labels()

    def _on_hist_clear(self) -> None:
        """"Limpiar" (histórico): vacía los resultados, la selección y los
        filtros cliente, dejando la vista en blanco lista para otra búsqueda. El
        formulario de consulta (tiempo / región / orden) se conserva."""

        self._hist_quakes = []
        self._all_quakes = []
        self._search_index = None
        self._clear_selection()       # también limpia el panel de cercanas
        # filter_bar.reset() limpia palabra clave / magnitud / profundidad y
        # dispara _apply_filters → tabla vacía (porque _all_quakes ya es []).
        self.filter_bar.reset()

    def _ensure_worker(self):
        if self._worker is None:
            from shakevision.services.fdsn_worker import FDSNQueryWorker
            self._worker = FDSNQueryWorker(parent=self)
            self._worker.results.connect(self._on_hist_results)
            self._worker.failed.connect(self._on_hist_failed)
        return self._worker

    def _on_historical_search(self, params: dict) -> None:
        self.hist_bar.set_searching(True)
        self._ensure_worker().query(params)

    def _on_hist_results(self, quakes) -> None:
        self.hist_bar.set_searching(False)
        self._hist_quakes = list(quakes)
        if self._mode == MODE_REPLAY:
            # Mismo refinado cliente que en vivo (palabra clave / mag / prof.).
            self._all_quakes = self._hist_quakes
            self._search_index = None
            self._update_time_bounds()
            self._apply_filters()

    def _on_hist_failed(self, message: str, too_many: bool) -> None:
        self.hist_bar.set_searching(False)
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.warning(self, t("hist.mode_historical"), message)

    def _build_mag_legend(self):
        from PySide6.QtGui import QColor, QPixmap
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        cap = QLabel(t("events.col_mag"))
        cap.setObjectName("Caption")
        lay.addWidget(cap)
        self._legend_labels = []
        for hex_color, key in magnitude_scale_legend():
            sw = QLabel()
            pm = QPixmap(12, 12)
            pm.fill(QColor(hex_color))
            sw.setPixmap(pm)
            lay.addWidget(sw)
            lbl = QLabel(t(key))
            lbl.setObjectName("Caption")
            self._legend_labels.append((lbl, key))
            lay.addWidget(lbl)
        lay.addStretch(1)
        return w

    def _ensure_search_index(self) -> dict:
        """Mapa ``id → [campos buscables localizados]`` (perezoso, cacheado).

        Solo se construye cuando hay texto de búsqueda, para no pagar el coste
        de geocodificación inversa / FE cuando el usuario no busca. Se invalida
        al cambiar el catálogo (``set_events``) o el idioma (``_retranslate``).
        """

        if getattr(self, "_search_index", None) is None:
            from shakevision.processing.event_filter import structured_tokens
            from shakevision.services.geo_region import search_fields_for
            loc = LocaleService.current_language() or "en"
            self._search_index = {
                q.id: (
                    search_fields_for(
                        q.latitude, q.longitude, loc, place=q.place or "")
                    + structured_tokens(
                        eventid=q.id, magnitude=q.magnitude,
                        timestamp_unix=q.timestamp_unix, depth_km=q.depth_km)
                )
                for q in self._all_quakes
            }
        return self._search_index

    def _apply_filters(self) -> None:
        """Aplica los filtros de la barra al catálogo y repuebla la tabla."""

        t_from, t_to = self.filter_bar.time_range()
        min_depth, max_depth = self.filter_bar.depth_range()
        query = self.filter_bar.query()
        # Búsqueda multilingüe: solo resolvemos campos localizados si hay texto
        # Y el dataset no es enorme. Construir el índice (geocodificación inversa
        # + FE por evento) sobre los ~miles del feed all_month congelaría la UI;
        # en ese caso caemos a búsqueda por ``place`` EN (rápida, sin geo).
        extra_text = None
        if query.strip() and len(self._all_quakes) <= LOCALIZED_SEARCH_MAX:
            idx = self._ensure_search_index()
            extra_text = lambda ev: idx.get(ev.id, (ev.place or "",))  # noqa: E731
        filtered = filter_quakes(
            self._all_quakes,
            min_mag=self.filter_bar.min_mag(),
            min_depth=min_depth, max_depth=max_depth,
            t_from=t_from, t_to=t_to,
            query=query,
            extra_text=extra_text,
        )
        # _quakes = lo mostrado: _on_event_selected / favoritos lo usan.
        self._quakes = filtered
        self._render(filtered)
        self.filter_bar.set_count(len(filtered), len(self._all_quakes))

    def _min_station_dist_deg(self, lat: float, lon: float):
        """Δ° a la estación más cercana — O(M) (solo el mínimo, sin ordenar)."""

        best = None
        for s in self._stations:
            slat = getattr(s, "latitude", None)
            slon = getattr(s, "longitude", None)
            if slat is None or slon is None:
                continue
            d = great_circle_degrees(lat, lon, slat, slon)
            if best is None or d < best:
                best = d
        return best

    def _categories_for(self, quakes) -> dict:
        """``{id: (etiqueta, Δ°)}`` con la categoría de distancia a la estación
        más cercana. Cacheado por id (se invalida al cambiar de estaciones);
        sin caché, recomputarlo en cada filtrado/reset sobre miles de eventos
        del feed ``all_month`` congelaba la UI."""

        if not self._stations:
            return {}
        out = {}
        for q in quakes:
            cached = self._cat_cache.get(q.id, _MISSING)
            if cached is _MISSING:
                dist = self._min_station_dist_deg(q.latitude, q.longitude)
                cached = ((_distance_category(dist), dist)
                          if dist is not None else None)
                self._cat_cache[q.id] = cached
            if cached is not None:
                out[q.id] = cached
        return out

    def _render(self, quakes) -> None:
        """Pinta la tabla con la columna de categoría de distancia rellena.

        Solo calculamos categorías para las filas que se PINTARÁN (las más
        recientes hasta el tope), no para los miles filtrados — así el reset
        sobre el feed all_month no recorre todo el catálogo."""

        shown = sorted(
            quakes, key=lambda q: q.timestamp_unix, reverse=True)[:_MAX_ROWS]
        self.event_list.set_events(quakes, self._categories_for(shown))

    def _update_time_bounds(self) -> None:
        """Ajusta el rango del slider temporal al span del dataset activo."""

        if not self._all_quakes:
            return
        ts = [q.timestamp_unix for q in self._all_quakes]
        self.filter_bar.set_time_bounds(min(ts), max(ts))

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
        # Cambió el catálogo de estaciones → la estación más cercana de cada
        # evento puede cambiar: invalidar la caché de categorías.
        self._cat_cache = {}
        # Si ya hay un evento seleccionado, recomputar el panel de cercanas.
        if self._current_latlon is not None:
            self._refresh_nearest()
        # Las estaciones acaban de llegar/cambiar → rellenar la columna de
        # categoría de distancia de la tabla (antes podía estar en "—").
        if self._quakes:
            self._render(self._quakes)

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
            self.review_requested.emit(q, rows[0][0])

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

    def _bound_station(self):
        """Estación ENLAZADA al evento: la SELECCIONADA en la tabla de
        cercanas, o la más cercana si no hay selección. ``None`` si no hay
        catálogo de estaciones."""

        row = self._sta_table.currentRow()
        if row >= 0:
            it = self._sta_table.item(row, 0)
            s = it.data(Qt.UserRole + 1) if it else None
            if s is not None:
                return s
        if self._current_latlon and self._stations:
            rows = nearest_stations(
                self._current_latlon[0], self._current_latlon[1],
                self._stations, k=1)
            if rows:
                return rows[0][0]
        return None

    def _on_fav_event(self) -> None:
        """Añade/quita de favoritos el sismo seleccionado.

        Al AÑADIR, también enlaza y favoritea la estación relacionada (la
        seleccionada o la más cercana): evento y estación van juntos, y el
        favorito recuerda con QUÉ estación revisarlo."""

        q = next((x for x in self._quakes
                  if x.id == self._current_quake_id), None)
        if q is None:
            return
        if FavoritesStore.is_favorite_event(q.id):
            FavoritesStore.remove_event(q.id)
        else:
            st = self._bound_station()
            net = getattr(st, "network", "") if st is not None else ""
            code = getattr(st, "code", "") if st is not None else ""
            FavoritesStore.add_event(
                id=q.id, magnitude=float(q.magnitude), place=q.place or "",
                timestamp_unix=float(q.timestamp_unix),
                latitude=float(q.latitude), longitude=float(q.longitude),
                depth_km=float(q.depth_km),
                network=net, station=code)
            # Añadir también la estación enlazada a favoritos (si la hay).
            if st is not None and net and code:
                FavoritesStore.add_station(
                    net, code, site_name=getattr(st, "site_name", "") or "",
                    provider=getattr(st, "provider", "") or "")
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

        from shakevision.ui.theme_manager import ThemeManager as _TM
        try:
            th = _TM.current_theme()
        except Exception:  # noqa: BLE001
            th = "dark"
        self.refresh_btn.setIcon(get_icon("refresh", theme=th))
        q = next((x for x in self._quakes
                  if x.id == self._current_quake_id), None)
        ev_fav = bool(q and FavoritesStore.is_favorite_event(q.id))
        self.fav_event_btn.setText(
            t("events.unfav_event") if ev_fav else t("events.fav_event"))
        self.fav_event_btn.setIcon(
            get_icon("star_fill" if ev_fav else "star", theme=th))
        st_fav = False
        row = self._sta_table.currentRow()
        if row >= 0:
            it = self._sta_table.item(row, 0)
            s = it.data(Qt.UserRole + 1) if it else None
            st_fav = bool(s and FavoritesStore.is_favorite_station(
                s.network, s.code))
        self.fav_station_btn.setText(
            t("events.unfav_station") if st_fav else t("events.fav_station"))
        self.fav_station_btn.setIcon(
            get_icon("star_fill" if st_fav else "star", theme=th))

    def _on_station_activated(self, item: QTableWidgetItem) -> None:
        if self._current_quake_id is None:
            return
        code_item = self._sta_table.item(item.row(), 0)
        if code_item is None:
            return
        station = code_item.data(Qt.UserRole + 1)
        q = next((x for x in self._quakes
                  if x.id == self._current_quake_id), None)
        if station is not None and q is not None:
            self.review_requested.emit(q, station)

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
        self._btn_live.setText(t("hist.mode_live"))
        self._btn_hist.setText(t("hist.mode_historical"))
        for lbl, key in getattr(self, "_legend_labels", []):
            try:
                lbl.setText(t(key))
            except RuntimeError:
                pass
        # El idioma cambió → los nombres de país localizados también; rehacer
        # el índice de búsqueda en el próximo filtrado.
        self._search_index = None
