"""
Panel de control lateral.

Agrupa los selectores y deslizadores que el usuario manipulará para:
  - Cambiar de estación en caliente.
  - Ajustar la banda del filtro Butterworth.
  - Configurar los parámetros del detector STA/LTA.

El panel emite señales Qt cuando el usuario cambia un valor; la
ventana principal se encarga de propagar esos cambios al resto de la
aplicación (fuente de datos, procesador, etc.).
"""

from __future__ import annotations

from collections import deque
from typing import Iterable, Optional

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from shakevision.config import (
    AppConfig,
    FilterConfig,
    StationPreset,
    TriggerConfig,
)
from shakevision.i18n import LocaleService, t
from shakevision.processing.sonifier import (
    DEFAULT_SPEED_FACTOR,
    MAX_SPEED_FACTOR,
    MIN_SPEED_FACTOR,
    estimate_audio_duration_s,
)
from shakevision.services.shake_presets import (
    LanShakePreset,
    ShakePresetStore,
)
from shakevision.ui.signal_safety import subscribe


# Identificador interno del item "+ Add LAN Shake..." en el combo.
# Lo usamos como userData para distinguirlo de los presets reales en
# ``_on_station_changed`` y evitar emitir station_changed con datos basura.
_ADD_LAN_SHAKE_SENTINEL = object()


