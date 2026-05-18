"""
Diálogo "Add LAN Shake" — v0.3.0.

Permite al usuario añadir una estación Raspberry Shake propia en
la red local indicando IP/hostname, puerto, código de estación y una
etiqueta legible. Antes de aceptar puede pulsar "Test connection"
que hace un pre-check TCP de 5 s (sin importar ObsPy) para
diagnosticar problemas de firewall / IP errónea antes de comprometer
el preset.

El diálogo es completamente reutilizable desde dos lugares:
  * ControlPanel (`+ Add LAN Shake...` en el desplegable de estaciones)
  * SettingsDialog → My Shakes tab (botón "Add...")

Diseño UX
---------
* Validación en vivo del botón OK: deshabilitado si IP o station vacíos.
* "Test connection" pinta resultado al lado con punto verde/rojo.
* Los datos se devuelven como ``LanShakePreset``; el caller decide si
  guardar en el store o solo añadir a la sesión actual.
"""

from __future__ import annotations

import socket
from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from shakevision.i18n import LocaleService, t
from shakevision.services.shake_presets import DEFAULT_PORT, LanShakePreset


# ============================================================
# Worker de TCP pre-check
# ============================================================
class _TcpCheckWorker(QObject):
    """Hace un ``socket.create_connection`` con timeout 5 s y reporta."""

    done = Signal(bool, str)   # (ok, mensaje legible)

    def __init__(self, host: str, port: int) -> None:
        super().__init__()
        self._host = host
        self._port = port

    @Slot()
    def run(self) -> None:
        import time as _time
        t0 = _time.monotonic()
        try:
            with socket.create_connection((self._host, self._port), timeout=5.0):
                pass
        except socket.gaierror as exc:
            self.done.emit(False, t("dialog.add_shake.dns_fail",
                                     host=self._host, detail=str(exc)))
            return
        except (socket.timeout, TimeoutError):
            self.done.emit(False, t("dialog.add_shake.tcp_timeout",
                                     host=self._host, port=self._port))
            return
        except OSError as exc:
            self.done.emit(False, t("dialog.add_shake.tcp_unreachable",
                                     host=self._host, port=self._port,
                                     detail=str(exc)))
            return
        ms = (_time.monotonic() - t0) * 1000
        self.done.emit(True, t("dialog.add_shake.tcp_ok", ms=int(ms)))


# ============================================================
# Diálogo
# ============================================================
class AddShakeDialog(QDialog):
    """Diálogo modal para definir / editar un LAN Shake preset."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        initial: Optional[LanShakePreset] = None,
    ) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setMinimumWidth(420)

        self._test_thread: Optional[QThread] = None
        self._test_worker: Optional[_TcpCheckWorker] = None

        # ─── Formulario ───
        form = QFormLayout()
        form.setSpacing(6)

        self.label_edit = QLineEdit(initial.label if initial else "")
        self.host_edit = QLineEdit(initial.host if initial else "rs.local")
        self.station_edit = QLineEdit(initial.station if initial else "R0000")
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(initial.port if initial else DEFAULT_PORT)

        self._lbl_label = QLabel()
        self._lbl_host = QLabel()
        self._lbl_station = QLabel()
        self._lbl_port = QLabel()
        form.addRow(self._lbl_label, self.label_edit)
        form.addRow(self._lbl_host, self.host_edit)
        form.addRow(self._lbl_station, self.station_edit)
        form.addRow(self._lbl_port, self.port_spin)

        # ─── Fila "Test connection" + status ───
        test_row = QHBoxLayout()
        self.test_button = QPushButton()
        self.test_button.clicked.connect(self._on_test_clicked)
        test_row.addWidget(self.test_button)
        self.test_status = QLabel("")
        self.test_status.setObjectName("StatusValue")
        test_row.addWidget(self.test_status, stretch=1)

        # ─── Botones OK/Cancel ───
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        # Cambios en los campos: revalida el OK
        for w in (self.label_edit, self.host_edit, self.station_edit):
            w.textChanged.connect(self._revalidate)

        # ─── Layout raíz ───
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)
        root.addLayout(form)
        root.addLayout(test_row)
        root.addStretch(1)
        root.addWidget(self.buttons)

        self._retranslate()
        LocaleService.language_changed_signal().connect(self._retranslate)
        self._revalidate()

    # ------------------------------------------------------------------
    # API: lectura del resultado tras .exec() == Accepted
    # ------------------------------------------------------------------
    def result_preset(self) -> Optional[LanShakePreset]:
        """Devuelve el preset construido a partir del formulario.

        ``None`` si el usuario canceló o si los datos no son válidos.
        """

        label = self.label_edit.text().strip()
        host = self.host_edit.text().strip()
        station = self.station_edit.text().strip().upper()
        port = int(self.port_spin.value())
        if not host or not station:
            return None
        if not label:
            label = f"Shake @ {host}"
        return LanShakePreset(
            label=label,
            host=host,
            station=station,
            network="AM",
            location="",
            port=port,
        )

    # ------------------------------------------------------------------
    # i18n
    # ------------------------------------------------------------------
    def _retranslate(self) -> None:
        self.setWindowTitle(t("dialog.add_shake.title"))
        self._lbl_label.setText(t("dialog.add_shake.label"))
        self._lbl_host.setText(t("dialog.add_shake.host"))
        self._lbl_station.setText(t("dialog.add_shake.station"))
        self._lbl_port.setText(t("dialog.add_shake.port"))
        self.test_button.setText(t("dialog.add_shake.test_connection"))

    # ------------------------------------------------------------------
    # Validación + estado del botón OK
    # ------------------------------------------------------------------
    @Slot()
    def _revalidate(self) -> None:
        host = self.host_edit.text().strip()
        station = self.station_edit.text().strip()
        ok = bool(host) and bool(station)
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(ok)

    # ------------------------------------------------------------------
    # Test connection
    # ------------------------------------------------------------------
    @Slot()
    def _on_test_clicked(self) -> None:
        host = self.host_edit.text().strip()
        if not host:
            return
        port = int(self.port_spin.value())
        self.test_button.setEnabled(False)
        self.test_status.setText(t("dialog.add_shake.testing"))
        self._set_status_color(QColor("#a1a1aa"))   # gris neutro

        # Run en hilo aparte para no bloquear la UI 5 s
        self._test_thread = QThread()
        self._test_worker = _TcpCheckWorker(host, port)
        self._test_worker.moveToThread(self._test_thread)
        self._test_thread.started.connect(self._test_worker.run)
        self._test_worker.done.connect(self._on_test_done)
        self._test_worker.done.connect(self._test_thread.quit)
        self._test_thread.finished.connect(self._cleanup_test_thread)
        self._test_thread.start()

    @Slot(bool, str)
    def _on_test_done(self, ok: bool, message: str) -> None:
        self.test_status.setText(message)
        self._set_status_color(QColor("#22c55e") if ok else QColor("#ef4444"))
        self.test_button.setEnabled(True)

    @Slot()
    def _cleanup_test_thread(self) -> None:
        if self._test_thread is None:
            return
        self._test_thread.wait(1000)
        self._test_thread.deleteLater()
        self._test_thread = None
        if self._test_worker is not None:
            self._test_worker.deleteLater()
            self._test_worker = None

    def _set_status_color(self, color: QColor) -> None:
        palette = self.test_status.palette()
        palette.setColor(QPalette.WindowText, color)
        self.test_status.setPalette(palette)
