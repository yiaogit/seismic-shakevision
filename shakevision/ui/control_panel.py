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
from typing import Iterable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
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

        # Construir la interfaz por secciones
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(14)

        root.addLayout(self._build_station_section(config.stations))
        root.addLayout(self._build_connection_section())
        root.addLayout(self._build_filter_section(config.filt))
        root.addLayout(self._build_trigger_section(config.trigger))
        root.addLayout(self._build_sound_section(config.stream.sample_rate_hz))
        root.addStretch(1)

        # Aplicar textos traducidos + suscribirse a cambios de idioma
        self._retranslate()
        LocaleService.language_changed_signal().connect(self._retranslate)

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
        self.station_combo.currentIndexChanged.connect(self._on_station_changed)
        layout.addWidget(self.station_combo)

        # Información detallada del preset seleccionado
        self.station_detail = QLabel()
        self.station_detail.setObjectName("StatusValue")
        self.station_detail.setWordWrap(True)
        layout.addWidget(self.station_detail)

        # Mostrar el detalle inicial
        self._refresh_station_detail()

        return layout

    def _build_connection_section(self) -> QHBoxLayout:
        """Botones de conexión/desconexión."""

        layout = QHBoxLayout()
        layout.setSpacing(6)

        self.connect_button = QPushButton()
        self.connect_button.clicked.connect(self.connect_clicked.emit)
        layout.addWidget(self.connect_button)

        self.disconnect_button = QPushButton()
        self.disconnect_button.clicked.connect(self.disconnect_clicked.emit)
        layout.addWidget(self.disconnect_button)

        return layout

    def _build_filter_section(self, filt: FilterConfig) -> QVBoxLayout:
        """Controles del filtro Butterworth pasa banda."""

        layout = QVBoxLayout()
        layout.setSpacing(6)
        self._filter_section_title = self._section_title("")
        layout.addWidget(self._filter_section_title)

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

        # Reflejar el estado inicial en los controles dependientes
        self._apply_filter_enabled(filt.enabled)

        return layout

    def _build_trigger_section(self, trig: TriggerConfig) -> QVBoxLayout:
        """Controles del detector STA/LTA."""

        layout = QVBoxLayout()
        layout.setSpacing(6)
        self._trigger_section_title = self._section_title("")
        layout.addWidget(self._trigger_section_title)

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
        self._sound_section_title = self._section_title("")
        layout.addWidget(self._sound_section_title)

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
        self._filter_section_title.setText(t("controls.section.filter"))
        self._trigger_section_title.setText(t("controls.section.trigger"))
        self._sound_section_title.setText(t("controls.section.sound"))

        self.connect_button.setText(t("controls.connect"))
        self.disconnect_button.setText(t("controls.disconnect"))

        self.filter_enabled_check.setText(t("controls.filter.enable"))
        self._lowcut_label.setText(t("controls.filter.lowcut"))
        self._highcut_label.setText(t("controls.filter.highcut"))
        self._order_label.setText(t("controls.filter.order"))

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

        Devuelve ``True`` si añadió una entrada nueva al combo,
        ``False`` si solo seleccionó una existente.
        """

        # ¿Ya existe? Comparamos por N.S.L (sin canal, el canal Z se
        # asume EHZ por defecto y no debe forzar duplicados).
        for i in range(self.station_combo.count()):
            existing: StationPreset | None = self.station_combo.itemData(i)
            if existing is None:
                continue
            if (existing.network == preset.network
                    and existing.station == preset.station
                    and existing.location == preset.location):
                self.station_combo.setCurrentIndex(i)
                return False

        # FIFO sobre las dinámicas
        if len(self._dynamic_stations) >= self.MAX_DYNAMIC_STATIONS:
            oldest = self._dynamic_stations.popleft()
            for i in range(self.station_combo.count()):
                d: StationPreset | None = self.station_combo.itemData(i)
                if d is oldest:
                    self.station_combo.removeItem(i)
                    break

        # Insertar al final y seleccionar.
        self.station_combo.addItem(preset.label, userData=preset)
        self._dynamic_stations.append(preset)
        self.station_combo.setCurrentIndex(self.station_combo.count() - 1)
        return True

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

    def _refresh_station_detail(self) -> None:
        """Actualiza el texto descriptivo del preset seleccionado."""

        preset: StationPreset | None = self.station_combo.currentData()
        if preset is None:
            self.station_detail.setText("—")
            return
        self.station_detail.setText(
            f"{preset.network}.{preset.station}."
            f"{preset.location or '--'}.{preset.channel}"
        )

    # ------------------------------------------------------------------
    # Manejadores de señales internas
    # ------------------------------------------------------------------
    def _on_station_changed(self, _index: int) -> None:
        """Reemite la estación seleccionada hacia el exterior."""

        self._refresh_station_detail()
        preset: StationPreset | None = self.station_combo.currentData()
        if preset is not None:
            self.station_changed.emit(preset)

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