class ControlPanel(QFrame):
    """Panel lateral con todos los controles del usuario."""

    # Señales emitidas a la ventana principal
    station_changed = Signal(object)         # StationPreset
    filter_changed = Signal(object)          # FilterConfig
    trigger_changed = Signal(object)         # TriggerConfig
    connect_clicked = Signal()               # Solicita iniciar la fuente
    disconnect_clicked = Signal()            # Solicita detener la fuente
    listen_clicked = Signal(int, int)        # (seconds_to_play, speed_factor)

    # Máximo de estaciones añadidas dinámicamente desde el globo. Los
    # presets que vienen de AppConfig (Demo + LAN Shake) están EXENTOS
    # de este límite — se preservan siempre en la parte alta del combo.
    MAX_DYNAMIC_STATIONS: int = 8

    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # Identificador para que la hoja de estilo lo seleccione
        self.setObjectName("ControlPanel")
        self.setFrameShape(QFrame.NoFrame)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.setFixedWidth(300)

        # Guardar referencia a la configuración (clonada para evitar
        # alterar la global hasta que el usuario "aplique")
        self._config = config

        # Cola FIFO de estaciones añadidas dinámicamente desde el globo.
        # Almacenamos el preset (no el índice) para resistir cambios en
        # el orden del combo. ``deque`` con maxlen N hace pop automático
        # cuando se inserta el N+1; aquí lo gestionamos a mano para
        # eliminar también la entrada correspondiente del combo.
        self._dynamic_stations: deque = deque()

        # ¿Hay una fuente de datos activa (conectando o en streaming)?
        # Lo mantiene sincronizado el WorkbenchController. Cuando es True,
        # añadir una estación NO debe cambiar la selección del combo (eso
        # interrumpiría/reconectaría el stream en curso): la estación solo
        # se agrega a la lista y el usuario decide cuándo cambiarse.
        self._source_active: bool = False

        # Secciones colapsables registradas (header, title_key, content).
        self._collapsibles: list = []

        # v0.7.7: TODO el contenido va dentro de un QScrollArea. Antes el
        # layout se ponía directo sobre el panel; al expandir varias secciones
        # el contenido excedía la altura de la ventana y Qt COMPRIMÍA los
        # widgets por debajo de su tamaño natural → las cabeceras de las
        # secciones colapsables salían recortadas. Con scroll, si sobra altura
        # aparece una barra y no se recorta nada.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.viewport().setStyleSheet("background: transparent;")
        outer.addWidget(scroll)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        scroll.setWidget(content)

        # Construir la interfaz por secciones (dentro del contenido scrollable)
        root = QVBoxLayout(content)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        # Conexión + estación: SIEMPRE visibles (el flujo principal).
        root.addLayout(self._build_station_section(config.stations))
        root.addLayout(self._build_connection_section())
        # Filtro / detector / sonido: colapsables (v0.7.7) para que el panel
        # no crezca sin límite. Sonido va colapsado por defecto (degradado:
        # es una función de divulgación, no de análisis).
        root.addWidget(self._collapsible(
            "controls.section.filter",
            self._wrap(self._build_filter_section(config.filt)),
            collapsed=False))
        root.addWidget(self._collapsible(
            "controls.section.trigger",
            self._wrap(self._build_trigger_section(config.trigger)),
            collapsed=True))
        root.addWidget(self._collapsible(
            "controls.section.sound",
            self._wrap(self._build_sound_section(config.stream.sample_rate_hz)),
            collapsed=True))
        root.addStretch(1)

        # Aplicar textos traducidos + suscribirse a cambios de idioma
        self._retranslate()
        subscribe(self, LocaleService.language_changed_signal(),
                  self._retranslate)  # v0.7.7 (B1)

    # ------------------------------------------------------------------
    # Construcción de secciones
    # ------------------------------------------------------------------
    def _build_station_section(self, stations: Iterable[StationPreset]) -> QVBoxLayout:
        """Selector de estación y campos de texto auxiliares."""

        layout = QVBoxLayout()
        layout.setSpacing(6)
        self._station_section_title = self._section_title("")
        layout.addWidget(self._station_section_title)

        self.station_combo = QComboBox()
        for s in stations:
            # Guardar el preset entero en userData para recuperarlo al cambiar
            self.station_combo.addItem(s.label, userData=s)
        # Cargar Shakes LAN guardados (v0.3.0) — vienen del store y
        # entran como dinámicos para que cuenten en el FIFO de 8.
        for lan in ShakePresetStore.all():
            self._add_lan_shake_to_combo(lan)
        # ── Sentinela "+ Add LAN Shake..." al final ──
        self._add_lan_sentinel_to_combo()
        self.station_combo.currentIndexChanged.connect(self._on_station_changed)
        layout.addWidget(self.station_combo)

        # Información detallada del preset seleccionado
        self.station_detail = QLabel()
        self.station_detail.setObjectName("StatusValue")
        self.station_detail.setWordWrap(True)
        layout.addWidget(self.station_detail)

        # Mostrar el detalle inicial
        self._refresh_station_detail()

        # Suscripción al store: cambios externos (Settings → My Shakes,
        # otra ventana, etc.) deben reflejarse aquí inmediatamente.
        subscribe(self, ShakePresetStore.changed_signal(),
                  self._refresh_lan_shakes_from_store)  # v0.7.7 (B1)

        return layout

    # Marcos del spinner de conexión (braille — gira suave, sin assets).
    _SPINNER_FRAMES: str = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def _build_connection_section(self) -> QVBoxLayout:
        """Botones de conexión/desconexión + fila de progreso en vivo."""

        outer = QVBoxLayout()
        outer.setSpacing(6)

        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        self.connect_button = QPushButton()
        self.connect_button.clicked.connect(self.connect_clicked.emit)
        buttons.addWidget(self.connect_button)

        self.disconnect_button = QPushButton()
        self.disconnect_button.clicked.connect(self.disconnect_clicked.emit)
        buttons.addWidget(self.disconnect_button)
        outer.addLayout(buttons)

        # v0.7.7: fila de progreso de conexión (spinner + estado en vivo).
        # Oculta mientras estamos desconectados; el WorkbenchController la
        # alimenta con los mensajes de estado de la fuente (DNS, handshake,
        # SELECT, esperando datos, streaming…).
        self._conn_row = QWidget()
        row = QHBoxLayout(self._conn_row)
        row.setContentsMargins(0, 2, 0, 0)
        row.setSpacing(6)
        self._conn_spinner = QLabel(self._SPINNER_FRAMES[0])
        self._conn_spinner.setObjectName("ConnSpinner")
        self._conn_spinner.setFixedWidth(14)
        self._conn_spinner.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        row.addWidget(self._conn_spinner)
        self._conn_status = QLabel("")
        self._conn_status.setObjectName("StatusValue")
        self._conn_status.setWordWrap(True)
        row.addWidget(self._conn_status, stretch=1)
        self._conn_row.setVisible(False)
        outer.addWidget(self._conn_row)

        # Temporizador del spinner.
        self._spinner_idx = 0
        self._conn_spinner_timer = QTimer(self)
        self._conn_spinner_timer.setInterval(90)
        self._conn_spinner_timer.timeout.connect(self._tick_spinner)

        return outer

    # ------------------------------------------------------------------
    # Visualización del progreso de conexión (v0.7.7)
    # ------------------------------------------------------------------
    def _tick_spinner(self) -> None:
        self._spinner_idx = (self._spinner_idx + 1) % len(self._SPINNER_FRAMES)
        self._conn_spinner.setText(self._SPINNER_FRAMES[self._spinner_idx])

    def set_connection_status(self, text: str, busy: bool = True) -> None:
        """Muestra ``text`` en la fila de progreso.

        ``busy=True`` anima el spinner (conectando / esperando datos);
        ``busy=False`` lo detiene y oculta (estado estable: streaming,
        error) dejando el texto visible.
        """

        self._conn_status.setText(text)
        self._conn_row.setVisible(True)
        if busy:
            self._conn_spinner.setVisible(True)
            if not self._conn_spinner_timer.isActive():
                self._conn_spinner_timer.start()
        else:
            self._conn_spinner_timer.stop()
            self._conn_spinner.setVisible(False)

    def set_source_active(self, active: bool) -> None:
        """El controlador informa si hay una fuente activa.

        Cuando hay una fuente activa, ``append_dynamic_station`` agrega la
        estación a la lista pero NO cambia la selección, para no interrumpir
        ni reconectar el stream en curso (ver la nota en ``__init__``).
        """

        self._source_active = bool(active)

    def clear_connection_status(self) -> None:
        """Oculta la fila de progreso (al desconectar)."""

        self._conn_spinner_timer.stop()
        self._conn_status.clear()
        self._conn_row.setVisible(False)

    def _build_filter_section(self, filt: FilterConfig) -> QVBoxLayout:
        """Controles del filtro Butterworth pasa banda."""

        layout = QVBoxLayout()
        layout.setSpacing(6)

        # Casilla de habilitación (bypass cuando está desmarcada)
        self.filter_enabled_check = QCheckBox()
        self.filter_enabled_check.setChecked(filt.enabled)
        self.filter_enabled_check.toggled.connect(self._on_filter_toggled)
        layout.addWidget(self.filter_enabled_check)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)

        # Frecuencia de corte inferior
        self._lowcut_label = QLabel()
        grid.addWidget(self._lowcut_label, 0, 0)
        self.lowcut_spin = QDoubleSpinBox()
        self.lowcut_spin.setRange(0.01, 49.0)
        self.lowcut_spin.setSingleStep(0.1)
        self.lowcut_spin.setValue(filt.lowcut_hz)
        self.lowcut_spin.valueChanged.connect(self._emit_filter_changed)
        grid.addWidget(self.lowcut_spin, 0, 1)

        # Frecuencia de corte superior
        self._highcut_label = QLabel()
        grid.addWidget(self._highcut_label, 1, 0)
        self.highcut_spin = QDoubleSpinBox()
        self.highcut_spin.setRange(0.1, 50.0)
        self.highcut_spin.setSingleStep(0.5)
        self.highcut_spin.setValue(filt.highcut_hz)
        self.highcut_spin.valueChanged.connect(self._emit_filter_changed)
        grid.addWidget(self.highcut_spin, 1, 1)

        # Orden del filtro
        self._order_label = QLabel()
        grid.addWidget(self._order_label, 2, 0)
        self.order_spin = QSpinBox()
        self.order_spin.setRange(1, 10)
        self.order_spin.setValue(filt.order)
        self.order_spin.valueChanged.connect(self._emit_filter_changed)
        grid.addWidget(self.order_spin, 2, 1)

        layout.addLayout(grid)

        # ── Presets de banda (un clic) ───────────────────────────────
        # Bandas sísmicas típicas: cuerpo P/S, superficiales, regional.
        # Pulsar uno ajusta lowcut/highcut + activa el filtro y reemite.
        self._lbl_filter_presets = QLabel()
        self._lbl_filter_presets.setObjectName("Caption")
        layout.addWidget(self._lbl_filter_presets)

        preset_row = QHBoxLayout()
        preset_row.setSpacing(4)
        self._filter_preset_buttons: list[tuple[QPushButton, str]] = []
        # (clave i18n, lowcut, highcut)  — "off" desactiva el filtro.
        for key, low, high in (
            ("controls.filter.preset_body", 1.0, 10.0),
            ("controls.filter.preset_surface", 0.02, 0.1),
            ("controls.filter.preset_regional", 2.0, 8.0),
            ("controls.filter.preset_off", 0.0, 0.0),
        ):
            btn = QPushButton()
            btn.setObjectName("ToolbarButton")
            btn.setMinimumWidth(44)
            if key == "controls.filter.preset_off":
                btn.clicked.connect(self._on_filter_preset_off)
            else:
                btn.setToolTip(f"{low:g}–{high:g} Hz")
                btn.clicked.connect(
                    lambda _=False, lo=low, hi=high: self._apply_filter_preset(lo, hi))
            preset_row.addWidget(btn)
            self._filter_preset_buttons.append((btn, key))
        preset_row.addStretch(1)
        layout.addLayout(preset_row)

        # Reflejar el estado inicial en los controles dependientes
        self._apply_filter_enabled(filt.enabled)

        return layout

    def _apply_filter_preset(self, low: float, high: float) -> None:
        """Aplica una banda preestablecida: activa el filtro, fija cortes y
        reemite una sola vez."""

        for w in (self.filter_enabled_check, self.lowcut_spin, self.highcut_spin):
            w.blockSignals(True)
        self.filter_enabled_check.setChecked(True)
        self._apply_filter_enabled(True)
        self.lowcut_spin.setValue(low)
        self.highcut_spin.setValue(high)
        for w in (self.filter_enabled_check, self.lowcut_spin, self.highcut_spin):
            w.blockSignals(False)
        self._emit_filter_changed()

    def _on_filter_preset_off(self) -> None:
        """Desactiva el filtro (bypass) — equivale a desmarcar la casilla."""

        self.filter_enabled_check.setChecked(False)  # dispara _on_filter_toggled

    def _build_trigger_section(self, trig: TriggerConfig) -> QVBoxLayout:
        """Controles del detector STA/LTA."""

        layout = QVBoxLayout()
        layout.setSpacing(6)

        # Etiqueta + valor numérico del umbral
        threshold_row = QHBoxLayout()
        self._threshold_label = QLabel()
        threshold_row.addWidget(self._threshold_label)
        self.threshold_value_label = QLabel(f"{trig.threshold_on:.2f}")
        self.threshold_value_label.setObjectName("StatusValue")
        threshold_row.addStretch(1)
        threshold_row.addWidget(self.threshold_value_label)
        layout.addLayout(threshold_row)

        # Slider del umbral de activación (mapeo 0.5–10.0 con 100 pasos)
        self.threshold_slider = QSlider(Qt.Horizontal)
        self.threshold_slider.setRange(50, 1000)  # 0.50 — 10.00 (paso 0.01)
        self.threshold_slider.setValue(int(trig.threshold_on * 100))
        self.threshold_slider.valueChanged.connect(self._on_threshold_slider_changed)
        layout.addWidget(self.threshold_slider)

        # Ventanas STA y LTA
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)

        self._sta_label = QLabel()
        grid.addWidget(self._sta_label, 0, 0)
        self.sta_spin = QDoubleSpinBox()
        self.sta_spin.setRange(0.1, 60.0)
        self.sta_spin.setSingleStep(0.1)
        self.sta_spin.setValue(trig.sta_seconds)
        self.sta_spin.valueChanged.connect(self._emit_trigger_changed)
        grid.addWidget(self.sta_spin, 0, 1)

        self._lta_label = QLabel()
        grid.addWidget(self._lta_label, 1, 0)
        self.lta_spin = QDoubleSpinBox()
        self.lta_spin.setRange(1.0, 600.0)
        self.lta_spin.setSingleStep(1.0)
        self.lta_spin.setValue(trig.lta_seconds)
        self.lta_spin.valueChanged.connect(self._emit_trigger_changed)
        grid.addWidget(self.lta_spin, 1, 1)

        layout.addLayout(grid)
        return layout

    def _build_sound_section(self, sample_rate_hz: int) -> QVBoxLayout:
        """Sección de sonificación: botón + slider de velocidad."""

        # Guardamos la frecuencia de muestreo para calcular la duración
        # estimada del clip en función del slider.
        self._stream_sample_rate = int(sample_rate_hz)
        # Duración fija de la ventana a sonificar (segundos de señal real)
        self._listen_seconds: int = 60

        layout = QVBoxLayout()
        layout.setSpacing(6)

        # Botón principal
        self.listen_button = QPushButton()
        self.listen_button.clicked.connect(self._on_listen_clicked)
        layout.addWidget(self.listen_button)

        # Slider de aceleración
        speed_row = QHBoxLayout()
        self._speed_label = QLabel()
        speed_row.addWidget(self._speed_label)
        self.speed_value_label = QLabel(f"× {DEFAULT_SPEED_FACTOR}")
        self.speed_value_label.setObjectName("StatusValue")
        speed_row.addStretch(1)
        speed_row.addWidget(self.speed_value_label)
        layout.addLayout(speed_row)

        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setRange(MIN_SPEED_FACTOR, MAX_SPEED_FACTOR)
        self.speed_slider.setValue(DEFAULT_SPEED_FACTOR)
        self.speed_slider.valueChanged.connect(self._on_speed_changed)
        layout.addWidget(self.speed_slider)

        # Texto auxiliar con la duración estimada del audio
        self.audio_duration_label = QLabel()
        self.audio_duration_label.setObjectName("StatusValue")
        self.audio_duration_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.audio_duration_label)
        self._refresh_audio_duration_label()

        return layout

    # ------------------------------------------------------------------
    # API pública para el ciclo de vida del botón
    # ------------------------------------------------------------------
    def set_listen_button_enabled(self, enabled: bool, label: str | None = None) -> None:
        """Habilita/deshabilita el botón Escuchar y opcionalmente cambia el texto."""

        self.listen_button.setEnabled(enabled)
        if label is not None:
            self.listen_button.setText(label)
        elif enabled:
            self.listen_button.setText(
                t("controls.sound.listen_button", seconds=self._listen_seconds)
            )

    # ------------------------------------------------------------------
    # Re-traducción
    # ------------------------------------------------------------------
    def _retranslate(self) -> None:
        """Re-aplica los textos traducidos sin reconstruir widgets."""

        self._station_section_title.setText(t("controls.section.station"))
        # Cabeceras de las secciones colapsables (título + chevron).
        for header, title_key, content in self._collapsibles:
            self._apply_collapsible_text(header, title_key, content.isVisible())

        # Re-etiquetar el item sentinela ("+ Add LAN Shake...") tras
        # cambio de idioma. Localizarlo por userData en lugar de índice.
        for i in range(self.station_combo.count()):
            if self.station_combo.itemData(i) is _ADD_LAN_SHAKE_SENTINEL:
                self.station_combo.setItemText(i, t("controls.station.add_lan_shake"))
                break

        self.connect_button.setText(t("controls.connect"))
        self.disconnect_button.setText(t("controls.disconnect"))

        self.filter_enabled_check.setText(t("controls.filter.enable"))
        self._lowcut_label.setText(t("controls.filter.lowcut"))
        self._highcut_label.setText(t("controls.filter.highcut"))
        self._order_label.setText(t("controls.filter.order"))
        self._lbl_filter_presets.setText(t("controls.filter.presets"))
        for btn, key in self._filter_preset_buttons:
            btn.setText(t(key))

        self._threshold_label.setText(t("controls.trigger.threshold"))
        self._sta_label.setText(t("controls.trigger.sta"))
        self._lta_label.setText(t("controls.trigger.lta"))

        self._speed_label.setText(t("controls.sound.speed"))
        # El botón depende de su estado actual; usamos el helper
        if self.listen_button.isEnabled():
            self.listen_button.setText(
                t("controls.sound.listen_button", seconds=self._listen_seconds)
            )
        # Refrescar la duración estimada del audio (formato puede haber cambiado)
        self._refresh_audio_duration_label()

    def append_dynamic_station(self, preset: StationPreset) -> bool:
        """Añade una estación al combo desde una fuente externa (globo).

        Reglas:
          * Si la estación ya está en el combo (por N.S.L.C.) se
            selecciona y se devuelve ``False`` (no se añade duplicado).
          * Si supera ``MAX_DYNAMIC_STATIONS``, se elimina la dinámica
            más antigua antes de insertar la nueva.
          * Los presets que vinieron de la configuración inicial nunca
            se eliminan: el FIFO solo aplica a las dinámicas.
          * Después de añadir, se selecciona automáticamente la nueva
            estación (lo que dispara ``station_changed`` hacia main).
          * **El sentinela "➕ Add LAN Shake…" (introducido en v0.3.0)
            siempre debe quedar en la ÚLTIMA posición.** Insertamos
            la nueva fila *antes* de ese ítem y seleccionamos su
            índice real, nunca ``count - 1`` (que sería el sentinela).

        Devuelve ``True`` si añadió una entrada nueva al combo,
        ``False`` si solo seleccionó una existente.
        """

        # ¿Ya existe? Comparamos por N.S.L (sin canal, el canal Z se
        # asume EHZ por defecto y no debe forzar duplicados).
        # Se hace ``isinstance`` para saltar el sentinel cuyo userData
        # no es un StationPreset (era la causa de un AttributeError
        # silencioso que rompía toda la rutina de añadir estación).
        for i in range(self.station_combo.count()):
            existing = self.station_combo.itemData(i)
            if not isinstance(existing, StationPreset):
                continue
            if (existing.network == preset.network
                    and existing.station == preset.station
                    and existing.location == preset.location):
                # Solo cambiamos de selección si NO hay un stream activo:
                # si lo hay, no interrumpimos la conexión en curso.
                if not self._source_active:
                    self.station_combo.setCurrentIndex(i)
                return False

        # FIFO sobre las dinámicas
        if len(self._dynamic_stations) >= self.MAX_DYNAMIC_STATIONS:
            oldest = self._dynamic_stations.popleft()
            for i in range(self.station_combo.count()):
                d = self.station_combo.itemData(i)
                if d is oldest:
                    self.station_combo.removeItem(i)
                    break

        # Calcular la posición de inserción: justo ANTES del sentinel
        # si existe; si no, al final del combo.
        sentinel_idx = self._sentinel_index()
        insert_idx = sentinel_idx if sentinel_idx >= 0 else self.station_combo.count()
        self.station_combo.insertItem(insert_idx, preset.label, userData=preset)
        self._dynamic_stations.append(preset)
        # Con un stream activo NO auto-seleccionamos la estación nueva: eso
        # dispararía ``station_changed`` → reconexión y cortaría el stream en
        # curso. La estación queda en la lista; el usuario se cambia a ella
        # manualmente cuando quiera (coherente con "pulsa Conectar para
        # empezar" del diálogo de añadir). Sin stream activo sí la dejamos
        # seleccionada para que el próximo Conectar la use.
        if not self._source_active:
            self.station_combo.setCurrentIndex(insert_idx)
        return True

    def _sentinel_index(self) -> int:
        """Devuelve el índice del item '+ Add LAN Shake…' o -1 si falta."""

        for i in range(self.station_combo.count()):
            if self.station_combo.itemData(i) is _ADD_LAN_SHAKE_SENTINEL:
                return i
        return -1

    def dynamic_station_count(self) -> int:
        """Cuántas estaciones dinámicas están actualmente en el combo."""

        return len(self._dynamic_stations)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _section_title(text: str) -> QLabel:
        """Crea una etiqueta con el estilo de "título de sección"."""

        label = QLabel(text)
        label.setObjectName("SectionTitle")
        return label

    # ------------------------------------------------------------------
    # Secciones colapsables (v0.7.7)
    # ------------------------------------------------------------------
    @staticmethod
    def _wrap(layout) -> QWidget:
        """Envuelve un layout en un QWidget (para poder ocultarlo entero)."""

        w = QWidget()
        w.setLayout(layout)
        return w

    def _collapsible(self, title_key: str, content: QWidget,
                     collapsed: bool = False) -> QWidget:
        """Crea una sección con cabecera clicable que muestra/oculta ``content``."""

        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)

        header = QPushButton()
        header.setObjectName("SectionHeader")
        header.setCheckable(True)
        header.setChecked(not collapsed)
        header.setCursor(Qt.PointingHandCursor)
        header.toggled.connect(
            lambda on, c=content, h=header, k=title_key:
            self._on_collapse(on, c, h, k))
        v.addWidget(header)
        v.addWidget(content)

        content.setVisible(not collapsed)
        self._apply_collapsible_text(header, title_key, not collapsed)
        self._collapsibles.append((header, title_key, content))
        return box

    def _on_collapse(self, expanded: bool, content: QWidget,
                     header: QPushButton, title_key: str) -> None:
        content.setVisible(expanded)
        self._apply_collapsible_text(header, title_key, expanded)

    @staticmethod
    def _apply_collapsible_text(header: QPushButton, title_key: str,
                                expanded: bool) -> None:
        chevron = "▾" if expanded else "▸"
        header.setText(f"{chevron}  {t(title_key)}")

    def _refresh_station_detail(self) -> None:
        """Actualiza el texto descriptivo del preset seleccionado.

        Defiende contra el sentinel "➕ Add LAN Shake…" (cuyo userData
        no es un StationPreset) — si por algún camino quedara como
        currentData, se ignora en lugar de provocar AttributeError.
        """

        preset = self.station_combo.currentData()
        if not isinstance(preset, StationPreset):
            self.station_detail.setText("—")
            return
        self.station_detail.setText(
            f"{preset.network}.{preset.station}."
            f"{preset.location or '--'}.{preset.channel}"
        )

    def current_station(self) -> Optional[StationPreset]:
        """Devuelve el ``StationPreset`` actualmente seleccionado (o None).

        Lo usa el panel de Replay para reflejar la estación elegida en la
        barra lateral sin que el usuario tenga que volver a teclear N.S.L.C.
        """

        data = self.station_combo.currentData()
        return data if isinstance(data, StationPreset) else None

    # ------------------------------------------------------------------
    # Manejadores de señales internas
    # ------------------------------------------------------------------
    def _on_station_changed(self, _index: int) -> None:
        """Reemite la estación seleccionada hacia el exterior.

        Intercepta el item especial "+ Add LAN Shake..." → en lugar
        de tratarlo como un preset, abre el diálogo y revierte la
        selección visible al item previo (para que el usuario vea su
        elección anterior mientras decide).
        """

        data = self.station_combo.currentData()
        if data is _ADD_LAN_SHAKE_SENTINEL:
            self._open_add_lan_shake_dialog()
            return

        self._refresh_station_detail()
        if isinstance(data, StationPreset):
            self.station_changed.emit(data)

    # ------------------------------------------------------------------
    # LAN Shakes — sentinela + diálogo + sincronización con el store
    # ------------------------------------------------------------------
    def _add_lan_sentinel_to_combo(self) -> None:
        """Inserta o re-inserta la fila '+ Add LAN Shake...' al final."""

        # Si ya está, removerlo para garantizar que SIEMPRE quede el último.
        for i in range(self.station_combo.count()):
            if self.station_combo.itemData(i) is _ADD_LAN_SHAKE_SENTINEL:
                self.station_combo.removeItem(i)
                break
        self.station_combo.addItem(
            t("controls.station.add_lan_shake"),
            userData=_ADD_LAN_SHAKE_SENTINEL,
        )

    def _add_lan_shake_to_combo(self, lan: "LanShakePreset") -> None:
        """Inserta un LanShakePreset como un StationPreset normal."""

        preset = lan.to_station_preset()
        # Reusamos append_dynamic_station para respetar el FIFO de 8.
        # Pero esa función inserta tras el último item; aseguramos que
        # el sentinela quede después llamando a _add_lan_sentinel_to_combo.
        self.append_dynamic_station(preset)
        self._add_lan_sentinel_to_combo()

    def _open_add_lan_shake_dialog(self) -> None:
        """Abre AddShakeDialog, persiste el resultado y selecciona el preset."""

        # Importación tardía para evitar ciclo con ui/add_shake_dialog.py
        from shakevision.ui.add_shake_dialog import AddShakeDialog

        # Antes de abrir, revertir la selección al item anterior para
        # que la UI no se quede pintando "+ Add LAN Shake..." si el
        # usuario cancela.
        self._restore_previous_combo_index()

        dialog = AddShakeDialog(parent=self)
        if dialog.exec() != dialog.Accepted:
            return
        lan = dialog.result_preset()
        if lan is None:
            return

        # Persistir (puede sobrescribir si el host ya existía)
        ShakePresetStore.add(lan)
        # El store emite presets_changed → _refresh_lan_shakes_from_store
        # se encarga de añadir / seleccionar en el combo.

    def _restore_previous_combo_index(self) -> None:
        """Selecciona el primer item válido distinto del sentinela."""

        for i in range(self.station_combo.count()):
            if self.station_combo.itemData(i) is not _ADD_LAN_SHAKE_SENTINEL:
                self.station_combo.blockSignals(True)
                self.station_combo.setCurrentIndex(i)
                self.station_combo.blockSignals(False)
                self._refresh_station_detail()
                return

    @Slot()
    def _refresh_lan_shakes_from_store(self) -> None:
        """Sincroniza el combo con la lista actual del store.

        Estrategia: borrar todos los items dinámicos cuyo host coincide
        con algún preset del store o que ya no existen, y re-insertar
        los actuales. Conserva los presets estáticos (XX/MOCK + AM
        defaults de AppConfig) y selecciona el último Shake añadido si
        el usuario acaba de añadir uno.
        """

        from shakevision.services.shake_presets import ShakePresetStore

        store_by_host = {p.host.lower(): p for p in ShakePresetStore.all()}

        # Recopilar índices de items dinámicos que vinieron del store.
        # Heurística: presets con seedlink_host no nulo y network "AM".
        to_remove: list[int] = []
        for i in range(self.station_combo.count()):
            d = self.station_combo.itemData(i)
            if d is _ADD_LAN_SHAKE_SENTINEL:
                continue
            if isinstance(d, StationPreset) and d.seedlink_host and d.network == "AM":
                to_remove.append(i)
        for i in reversed(to_remove):
            self.station_combo.removeItem(i)
            # También limpiar de _dynamic_stations si estaba
            self._dynamic_stations = type(self._dynamic_stations)(
                [d for d in self._dynamic_stations
                 if not (isinstance(d, StationPreset)
                         and d.seedlink_host
                         and d.network == "AM")],
                maxlen=self._dynamic_stations.maxlen,
            )

        # Re-insertar los presets actuales del store
        for lan in store_by_host.values():
            self.append_dynamic_station(lan.to_station_preset())

        # Asegurar que el sentinela queda el último
        self._add_lan_sentinel_to_combo()

    def _on_threshold_slider_changed(self, raw_value: int) -> None:
        """Convierte el valor del slider a flotante y reemite."""

        value = raw_value / 100.0
        self.threshold_value_label.setText(f"{value:.2f}")
        self._emit_trigger_changed()

    def _emit_filter_changed(self) -> None:
        """Empaqueta los valores actuales del filtro y los emite."""

        cfg = FilterConfig(
            enabled=self.filter_enabled_check.isChecked(),
            lowcut_hz=float(self.lowcut_spin.value()),
            highcut_hz=float(self.highcut_spin.value()),
            order=int(self.order_spin.value()),
            detrend=self._config.filt.detrend,
        )
        self.filter_changed.emit(cfg)

    def _on_filter_toggled(self, checked: bool) -> None:
        """Aplica el bypass: deshabilita los controles dependientes y reemite."""

        self._apply_filter_enabled(checked)
        self._emit_filter_changed()

    def _apply_filter_enabled(self, enabled: bool) -> None:
        """Activa o desactiva visualmente los spinboxes de corte y orden."""

        for widget in (self.lowcut_spin, self.highcut_spin, self.order_spin):
            widget.setEnabled(enabled)

    # ------------------------------------------------------------------
    # Sonificación
    # ------------------------------------------------------------------
    def _on_listen_clicked(self) -> None:
        """Reemite la señal con los parámetros actuales del slider."""

        self.listen_clicked.emit(
            self._listen_seconds, int(self.speed_slider.value())
        )

    def _on_speed_changed(self, raw: int) -> None:
        """Refresca la etiqueta del slider y la duración estimada."""

        self.speed_value_label.setText(f"× {raw}")
        self._refresh_audio_duration_label()

    def _refresh_audio_duration_label(self) -> None:
        """Recalcula 'X s de audio' a partir del slider."""

        n_samples = self._listen_seconds * self._stream_sample_rate
        duration_s = estimate_audio_duration_s(
            input_samples=n_samples,
            input_rate_hz=self._stream_sample_rate,
            speed_factor=float(self.speed_slider.value()),
        )
        if duration_s >= 1.0:
            text = t("controls.sound.audio_duration_seconds", value=duration_s)
        else:
            text = t("controls.sound.audio_duration_ms", value=duration_s * 1000)
        self.audio_duration_label.setText(text)

    def _emit_trigger_changed(self) -> None:
        """Empaqueta los valores actuales del trigger y los emite."""

        cfg = TriggerConfig(
            enabled=True,
            sta_seconds=float(self.sta_spin.value()),
            lta_seconds=float(self.lta_spin.value()),
            threshold_on=self.threshold_slider.value() / 100.0,
            threshold_off=self._config.trigger.threshold_off,
            pre_event_seconds=self._config.trigger.pre_event_seconds,
            post_event_seconds=self._config.trigger.post_event_seconds,
        )
        self.trigger_changed.emit(cfg)
