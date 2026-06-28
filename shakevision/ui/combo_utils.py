"""Utilidad de dimensionado de ``QComboBox`` consciente del idioma.

Problema: el popup de un combo toma por defecto el ancho del propio control,
así que un ítem traducido más largo que la selección actual (o que aparece solo
en otro idioma) se recorta — p. ej. "全部" en el selector de magnitud mínima del
Centro de eventos.

Solución: medir el texto MÁS LARGO entre TODOS los idiomas soportados y fijar
con él el ancho mínimo del combo y de su popup. Como la medida considera los 4
idiomas, el resultado es estable: cambiar de idioma nunca recorta y no hace
falta recalcular en cada cambio.
"""

from __future__ import annotations

from typing import Optional, Sequence

from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QComboBox

from shakevision.i18n.service import LocaleService

# Holgura horizontal: columna del check del popup + márgenes del ítem + flecha
# del combo + posible barra de scroll. Generosa a propósito porque la fuente
# real puede venir de QSS y no reflejarse del todo en ``combo.font()``.
_PADDING_PX = 46
# Tope del ancho del CUERPO (combo cerrado) para que un ítem largo no monopolice
# una fila estrecha; el POPUP sí puede crecer por encima de este tope.
_MAX_BODY_PX = 360


def fit_combo(
    combo: QComboBox,
    i18n_keys: Optional[Sequence[str]] = None,
    extra: Optional[Sequence[str]] = None,
    max_body_px: int = _MAX_BODY_PX,
) -> None:
    """Dimensiona ``combo`` y su popup al texto más largo entre idiomas.

    Parámetros
    ----------
    combo
        El ``QComboBox`` a ajustar.
    i18n_keys
        Claves i18n de los ítems traducidos. Se mide su valor en los 4
        idiomas (cubre combos cuyos ítems cambian con el idioma: "全部" /
        "Any" / "Quelconque"…).
    extra
        Literales adicionales a considerar (p. ej. plantillas de ancho fijo
        que aún no estén entre los ítems).
    max_body_px
        Tope del ancho del cuerpo del combo cerrado.

    El ancho de los ítems ACTUALES siempre se mide — eso cubre los combos con
    datos no traducibles (estaciones, husos horarios, nombres de región).
    """

    try:
        fm = QFontMetrics(combo.font())
        samples: list[str] = [combo.itemText(i) for i in range(combo.count())]
        if i18n_keys:
            for key in i18n_keys:
                samples += LocaleService.all_translations(key)
        if extra:
            samples += list(extra)
        samples = [s for s in samples if s]
        if not samples:
            return
        width = max(fm.horizontalAdvance(s) for s in samples) + _PADDING_PX
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        view = combo.view()
        if view is not None:
            view.setMinimumWidth(width)
        combo.setMinimumWidth(min(width, max_body_px))
    except Exception:  # noqa: BLE001 — medir texto nunca debe romper la UI
        pass
