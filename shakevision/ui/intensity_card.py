"""
Tarjeta de "intensidad sentida" — pensada para usuarios no especialistas.

En lugar de mostrar números crudos (PGV en cm/s, ratio STA/LTA, dB,
etc.), esta tarjeta traduce el movimiento del suelo de los últimos
60 segundos a una etiqueta humana inmediata: "Imperceptible",
"Débil", "Moderado", "Fuerte"… acompañada de un fondo coloreado
acorde a la escala MMI y de un valor numérico secundario para el
usuario que sí quiere mirar la cifra.

Diseño visual
-------------
┌──────────────────────────────────────────────────────────┐
│  🌐 Intensidad sentida                                   │
│                                                          │
│  ▴  IV   Ligero                                          │
│         La mayoría lo siente; cristalería tintinea.      │
│                                                          │
│         PGV 1.84 cm/s   ·   MMI 4.2 (Mercalli mod.)      │
└──────────────────────────────────────────────────────────┘

El color del recuadro lateral izquierdo refleja la intensidad MMI
actual (gris para "imperceptible", amarillo para "fuerte", rojo
para "muy fuerte/severo", negro para "devastador").
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from shakevision.i18n import LocaleService, t
from shakevision.processing.intensity import (
    INTENSITY_LEVELS,
    IntensityLevel,
    IntensitySnapshot,
)
from shakevision.ui.theme import (
    FONT_STACK_MONO,
    FONT_STACK_SANS,
)


# Numerales romanos del 1 al 12 (convención clásica de la escala MMI)
_ROMAN_NUMERALS: dict[int, str] = {
    1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI",
    7: "VII", 8: "VIII", 9: "IX", 10: "X", 11: "XI", 12: "XII",
}


class IntensityCard(QFrame):
    """Tarjeta compacta y siempre visible que traduce PGV a MMI."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("IntensityCard")
        self.setFrameShape(QFrame.NoFrame)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.setFixedHeight(112)

        # Aplicamos un QSS local (no global) para no tener que tocar theme.py
        self._apply_local_qss(initial_color=INTENSITY_LEVELS[1].color)

        # Layout principal: barra de color a la izquierda + texto a la derecha
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ----- Barra lateral coloreada (refleja MMI) -----
        self._color_bar = QFrame(self)
        self._color_bar.setObjectName("IntensityBar")
        self._color_bar.setFixedWidth(8)
        root.addWidget(self._color_bar)

        # ----- Bloque de texto -----
        text_container = QWidget(self)
        text_layout = QVBoxLayout(text_container)
        text_layout.setContentsMargins(16, 12, 16, 12)
        text_layout.setSpacing(2)

        # Estado interno: nivel + snapshot actuales, para poder
        # re-renderizar tras cambio de idioma sin perder los valores.
        self._current_level: IntensityLevel = INTENSITY_LEVELS[1]
        self._current_snap: Optional[IntensitySnapshot] = None

        # Cabecera "INTENSIDAD SENTIDA"
        self._header_label = QLabel(t("intensity.title"))
        self._header_label.setObjectName("IntensityHeader")
        text_layout.addWidget(self._header_label)

        # Fila principal: número romano + etiqueta corta
        main_row = QHBoxLayout()
        main_row.setSpacing(14)
        main_row.setContentsMargins(0, 4, 0, 0)

        self._roman_label = QLabel("I")
        self._roman_label.setObjectName("IntensityRoman")
        self._roman_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        main_row.addWidget(self._roman_label)

        self._title_label = QLabel(t("intensity.level.1"))
        self._title_label.setObjectName("IntensityTitle")
        self._title_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        main_row.addWidget(self._title_label, stretch=1)

        text_layout.addLayout(main_row)

        # Descripción de una línea
        self._desc_label = QLabel(t("intensity.desc.1"))
        self._desc_label.setObjectName("IntensityDesc")
        self._desc_label.setWordWrap(True)
        text_layout.addWidget(self._desc_label)

        # Línea métrica (PGV + MMI numérico)
        self._metric_label = QLabel(t("intensity.metric_empty"))
        self._metric_label.setObjectName("IntensityMetric")
        text_layout.addWidget(self._metric_label)

        root.addWidget(text_container, stretch=1)

        # Suscribirse a cambios de idioma para retraducir en caliente
        LocaleService.language_changed_signal().connect(self._retranslate)

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def update_from_snapshot(self, snap: IntensitySnapshot) -> None:
        """Refresca los textos y el color en función de un snapshot."""

        self._current_level = snap.level
        self._current_snap = snap
        mmi = snap.level.mmi
        self._set_level(snap.level)
        self._roman_label.setText(_ROMAN_NUMERALS[mmi])
        self._title_label.setText(t(f"intensity.level.{mmi}"))
        self._desc_label.setText(t(f"intensity.desc.{mmi}"))
        self._metric_label.setText(
            t("intensity.metric", pgv=snap.pgv_cm_s, mmi=snap.mmi)
        )

    def reset(self) -> None:
        """Vuelve al estado "imperceptible" (al desconectar fuente)."""

        self._current_level = INTENSITY_LEVELS[1]
        self._current_snap = None
        self._set_level(self._current_level)
        self._roman_label.setText(_ROMAN_NUMERALS[1])
        self._title_label.setText(t("intensity.level.1"))
        self._desc_label.setText(t("intensity.desc.1"))
        self._metric_label.setText(t("intensity.metric_empty"))

    def _retranslate(self) -> None:
        """Reaplica las cadenas traducidas al cambiar de idioma."""

        self._header_label.setText(t("intensity.title"))
        mmi = self._current_level.mmi
        self._title_label.setText(t(f"intensity.level.{mmi}"))
        self._desc_label.setText(t(f"intensity.desc.{mmi}"))
        if self._current_snap is not None:
            self._metric_label.setText(
                t("intensity.metric",
                  pgv=self._current_snap.pgv_cm_s,
                  mmi=self._current_snap.mmi)
            )
        else:
            self._metric_label.setText(t("intensity.metric_empty"))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _set_level(self, level: IntensityLevel) -> None:
        """Cambia el color de la barra lateral y el matiz del fondo.

        v0.6: lee colores del theme dinámicamente — al cambiar de tema,
        la subscripción a ThemeManager.changed_signal llama de nuevo a
        _set_level (vía _on_theme_changed), garantizando que el tinte
        y el borde se recalculen con la paleta nueva.
        """

        from shakevision.ui import theme as _t

        bar_qss = (
            f"QFrame#IntensityBar {{ background-color: {level.color}; "
            f"border-top-left-radius: 10px; border-bottom-left-radius: 10px; }}"
        )
        # 92 % panel + 8 % nivel = tinte sutil sin perder legibilidad
        tint = self._mix_color(_t.COLOR_PANEL, level.color, weight=0.08)
        card_qss = (
            f"QFrame#IntensityCard {{ background-color: {tint}; "
            f"border: 1px solid {_t.COLOR_PANEL_BORDER}; "
            f"border-radius: 10px; }}"
        )
        self.setStyleSheet(self._build_base_qss() + bar_qss + card_qss)

    def _on_theme_changed(self, _theme: str) -> None:
        """Slot conectado a ThemeManager.changed_signal."""

        self._set_level(self._current_level)

    def _apply_local_qss(self, initial_color: str) -> None:
        """Configura el QSS inicial y la subscripción al cambio de tema."""

        self._set_level(INTENSITY_LEVELS[1])
        # v0.6: re-pintar al cambiar tema
        try:
            from shakevision.ui.theme_manager import ThemeManager
            ThemeManager.changed_signal().connect(self._on_theme_changed)
        except Exception:  # noqa: BLE001
            pass

    def _build_base_qss(self) -> str:
        """Genera el QSS de los labels leyendo del módulo theme en runtime."""

        from shakevision.ui import theme as _t
        return f"""
        QLabel#IntensityHeader {{
            color: {_t.COLOR_TEXT_SECONDARY};
            font-family: {FONT_STACK_SANS};
            font-size: 10px;
            font-weight: 600;
            letter-spacing: 1.2px;
            text-transform: uppercase;
        }}
        QLabel#IntensityRoman {{
            color: {_t.COLOR_TEXT_PRIMARY};
            font-family: {FONT_STACK_SANS};
            font-size: 36px;
            font-weight: 800;
            min-width: 56px;
        }}
        QLabel#IntensityTitle {{
            color: {_t.COLOR_TEXT_PRIMARY};
            font-family: {FONT_STACK_SANS};
            font-size: 22px;
            font-weight: 600;
        }}
        QLabel#IntensityDesc {{
            color: {_t.COLOR_TEXT_SECONDARY};
            font-family: {FONT_STACK_SANS};
            font-size: 12px;
            padding-top: 2px;
        }}
        QLabel#IntensityMetric {{
            color: {_t.COLOR_TEXT_MUTED};
            font-family: {FONT_STACK_MONO};
            font-size: 11px;
            padding-top: 4px;
        }}
        """

    @staticmethod
    def _mix_color(hex_a: str, hex_b: str, weight: float) -> str:
        """Mezcla dos colores hex (0–1 = peso de B) y devuelve hex."""

        a = QColor(hex_a)
        b = QColor(hex_b)
        w = max(0.0, min(1.0, weight))
        return QColor(
            round(a.red()   * (1 - w) + b.red()   * w),
            round(a.green() * (1 - w) + b.green() * w),
            round(a.blue()  * (1 - w) + b.blue()  * w),
        ).name()
