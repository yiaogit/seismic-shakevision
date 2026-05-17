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

import logging
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from shakevision.i18n import LocaleService, t
from shakevision.i18n.service import LANGUAGE_LABELS, SUPPORTED_LANGUAGES
from shakevision.services.timezone_service import TimezoneService


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
        root.setSpacing(18)

        # ─── Sección IDIOMA ───
        root.addLayout(self._build_language_section())
        root.addWidget(self._separator())

        # ─── Sección REGIÓN Y HORA ───
        root.addLayout(self._build_locale_section())

        root.addStretch(1)

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
        layout.setSpacing(6)
        title = QLabel(t("settings.section.language"))
        title.setObjectName("SectionTitle")
        title.setStyleSheet("font-weight: 600; font-size: 13px;")
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
        help_text.setWordWrap(True)
        help_text.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 11px;")
        layout.addLayout(form)
        layout.addWidget(help_text)
        return layout

    def _build_locale_section(self) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setSpacing(6)
        title = QLabel(t("settings.section.locale"))
        title.setObjectName("SectionTitle")
        title.setStyleSheet("font-weight: 600; font-size: 13px;")
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

        # ─── Address (texto libre) ───
        self._address_edit = QLineEdit()
        self._address_edit.setPlaceholderText(t("settings.address.placeholder"))
        form.addRow(t("settings.address.label"), self._address_edit)

        layout.addLayout(form)

        # Hints
        tz_help = QLabel(t("settings.timezone.help"))
        tz_help.setWordWrap(True)
        tz_help.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 11px;")
        layout.addWidget(tz_help)
        addr_help = QLabel(t("settings.address.help"))
        addr_help.setWordWrap(True)
        addr_help.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 11px;")
        layout.addWidget(addr_help)

        return layout

    @staticmethod
    def _separator() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet("color: rgba(255,255,255,0.08);")
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
