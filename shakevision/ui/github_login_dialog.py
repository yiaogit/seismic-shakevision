"""
``GitHubLoginDialog`` — UI del Device Flow (v0.5 阶段 K).

Tres estados visibles:

  1. INTRO    — explica qué pasa al pulsar "Conectar con GitHub" +
                botón principal "Conectar". Si client_id no está
                configurado, muestra mensaje "no configurado" y un
                campo opcional para introducirlo ad-hoc.
  2. WAITING  — tras start_device_flow: muestra ``user_code`` en
                grande (mono + cyan), botón "Abrir GitHub" que abre
                ``verification_uri`` en el navegador del sistema,
                spinner de "esperando autorización", y "Cancelar".
                El polling vive en un QThread; emite ``finished`` con
                el token o con la excepción.
  3. SUCCESS  — token recibido → fetch_user_profile → mostrar
                ``login`` + avatar (lazy descarga) + "Has iniciado
                sesión como X". Botón "Cerrar".

i18n
----
Todas las cadenas usan ``t("github.login.<key>")``. Los textos en
inglés/es/zh/fr se añaden a los 4 locales en el mismo commit.

Integración
-----------
La fachada ``GitHubAuthService`` se encarga de:
  * persistir token y perfil en QSettings tras ``SUCCESS``.
  * Profile page (阶段 L) puede consultar ``is_authenticated`` /
    ``current_user`` sin volver a abrir este diálogo.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QObject, QThread, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices, QKeyEvent
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from shakevision.i18n import LocaleService, t
from shakevision.services.github_auth import (
    AuthorizationDeniedError,
    AuthorizationExpiredError,
    DeviceCodeInfo,
    GitHubAuthError,
    GitHubAuthService,
    NotConfiguredError,
)


logger = logging.getLogger(__name__)


# ============================================================
# Worker QThread para el polling
# ============================================================
class _PollWorker(QObject):
    """Ejecuta poll_for_token + fetch_user_profile en un QThread.

    Emite ``succeeded(token, profile_dict)`` o ``failed(error_kind, msg)``
    según el resultado. ``error_kind`` es uno de:
      * "denied" / "expired" / "network" / "cancelled" / "unknown".
    """

    succeeded = Signal(str, dict)
    failed = Signal(str, str)

    def __init__(self, info: DeviceCodeInfo) -> None:
        super().__init__()
        self._info = info
        self._cancelled = False

    def request_cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            token = GitHubAuthService.poll_for_token(
                self._info,
                cancel_check=lambda: self._cancelled,
            )
            profile = GitHubAuthService.fetch_user_profile(token)
            self.succeeded.emit(token, profile)
        except AuthorizationDeniedError as exc:
            self.failed.emit("denied", str(exc))
        except AuthorizationExpiredError as exc:
            self.failed.emit("expired", str(exc))
        except GitHubAuthError as exc:
            if "cancelado" in str(exc).lower():
                self.failed.emit("cancelled", str(exc))
            else:
                self.failed.emit("network", str(exc))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit("unknown", str(exc))


# ============================================================
# Diálogo
# ============================================================
class GitHubLoginDialog(QDialog):
    """Modal de login GitHub Device Flow."""

    # Emitido cuando el login termina con éxito (token persistido).
    logged_in = Signal(dict)   # profile dict

    PAGE_INTRO   = 0
    PAGE_WAITING = 1
    PAGE_SUCCESS = 2

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("GitHubLoginDialog")
        self.setWindowTitle("GitHub")
        self.setModal(True)
        self.setMinimumWidth(420)

        self._thread: Optional[QThread] = None
        self._worker: Optional[_PollWorker] = None
        self._device_info: Optional[DeviceCodeInfo] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(14)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_intro_page())
        self._stack.addWidget(self._build_waiting_page())
        self._stack.addWidget(self._build_success_page())
        root.addWidget(self._stack)

        self._stack.setCurrentIndex(self.PAGE_INTRO)
        self._retranslate()

        # v0.5 阶段 O — escuchar cambios de idioma para re-traducir el
        # diálogo en vivo (igual que el resto de diálogos modales).
        try:
            LocaleService.language_changed_signal().connect(
                lambda _l: self._retranslate())
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------
    # Páginas
    # ------------------------------------------------------------------
    def _build_intro_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        self._intro_heading = QLabel()
        f = self._intro_heading.font(); f.setPointSize(14); f.setBold(True)
        self._intro_heading.setFont(f)
        layout.addWidget(self._intro_heading)

        self._intro_body = QLabel()
        self._intro_body.setWordWrap(True)
        layout.addWidget(self._intro_body)

        # Si no hay client_id configurado: campo para introducirlo
        self._client_id_field = QLineEdit()
        # v0.5 阶段 O — el placeholder ahora está en los 4 locales.
        self._client_id_field.setPlaceholderText(
            t("github.login.client_id_placeholder"))
        cur = GitHubAuthService.client_id()
        if cur:
            self._client_id_field.setText(cur)
        layout.addWidget(self._client_id_field)
        # Solo mostrar el campo si no está ya configurado
        self._client_id_field.setVisible(not GitHubAuthService.is_configured())

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self._intro_cancel_btn = QPushButton()
        self._intro_cancel_btn.clicked.connect(self.reject)
        self._intro_connect_btn = QPushButton()
        self._intro_connect_btn.setDefault(True)
        self._intro_connect_btn.clicked.connect(self._on_connect_clicked)
        btn_row.addWidget(self._intro_cancel_btn)
        btn_row.addWidget(self._intro_connect_btn)
        layout.addLayout(btn_row)

        return page

    def _build_waiting_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        self._wait_heading = QLabel()
        f = self._wait_heading.font(); f.setPointSize(13); f.setBold(True)
        self._wait_heading.setFont(f)
        layout.addWidget(self._wait_heading)

        self._wait_body = QLabel()
        self._wait_body.setWordWrap(True)
        layout.addWidget(self._wait_body)

        # User-code grande y mono
        self._user_code_label = QLabel("·····")
        f = self._user_code_label.font()
        f.setFamily("JetBrains Mono")
        f.setPointSize(24)
        f.setBold(True)
        self._user_code_label.setFont(f)
        self._user_code_label.setAlignment(Qt.AlignCenter)
        self._user_code_label.setTextInteractionFlags(
            Qt.TextSelectableByMouse)
        layout.addWidget(self._user_code_label)

        # v0.6: usa DialogHint global en lugar de hardcoded #71717a
        self._wait_status = QLabel()
        self._wait_status.setObjectName("DialogHint")
        self._wait_status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._wait_status)

        btn_row = QHBoxLayout()
        self._wait_cancel_btn = QPushButton()
        self._wait_cancel_btn.clicked.connect(self._on_wait_cancel)
        btn_row.addWidget(self._wait_cancel_btn)
        btn_row.addStretch(1)
        self._open_browser_btn = QPushButton()
        self._open_browser_btn.setDefault(True)
        self._open_browser_btn.clicked.connect(self._on_open_browser)
        btn_row.addWidget(self._open_browser_btn)
        layout.addLayout(btn_row)

        return page

    def _build_success_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        self._success_heading = QLabel()
        f = self._success_heading.font(); f.setPointSize(14); f.setBold(True)
        self._success_heading.setFont(f)
        layout.addWidget(self._success_heading)

        self._success_body = QLabel()
        self._success_body.setWordWrap(True)
        layout.addWidget(self._success_body)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self._success_close_btn = QPushButton()
        self._success_close_btn.setDefault(True)
        self._success_close_btn.clicked.connect(self.accept)
        btn_row.addWidget(self._success_close_btn)
        layout.addLayout(btn_row)

        return page

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def _on_connect_clicked(self) -> None:
        """Inicia el Device Flow. Maneja NotConfigured y errores de red."""

        # Si el usuario tipeó un client_id ad-hoc, persistirlo antes.
        cid = self._client_id_field.text().strip()
        if cid:
            GitHubAuthService.set_client_id(cid)

        try:
            info = GitHubAuthService.start_device_flow()
        except NotConfiguredError:
            self._wait_status.setText(
                t("github.login.not_configured"))
            return
        except GitHubAuthError as exc:
            self._wait_status.setText(
                t("github.login.network_error", error=str(exc)))
            return

        self._device_info = info
        self._user_code_label.setText(info.user_code)
        self._wait_status.setText(t("github.login.waiting"))
        self._stack.setCurrentIndex(self.PAGE_WAITING)
        self._retranslate()    # actualiza botones de la nueva página

        self._start_polling_thread(info)

    def _start_polling_thread(self, info: DeviceCodeInfo) -> None:
        # QThread + worker movido al hilo: patrón clásico Qt para no
        # bloquear la UI mientras dormimos N segundos esperando GitHub.
        self._thread = QThread(self)
        self._worker = _PollWorker(info)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.succeeded.connect(self._on_poll_success)
        self._worker.failed.connect(self._on_poll_failed)
        # Cleanup chains
        self._worker.succeeded.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_thread)
        self._thread.start()

    def _on_wait_cancel(self) -> None:
        if self._worker is not None:
            self._worker.request_cancel()
        self.reject()

    def _on_open_browser(self) -> None:
        if self._device_info is None:
            return
        QDesktopServices.openUrl(QUrl(self._device_info.verification_uri))

    def _on_poll_success(self, token: str, profile: dict) -> None:
        GitHubAuthService.save_token(token)
        GitHubAuthService.save_profile(profile)
        # Rellenar página SUCCESS
        login = profile.get("login", "?")
        name = profile.get("name", "")
        self._success_body.setText(
            t("github.login.success_body",
              login=login, name=(name or login)))
        self._stack.setCurrentIndex(self.PAGE_SUCCESS)
        self._retranslate()
        self.logged_in.emit(profile)

    def _on_poll_failed(self, kind: str, message: str) -> None:
        key = {
            "denied":    "github.login.error_denied",
            "expired":   "github.login.error_expired",
            "network":   "github.login.network_error",
            "cancelled": "github.login.error_cancelled",
        }.get(kind, "github.login.error_unknown")
        self._wait_status.setText(t(key, error=message))

    def _cleanup_thread(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        if self._thread is not None:
            self._thread.deleteLater()
            self._thread = None

    # ------------------------------------------------------------------
    # i18n
    # ------------------------------------------------------------------
    def _retranslate(self) -> None:
        self._intro_heading.setText(t("github.login.intro_heading"))
        self._intro_body.setText(t("github.login.intro_body"))
        self._intro_cancel_btn.setText(t("github.login.btn_cancel"))
        self._intro_connect_btn.setText(t("github.login.btn_connect"))

        self._wait_heading.setText(t("github.login.wait_heading"))
        self._wait_body.setText(t("github.login.wait_body"))
        self._wait_cancel_btn.setText(t("github.login.btn_cancel"))
        self._open_browser_btn.setText(t("github.login.btn_open_browser"))

        self._success_heading.setText(t("github.login.success_heading"))
        self._success_close_btn.setText(t("github.login.btn_close"))

        # Placeholder del campo client_id — i18n-able.
        if hasattr(self, "_client_id_field"):
            self._client_id_field.setPlaceholderText(
                t("github.login.client_id_placeholder"))

    # ------------------------------------------------------------------
    # Cerrar limpiamente
    # ------------------------------------------------------------------
    def closeEvent(self, event):  # noqa: N802
        if self._worker is not None:
            self._worker.request_cancel()
        super().closeEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key_Escape:
            self._on_wait_cancel() if (
                self._stack.currentIndex() == self.PAGE_WAITING
            ) else self.reject()
            return
        super().keyPressEvent(event)
