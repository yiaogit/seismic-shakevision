"""
ProfileDialog — wrapper modal del ProfileView (v0.5.3).

Por qué un diálogo y no un tab
-------------------------------
La v0.5.0 puso "Personal" como tercer tab junto a Globe y Data — pero
es una decisión de arquitectura cuestionable: el Profile es un destino
de *configuración / identidad*, no de *navegación de contenido*.
Compite con los modos de trabajo principales (vista de globo, vista de
datos) y diluye la jerarquía de la app.

Decisión v0.5.3: Profile pasa a ser un diálogo modal que se abre con el
botón 👤 de la AppHeader (igual que el botón ⚙ abre Settings). El tab
desaparece de la barra superior, dejando solo Globe y Data como
verdaderos destinos de navegación.

Diseño
------
* QDialog modal estándar, 720 × 560 px (suficiente para identidad +
  6 stat cards + 2 columnas de favoritos sin scroll).
* Encapsula la propia ``ProfileView`` (alfabéticamente probada en
  阶段 L) sin reescribir nada de su lógica.
* Botón "Cerrar" abajo a la derecha.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from shakevision.i18n import LocaleService, t
from shakevision.ui.profile_view import ProfileView
from shakevision.ui.signal_safety import subscribe


class ProfileDialog(QDialog):
    """Modal que envuelve ``ProfileView``."""

    # Re-emite la señal de ProfileView para que el caller pueda
    # abrir el diálogo de login GitHub.
    request_github_login = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("ProfileDialog")
        self.setModal(True)
        # Sin Qt.WindowMinimizeButtonHint / MaxButton — es un diálogo
        # de configuración, no una ventana funcional.
        self.setWindowFlag(Qt.WindowMinimizeButtonHint, False)
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, False)
        self.setMinimumSize(720, 580)

        # Layout: ProfileView ocupa todo, botón Close al pie
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._view = ProfileView(parent=self)
        # Reenviar la señal de login
        self._view.request_github_login.connect(self.request_github_login)
        root.addWidget(self._view, stretch=1)

        # Footer separator (hairline subtil — macOS sheet style)
        from PySide6.QtWidgets import QFrame as _QF
        sep = _QF()
        sep.setFrameShape(_QF.HLine)
        sep.setObjectName("ProfileDialogFooterSeparator")
        sep.setFixedHeight(1)
        root.addWidget(sep)

        # Botón Close estilo macOS dialog
        self._close_btn = QPushButton()
        self._close_btn.setObjectName("PrimaryButton")
        self._close_btn.setProperty("primary", True)
        self._close_btn.clicked.connect(self.accept)
        self._close_btn.setMinimumWidth(96)
        # Pequeño margen alrededor del botón
        from PySide6.QtWidgets import QWidget as _W, QHBoxLayout as _H
        footer = _W()
        footer.setObjectName("ProfileDialogFooter")
        f_layout = _H(footer)
        f_layout.setContentsMargins(20, 14, 20, 18)
        f_layout.addStretch(1)
        f_layout.addWidget(self._close_btn)
        root.addWidget(footer)

        # QSS local para que el footer y el separator se vean coherentes
        # con el tema activo. v0.6 Phase 14-fix: ahora se re-aplica al
        # cambiar tema (suscripción a ThemeManager.changed_signal abajo).
        self._refresh_themed_qss()
        # v0.7.7 (B1): subscribe() — disconnect en destroyed + guarda.
        from shakevision.ui.theme_manager import ThemeManager
        subscribe(self, ThemeManager.changed_signal(),
                  self._refresh_themed_qss)
        # v0.6: aplicar micro-animación al botón principal (hover/press
        # con fade ~150 ms estilo macOS, no el chasquido inmediato de QSS)
        try:
            from shakevision.ui.animations import attach_hover_press
            attach_hover_press(self._close_btn)
        except Exception:  # noqa: BLE001
            pass

        self._retranslate()
        subscribe(self, LocaleService.language_changed_signal(),
                  self._retranslate)  # v0.7.7 (B1)

    def _retranslate(self) -> None:
        self.setWindowTitle(t("profile.dialog_title"))
        self._close_btn.setText(t("profile.btn.close"))

    def _refresh_themed_qss(self) -> None:
        """Re-aplica el QSS local con los COLOR_* actuales del módulo
        theme. Se llama en __init__ y cada vez que ThemeManager cambia
        de tema, para que el footer y separator no se queden con el
        color del tema con el que se construyó el diálogo (lazy +
        persistente)."""

        try:
            from shakevision.ui import theme as _t
            self.setStyleSheet(f"""
            QFrame#ProfileDialogFooterSeparator {{
                background-color: {_t.COLOR_PANEL_BORDER};
                border: none;
            }}
            QWidget#ProfileDialogFooter {{
                background-color: {_t.COLOR_BACKGROUND};
            }}
            """)
            self.style().unpolish(self)
            self.style().polish(self)
        except Exception:  # noqa: BLE001
            pass

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        # Por si el tema cambió mientras el diálogo estaba oculto.
        self._refresh_themed_qss()

    # Conveniencia para el caller que quiera refrescar tras login.
    def refresh(self) -> None:
        self._view.refresh_all()
