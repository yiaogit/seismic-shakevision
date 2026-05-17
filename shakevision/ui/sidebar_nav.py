"""
Barra lateral de navegación principal (estilo VS Code / Linear).

Reemplaza al ``QTabWidget`` clásico por una columna estrecha de iconos
en el borde izquierdo del cuerpo. Cada icono representa una vista
principal (tiempo real, helicorder, hodograma, ajustes…). El widget
emite ``current_changed(int)`` cuando el usuario cambia de vista; la
ventana principal lo conecta a un ``QStackedWidget``.

Decisiones visuales
-------------------
* 64 px de ancho fijo, alto expandible.
* Cada botón ocupa 56 × 56 px y muestra un emoji centrado + una
  etiqueta corta debajo (similar a Discord / Slack).
* El elemento activo lleva una franja vertical azul de 3 px en el
  borde izquierdo y un fondo ligeramente más claro.
* Tooltip con el nombre largo al pasar el ratón.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from shakevision.ui.theme import (
    COLOR_ACCENT,
    COLOR_PANEL,
    COLOR_PANEL_BORDER,
    COLOR_PANEL_ELEVATED,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    FONT_STACK_SANS,
)


SIDEBAR_WIDTH_PX: int = 72
BUTTON_HEIGHT_PX: int = 60


@dataclass(frozen=True)
class NavItem:
    """Definición declarativa de un elemento de navegación."""

    icon: str         # Emoji o carácter Unicode
    label: str        # Texto corto (≤ 8 caracteres) bajo el icono
    tooltip: str      # Texto completo del tooltip


class SidebarNav(QFrame):
    """Barra lateral de navegación principal."""

    current_changed = Signal(int)

    def __init__(
        self,
        items: list[NavItem],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("SidebarNav")
        self.setFrameShape(QFrame.NoFrame)
        self.setFixedWidth(SIDEBAR_WIDTH_PX)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.setStyleSheet(self._build_qss())

        self._items = list(items)
        self._buttons: list[QPushButton] = []

        # QButtonGroup nos da exclusividad gratis (un solo botón
        # "checked" a la vez).
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 12)
        layout.setSpacing(4)

        # Crear un botón por cada elemento
        for index, item in enumerate(items):
            btn = self._make_nav_button(item)
            btn.toggled.connect(lambda checked, i=index: self._on_button_toggled(i, checked))
            self._group.addButton(btn, index)
            self._buttons.append(btn)
            layout.addWidget(btn)

        # Empujar todo arriba; los botones secundarios (settings) se
        # añaden después con add_secondary_item.
        layout.addStretch(1)

        self._secondary_layout = layout  # para añadir items abajo más tarde

        # Activar el primer botón por defecto
        if self._buttons:
            self._buttons[0].setChecked(True)

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def current_index(self) -> int:
        return self._group.checkedId()

    def set_current_index(self, index: int) -> None:
        if 0 <= index < len(self._buttons):
            self._buttons[index].setChecked(True)

    def add_secondary_item(self, item: NavItem) -> int:
        """Añade un elemento al final (típicamente "Ajustes")."""

        btn = self._make_nav_button(item)
        index = len(self._buttons)
        btn.toggled.connect(lambda checked, i=index: self._on_button_toggled(i, checked))
        self._group.addButton(btn, index)
        self._buttons.append(btn)
        # Insertar antes del stretch final (que está al final)
        self._secondary_layout.insertWidget(self._secondary_layout.count() - 1, btn)
        return index

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------
    def _make_nav_button(self, item: NavItem) -> QPushButton:
        """Crea un botón con icono arriba y etiqueta corta debajo."""

        btn = QPushButton(f"{item.icon}\n{item.label}")
        btn.setObjectName("SidebarButton")
        btn.setCheckable(True)
        btn.setAutoExclusive(False)  # gestionado por QButtonGroup
        btn.setFixedHeight(BUTTON_HEIGHT_PX)
        btn.setToolTip(item.tooltip)
        return btn

    def _on_button_toggled(self, index: int, checked: bool) -> None:
        if checked:
            self.current_changed.emit(index)

    @staticmethod
    def _build_qss() -> str:
        return f"""
        QFrame#SidebarNav {{
            background-color: {COLOR_PANEL};
            border-right: 1px solid {COLOR_PANEL_BORDER};
        }}

        QPushButton#SidebarButton {{
            background-color: transparent;
            color: {COLOR_TEXT_SECONDARY};
            border: none;
            border-left: 3px solid transparent;
            border-radius: 0px;
            font-family: {FONT_STACK_SANS};
            font-size: 10px;
            font-weight: 500;
            text-align: center;
            padding-top: 6px;
            padding-bottom: 6px;
        }}

        QPushButton#SidebarButton:hover {{
            background-color: {COLOR_PANEL_ELEVATED};
            color: {COLOR_TEXT_PRIMARY};
        }}

        QPushButton#SidebarButton:checked {{
            background-color: {COLOR_PANEL_ELEVATED};
            color: {COLOR_TEXT_PRIMARY};
            border-left: 3px solid {COLOR_ACCENT};
        }}
        """
