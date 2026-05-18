"""
Ventana «Preferencias».

Contenido:
  * Idioma de la interfaz (EN/ES/ZH/FR)
  * Zona horaria (auto-detección + manual + libre)
  * Ubicación personalizada (texto libre, opcional)

Política:
  * Aplicar es inmediato: cambiar idioma redibuja, cambiar timezone
    refresca todas las marcas de tiempo en vivo.
  * Cancelar deja el estado anterior intacto.
  * "Restaurar valores" vuelve a detección del sistema + EN.
"""

from __future__ import annotations

import datetime as _dt
import logging
from typing import Optional

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from shakevision.i18n import LocaleService, t
from shakevision.i18n.service import LANGUAGE_LABELS, SUPPORTED_LANGUAGES
from shakevision.services.shake_presets import ShakePresetStore
from shakevision.services.timezone_service import TimezoneService


def _safe_today() -> str:
    """YYYY-MM-DD del día actual — usado como sufijo del fichero de backup.

    v0.7-C: el tab "Backup" fue reemplazado por "Reset"; este helper
    se mantiene por compatibilidad si alguien lo importa.
    """

    return _dt.date.today().isoformat()


logger = logging.getLogger(__name__)


class SettingsDialog(QDialog):
    """Diálogo modal de preferencias."""

    # Emitidas cuando el usuario aplica cambios efectivos. MainWindow
    # las escucha para repintar status bar / re-disparar render del
    # dashboard con la nueva timezone.
    settings_applied = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("settings.title"))
        self.setMinimumWidth(520)
        # Permitir redimensionar (textos de algunos idiomas son largos)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)

        self._initial_lang = LocaleService.current_language()
        self._initial_tz = TimezoneService.current_iana()
        self._initial_address = TimezoneService.address()

        self._build_ui()
        self._populate()

    # ------------------------------------------------------------------
    # Construcción
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        # ─── Tab widget ───
        # En v0.3.0 el diálogo creció con la sección "My Shakes". En
        # vez de seguir apilando secciones verticales (que rebasaría
        # alto de pantalla en laptops 13"), separamos en pestañas.
        self._tabs = QTabWidget(self)
        self._tabs.setDocumentMode(True)

        # ── Tab General (idioma + región + dirección) ──
        general = QWidget(self._tabs)
        general_layout = QVBoxLayout(general)
        general_layout.setContentsMargins(8, 8, 8, 8)
        general_layout.setSpacing(14)
        general_layout.addLayout(self._build_language_section())
        general_layout.addWidget(self._separator())
        general_layout.addLayout(self._build_locale_section())
        general_layout.addStretch(1)
        self._tabs.addTab(general, t("settings.tab.general"))

        # ── Tab My Shakes (LAN Raspberry Shake presets) ──
        shakes = self._build_my_shakes_tab()
        self._tabs.addTab(shakes, t("settings.tab.my_shakes"))

        # ── Tab Reset (v0.7-C: clear cache) ──
        # Sustituye al antiguo tab "Backup" — el flujo export/import
        # JSON estaba poco usado y resultaba confuso ("¿qué incluye?").
        # La nueva acción es más directa: borrar TODO y reiniciar el
        # onboarding, equivalente a una reinstalación limpia.
        reset = self._build_reset_tab()
        self._tabs.addTab(reset, t("settings.tab.reset"))

        root.addWidget(self._tabs, stretch=1)

        # ─── Botones inferiores ───
        buttons = QDialogButtonBox()
        self._apply_btn = buttons.addButton(
            t("settings.actions.apply"), QDialogButtonBox.AcceptRole
        )
        self._cancel_btn = buttons.addButton(
            t("settings.actions.cancel"), QDialogButtonBox.RejectRole
        )
        self._restore_btn = buttons.addButton(
            t("settings.actions.restore_defaults"), QDialogButtonBox.ResetRole
        )
        self._apply_btn.clicked.connect(self._on_apply)
        self._cancel_btn.clicked.connect(self.reject)
        self._restore_btn.clicked.connect(self._on_restore_defaults)
        root.addWidget(buttons)

    def _build_language_section(self) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setSpacing(8)
        title = QLabel(t("settings.section.language"))
        # v0.6: usa el selector global SettingsSectionTitle en lugar
        # de inline setStyleSheet — funciona en ambos temas.
        title.setObjectName("SettingsSectionTitle")
        layout.addWidget(title)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(8)

        self._lang_combo = QComboBox()
        for code in SUPPORTED_LANGUAGES:
            label = LANGUAGE_LABELS.get(code, code)
            self._lang_combo.addItem(label, userData=code)
        form.addRow(t("settings.language.label"), self._lang_combo)

        help_text = QLabel(t("settings.language.help"))
        help_text.setObjectName("DialogHint")
        help_text.setWordWrap(True)
        layout.addLayout(form)
        layout.addWidget(help_text)
        return layout

    def _build_locale_section(self) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setSpacing(8)
        title = QLabel(t("settings.section.locale"))
        title.setObjectName("SettingsSectionTitle")
        layout.addWidget(title)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(8)

        # ─── Timezone ───
        tz_row = QHBoxLayout()
        tz_row.setSpacing(6)
        self._tz_combo = QComboBox()
        self._tz_combo.setEditable(True)
        # Cargar lista completa de zonas
        for name in TimezoneService.available_timezones():
            self._tz_combo.addItem(name)
        self._tz_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tz_row.addWidget(self._tz_combo, stretch=1)
        self._detect_btn = QPushButton(t("settings.timezone.detect_button"))
        self._detect_btn.clicked.connect(self._on_detect_clicked)
        tz_row.addWidget(self._detect_btn)
        form.addRow(t("settings.timezone.label"), tz_row)

        # ─── Address (texto libre + auto-detect por IP) ───
        # v0.7-D: añadimos un botón "Detectar mi ubicación" que llama a
        # ip-api.com (HTTP, sin key, ~45 req/min). El usuario debe
        # pulsarlo explícitamente — nunca se llama en background.
        addr_row = QHBoxLayout()
        addr_row.setSpacing(6)
        self._address_edit = QLineEdit()
        self._address_edit.setPlaceholderText(t("settings.address.placeholder"))
        self._address_edit.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Preferred)
        addr_row.addWidget(self._address_edit, stretch=1)
        self._detect_location_btn = QPushButton(
            t("settings.address.detect_button"))
        self._detect_location_btn.clicked.connect(
            self._on_detect_location_clicked)
        addr_row.addWidget(self._detect_location_btn)
        form.addRow(t("settings.address.label"), addr_row)

        layout.addLayout(form)

        # Hints — v0.6 usan DialogHint global
        tz_help = QLabel(t("settings.timezone.help"))
        tz_help.setObjectName("DialogHint")
        tz_help.setWordWrap(True)
        layout.addWidget(tz_help)
        addr_help = QLabel(t("settings.address.help"))
        addr_help.setObjectName("DialogHint")
        addr_help.setWordWrap(True)
        layout.addWidget(addr_help)

        return layout

    # ------------------------------------------------------------------
    # Tab "My Shakes"
    # ------------------------------------------------------------------
    def _build_my_shakes_tab(self) -> QWidget:
        """Construye la pestaña de gestión de Shakes LAN."""

        page = QWidget(self._tabs)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Encabezado explicativo — v0.6 usa DialogHint global
        self._shakes_help = QLabel()
        self._shakes_help.setObjectName("DialogHint")
        self._shakes_help.setWordWrap(True)
        layout.addWidget(self._shakes_help)

        # Lista de presets
        self._shakes_list = QListWidget()
        self._shakes_list.setAlternatingRowColors(True)
        self._shakes_list.setSelectionMode(QListWidget.SingleSelection)
        self._shakes_list.itemDoubleClicked.connect(self._on_shake_edit)
        layout.addWidget(self._shakes_list, stretch=1)

        # Mensaje "no shakes" cuando la lista está vacía
        self._shakes_empty = QLabel()
        self._shakes_empty.setObjectName("DialogEmpty")
        self._shakes_empty.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._shakes_empty)

        # Botonera inferior: Add / Rename / Delete
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self._shake_add_btn = QPushButton()
        self._shake_add_btn.clicked.connect(self._on_shake_add)
        btn_row.addWidget(self._shake_add_btn)
        self._shake_rename_btn = QPushButton()
        self._shake_rename_btn.clicked.connect(self._on_shake_rename)
        btn_row.addWidget(self._shake_rename_btn)
        self._shake_delete_btn = QPushButton()
        self._shake_delete_btn.clicked.connect(self._on_shake_delete)
        btn_row.addWidget(self._shake_delete_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        # Suscribirse a cambios externos del store (otra ventana, etc.)
        ShakePresetStore.changed_signal().connect(self._reload_shakes_list)
        self._reload_shakes_list()

        self._retranslate_shakes_tab()
        return page

    def _retranslate_shakes_tab(self) -> None:
        """Re-aplica i18n en la pestaña My Shakes."""

        self._shakes_help.setText(t("settings.my_shakes.help"))
        self._shake_add_btn.setText(t("settings.my_shakes.add"))
        self._shake_rename_btn.setText(t("settings.my_shakes.rename"))
        self._shake_delete_btn.setText(t("settings.my_shakes.delete"))
        self._shakes_empty.setText(t("settings.my_shakes.empty"))
        # Tabs
        if hasattr(self, "_tabs"):
            self._tabs.setTabText(0, t("settings.tab.general"))
            self._tabs.setTabText(1, t("settings.tab.my_shakes"))
            if self._tabs.count() > 2:
                self._tabs.setTabText(2, t("settings.tab.reset"))
        # Reset tab widgets (v0.7-C — sustituye al antiguo Backup)
        if hasattr(self, "_reset_heading"):
            self._reset_heading.setText(t("settings.reset.heading"))
            self._reset_help.setText(t("settings.reset.help"))
            self._reset_button.setText(t("settings.reset.button"))

    @Slot()
    def _reload_shakes_list(self) -> None:
        """Recarga la lista desde el store."""

        self._shakes_list.clear()
        presets = ShakePresetStore.all()
        for p in presets:
            item = QListWidgetItem(
                f"{p.label}    —    {p.host}:{p.port}  ·  {p.network}.{p.station}"
            )
            item.setData(Qt.UserRole, p.host)   # clave para mutar
            self._shakes_list.addItem(item)
        # Empty state
        has_any = len(presets) > 0
        self._shakes_empty.setVisible(not has_any)
        self._shakes_list.setVisible(has_any)
        self._shake_rename_btn.setEnabled(has_any)
        self._shake_delete_btn.setEnabled(has_any)

    @Slot()
    def _on_shake_add(self) -> None:
        """Abre AddShakeDialog para crear un preset nuevo."""

        # Importación tardía para evitar ciclo
        from shakevision.ui.add_shake_dialog import AddShakeDialog

        dialog = AddShakeDialog(parent=self)
        if dialog.exec() != QDialog.Accepted:
            return
        lan = dialog.result_preset()
        if lan is None:
            return
        ShakePresetStore.add(lan)
        # changed_signal triggea _reload_shakes_list

    @Slot()
    def _on_shake_edit(self, item: QListWidgetItem) -> None:
        """Doble-click en la lista → editar preset existente."""

        from shakevision.ui.add_shake_dialog import AddShakeDialog

        host = item.data(Qt.UserRole)
        existing = ShakePresetStore.find_by_host(host)
        if existing is None:
            return
        dialog = AddShakeDialog(parent=self, initial=existing)
        if dialog.exec() != QDialog.Accepted:
            return
        updated = dialog.result_preset()
        if updated is None:
            return
        # Si el usuario cambió el host, borramos el antiguo primero.
        if updated.host.lower() != existing.host.lower():
            ShakePresetStore.delete(existing.host)
        ShakePresetStore.add(updated)

    @Slot()
    def _on_shake_rename(self) -> None:
        """Pide un nuevo label para el item seleccionado."""

        item = self._shakes_list.currentItem()
        if item is None:
            return
        host = item.data(Qt.UserRole)
        existing = ShakePresetStore.find_by_host(host)
        if existing is None:
            return
        new_label, ok = QInputDialog.getText(
            self,
            t("settings.my_shakes.rename"),
            t("settings.my_shakes.rename_prompt"),
            text=existing.label,
        )
        if ok and new_label.strip():
            ShakePresetStore.rename(host, new_label.strip())

    @Slot()
    def _on_shake_delete(self) -> None:
        """Borra el item seleccionado tras confirmar."""

        item = self._shakes_list.currentItem()
        if item is None:
            return
        host = item.data(Qt.UserRole)
        existing = ShakePresetStore.find_by_host(host)
        if existing is None:
            return
        reply = QMessageBox.question(
            self,
            t("settings.my_shakes.delete"),
            t("settings.my_shakes.delete_confirm",
              label=existing.label, host=existing.host),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            ShakePresetStore.delete(host)

    # ------------------------------------------------------------------
    # Reset tab (v0.7-C — clear cache + restart como nueva instalación)
    # ------------------------------------------------------------------
    def _build_reset_tab(self) -> QWidget:
        """Tab con un botón rojo "Limpiar caché" + confirmación dura.

        Reemplaza al antiguo tab "Backup" cuyo flujo export/import JSON
        resultaba opaco. La nueva acción es directa y predecible: borra
        TODO el estado persistente (QSettings + cache de disco) y cierra
        la app — al volver a abrirla, el usuario verá splash + Localízame
        + Onboarding wizard otra vez, igual que el primer arranque.
        """

        from PySide6.QtWidgets import QWidget as _W
        tab = _W()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(14)

        # Texto de cabecera + descripción detallada de qué se borra
        self._reset_heading = QLabel()
        self._reset_heading.setObjectName("SettingsSectionTitle")
        layout.addWidget(self._reset_heading)
        self._reset_help = QLabel()
        self._reset_help.setWordWrap(True)
        self._reset_help.setObjectName("DialogHint")
        layout.addWidget(self._reset_help)

        # Botón destructivo — etiqueta y color de "danger" (objectName
        # DangerButton para que el QSS global lo pinte rojo si lo hay;
        # si no, queda con color por defecto pero la confirmación
        # protege al usuario igualmente).
        btns = QHBoxLayout()
        btns.setSpacing(8)
        self._reset_button = QPushButton()
        self._reset_button.setObjectName("DangerButton")
        self._reset_button.setProperty("danger", True)
        self._reset_button.clicked.connect(self._on_clear_cache_clicked)
        btns.addWidget(self._reset_button)
        btns.addStretch(1)
        layout.addLayout(btns)

        # Status visible de la última operación (poco usado — tras
        # clear la app se cierra inmediatamente).
        self._reset_status = QLabel("")
        self._reset_status.setWordWrap(True)
        self._reset_status.setObjectName("DialogHint")
        layout.addWidget(self._reset_status)
        layout.addStretch(1)
        return tab

    def _on_clear_cache_clicked(self) -> None:
        """Confirma con un diálogo destructivo, ejecuta clear_all() y
        cierra la app. El usuario tiene que volver a abrirla
        manualmente — esto es deliberado: dar tiempo a leer el efecto.
        """

        reply = QMessageBox.question(
            self,
            t("settings.reset.confirm_title"),
            t("settings.reset.confirm_body"),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            from shakevision.services.clear_cache import clear_all
            summary = clear_all()
            # Resumen condensado para el log (la UI ya no se verá tras
            # quit, pero el status queda escrito por si quit falla).
            errors = [k for k, v in summary.items()
                      if isinstance(v, str) and v.startswith("error")]
            if errors:
                self._reset_status.setText(
                    t("settings.reset.partial",
                      errors=", ".join(errors)))
                logger.warning("Clear cache: errores en %s", errors)
            else:
                self._reset_status.setText(
                    t("settings.reset.ok"))
                logger.info("Clear cache: todo OK, cerrando app")
        except Exception as exc:  # noqa: BLE001
            self._reset_status.setText(
                t("settings.reset.error", error=str(exc)))
            logger.exception("Clear cache falló")
            return

        # Cierre limpio del proceso. Usar QApplication.quit en lugar
        # de sys.exit para que Qt haga cleanup ordenado de timers,
        # threads, web engine, etc.
        from PySide6.QtWidgets import QApplication
        QApplication.quit()

    @staticmethod
    def _separator() -> QFrame:
        # v0.6: usa DialogSeparator global (responde al tema).
        line = QFrame()
        line.setObjectName("DialogSeparator")
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Plain)
        return line

    # ------------------------------------------------------------------
    # Datos iniciales
    # ------------------------------------------------------------------
    def _populate(self) -> None:
        # Idioma actual
        idx = self._lang_combo.findData(self._initial_lang)
        if idx >= 0:
            self._lang_combo.setCurrentIndex(idx)

        # Timezone actual
        idx = self._tz_combo.findText(self._initial_tz)
        if idx >= 0:
            self._tz_combo.setCurrentIndex(idx)
        else:
            self._tz_combo.setEditText(self._initial_tz)

        # Dirección libre
        self._address_edit.setText(self._initial_address)

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def _on_detect_clicked(self) -> None:
        """Botón «Detectar del sistema»."""

        detected = TimezoneService.detect_system_timezone()
        if not detected:
            QMessageBox.warning(
                self,
                t("common.error"),
                t("settings.timezone.detection_failed"),
            )
            return
        idx = self._tz_combo.findText(detected)
        if idx >= 0:
            self._tz_combo.setCurrentIndex(idx)
        else:
            self._tz_combo.setEditText(detected)
        # Pequeña confirmación visual
        self._detect_btn.setText(t("settings.timezone.detected", tz=detected))

    def _on_detect_location_clicked(self) -> None:
        """v0.7-D: botón «Detectar mi ubicación» — usa ip-api.com.

        La llamada va en QThread (LocationService.detect_async) para no
        bloquear la UI; mientras tanto el botón muestra "Detectando…" y
        se desactiva. Al volver se rellena el address field (o se
        muestra error con QMessageBox)."""

        # Estado "trabajando" — botón deshabilitado, texto de progreso.
        self._detect_location_btn.setEnabled(False)
        self._detect_location_btn.setText(t("settings.address.detecting"))

        def _on_done(detected, error):
            # Restaurar UI siempre, suceda lo que suceda
            self._detect_location_btn.setEnabled(True)
            self._detect_location_btn.setText(
                t("settings.address.detect_button"))
            if error:
                QMessageBox.warning(
                    self,
                    t("common.error"),
                    t("settings.address.detect_failed", error=error),
                )
                return
            if detected is None:
                return
            self._address_edit.setText(detected.formatted)
            # Si ip-api detectó una timezone distinta, ofrecemos
            # también actualizarla (atajo de UX — el usuario podría
            # estar configurando por primera vez).
            if detected.timezone and detected.timezone != self._tz_combo.currentText():
                reply = QMessageBox.question(
                    self,
                    t("settings.address.tz_offer_title"),
                    t("settings.address.tz_offer_body",
                      tz=detected.timezone),
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes,
                )
                if reply == QMessageBox.Yes:
                    idx = self._tz_combo.findText(detected.timezone)
                    if idx >= 0:
                        self._tz_combo.setCurrentIndex(idx)
                    else:
                        self._tz_combo.setEditText(detected.timezone)

        try:
            from shakevision.services.location_service import detect_async
            detect_async(_on_done)
        except Exception as exc:  # noqa: BLE001
            self._detect_location_btn.setEnabled(True)
            self._detect_location_btn.setText(
                t("settings.address.detect_button"))
            QMessageBox.warning(
                self,
                t("common.error"),
                t("settings.address.detect_failed", error=str(exc)),
            )

    def _on_restore_defaults(self) -> None:
        """Restaurar: idioma EN + timezone detectado + dirección vacía."""

        # Idioma EN
        idx = self._lang_combo.findData("en")
        if idx >= 0:
            self._lang_combo.setCurrentIndex(idx)
        # Timezone detectado o UTC
        detected = TimezoneService.detect_system_timezone() or "UTC"
        idx = self._tz_combo.findText(detected)
        if idx >= 0:
            self._tz_combo.setCurrentIndex(idx)
        else:
            self._tz_combo.setEditText(detected)
        # Dirección vacía
        self._address_edit.clear()

    def _on_apply(self) -> None:
        """Aplica los cambios y cierra el diálogo con accept()."""

        # Idioma
        new_lang = self._lang_combo.currentData()
        if new_lang and new_lang != self._initial_lang:
            LocaleService.set_language(new_lang)

        # Timezone — validar antes de aceptar
        new_tz = self._tz_combo.currentText().strip()
        if new_tz and new_tz != self._initial_tz:
            ok = TimezoneService.set_timezone(new_tz)
            if not ok:
                QMessageBox.warning(
                    self,
                    t("common.error"),
                    t(
                        "settings.timezone.partial_detection",
                    ),
                )
                # No cerramos — dejar al usuario corregir
                return

        # Dirección
        new_addr = self._address_edit.text().strip()
        if new_addr != self._initial_address:
            TimezoneService.set_address(new_addr)

        self.settings_applied.emit()
        self.accept()
