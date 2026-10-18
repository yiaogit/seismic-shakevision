"""
Barra de alcance ("scope bar") para las pestañas de nivel superior.

Aclara la división de responsabilidades que pedía el UX review P2:

* **Datos** = visión agregada (gráficas, KPIs, análisis por región/ventana).
* **Eventos** = revisión evento a evento (tabla, estación cercana, Workbench).

Cada barra muestra un título, una frase de alcance y un botón que salta a la
otra vista, para que el usuario no tenga que adivinar dónde está cada cosa.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from shakevision.i18n import LocaleService, t
from shakevision.ui.signal_safety import subscribe


class ScopeBar(QFrame):
    """Título + explicación de alcance + enlace a la vista complementaria."""

    link_clicked = Signal()

    def __init__(self, title_key: str, hint_key: str, link_key: str,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("ScopeBar")
        self.setFrameShape(QFrame.NoFrame)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._title_key = title_key
        self._hint_key = hint_key
        self._link_key = link_key

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(10)

        self._title = QLabel()
        self._title.setObjectName("SectionTitle")
        layout.addWidget(self._title)

        self._hint = QLabel()
        self._hint.setObjectName("Caption")
        self._hint.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout.addWidget(self._hint, stretch=1)

        self._link = QPushButton()
        self._link.setObjectName("ChipButton")
        self._link.setFixedHeight(22)
        self._link.clicked.connect(self.link_clicked.emit)
        layout.addWidget(self._link)

        self._retranslate()
        subscribe(self, LocaleService.language_changed_signal(),
                  self._retranslate)

    def _retranslate(self) -> None:
        self._title.setText(t(self._title_key))
        self._hint.setText(t(self._hint_key))
        self._link.setText(t(self._link_key))
