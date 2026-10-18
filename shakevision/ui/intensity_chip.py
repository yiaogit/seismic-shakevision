"""
Chip compacto de intensidad (MMI) para la cabecera global.

Sustituye visualmente a la tarjeta grande del Workbench: muestra en una
píldora de ~26 px el MMI actual y el PGV, con el color del nivel sísmico.
Está disponible en **ambos modos** (Estándar / Profesional) porque vive en
``AppHeader``; un clic abre el Workbench en vivo para ver el detalle.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QWidget,
)

from shakevision.i18n import LocaleService, t
from shakevision.processing.intensity import IntensitySnapshot
from shakevision.ui.signal_safety import subscribe


class IntensityChip(QFrame):
    """Píldora MMI/PGV de la cabecera (oculta hasta recibir datos)."""

    clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("IntensityChip")
        self.setFrameShape(QFrame.NoFrame)
        self.setFixedHeight(26)
        self.setMinimumWidth(168)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.setVisible(False)

        self._snap: Optional[IntensitySnapshot] = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 10, 0)
        layout.setSpacing(6)

        self._bar = QFrame(self)
        self._bar.setObjectName("IntensityChipBar")
        self._bar.setFixedSize(4, 14)
        layout.addWidget(self._bar)

        self._label = QLabel("MMI —", self)
        self._label.setObjectName("IntensityChipText")
        layout.addWidget(self._label)

        self._value = QLabel("", self)
        self._value.setObjectName("IntensityChipValue")
        layout.addWidget(self._value)

        # Los hijos no deben tragarse el clic: toda la píldora abre el
        # Workbench, no solo el borde.
        for child in (self._bar, self._label, self._value):
            child.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        self._apply_style()
        subscribe(self, LocaleService.language_changed_signal(),
                  self._retranslate)
        from shakevision.ui.theme_manager import ThemeManager
        subscribe(self, ThemeManager.changed_signal(), self._apply_style)

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------
    def set_snapshot(self, snap: Optional[IntensitySnapshot]) -> None:
        """Actualiza (o limpia, con ``None``) el chip."""

        previous_level = self._snap.level.mmi if self._snap is not None else None
        self._snap = snap
        if snap is None:
            self.setVisible(False)
            self._label.setText("MMI —")
            self._value.clear()
            return

        self._label.setText(f"MMI {snap.mmi:.1f}")
        self._value.setText(f"{snap.pgv_cm_s:.3g} cm/s")
        self._update_tooltip()
        # Re-aplicar QSS en cada frame sería caro (30 Hz): solo cambia cuando
        # cambia el nivel MMI; el tema se re-aplica por su propia señal.
        if snap.level.mmi != previous_level:
            self._apply_style()
        self.setVisible(True)

    def snapshot(self) -> Optional[IntensitySnapshot]:
        return self._snap

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------
    def _retranslate(self) -> None:
        if self._snap is not None:
            self._label.setText(f"MMI {self._snap.mmi:.1f}")
            self._update_tooltip()

    def _update_tooltip(self) -> None:
        snap = self._snap
        if snap is None:
            self.setToolTip("")
            return
        self.setToolTip(
            t("intensity.chip_tooltip",
              level=t(f"intensity.level.{snap.level.mmi}"),
              mmi=f"{snap.mmi:.1f}",
              pgv=f"{snap.pgv_cm_s:.3g}")
            + "\n" + t("intensity.chip_open_hint"))

    def _apply_style(self) -> None:
        from shakevision.ui import theme as _t

        color = (self._snap.level.color if self._snap is not None
                 else _t.COLOR_TEXT_MUTED)
        self.setStyleSheet(f"""
        QFrame#IntensityChip {{
            background-color: {_t.COLOR_PANEL_ELEVATED};
            border: 1px solid {_t.COLOR_PANEL_BORDER};
            border-radius: 13px;
        }}
        QFrame#IntensityChip:hover {{
            border-color: {_t.COLOR_ACCENT};
        }}
        QFrame#IntensityChipBar {{
            background-color: {color};
            border-radius: 2px;
        }}
        QLabel#IntensityChipText {{
            color: {_t.COLOR_TEXT_PRIMARY};
            font-family: {_t.FONT_STACK_SANS};
            font-size: 11px;
            font-weight: 600;
        }}
        QLabel#IntensityChipValue {{
            color: {_t.COLOR_TEXT_SECONDARY};
            font-family: {_t.FONT_STACK_MONO};
            font-size: 10px;
        }}
        """)

    # ------------------------------------------------------------------
    def mousePressEvent(self, event) -> None:  # noqa: N802 (API Qt)
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)
