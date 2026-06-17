"""Lógica pura de "periodos" (ventanas temporales) — sin Qt ni i18n.

v0.7.7 (O2). Extraído de ``MainWindow`` para que el mapeo periodo→segundos
y el filtrado de sismos por ventana temporal sean funciones puras,
testeables sin un ``QApplication``.

Los nombres de periodo (``"all_hour"``, ``"all_day"`` …) son los mismos que
emiten el globo y el dashboard. La etiqueta i18n del periodo sigue
resolviéndose en la UI (depende de ``t()``), no aquí.
"""

from __future__ import annotations

import time
from typing import Iterable, Optional

# Nombre de periodo → segundos de ventana.
PERIOD_SECONDS: dict[str, int] = {
    "all_hour":  3600,
    "all_6h":    6 * 3600,
    "all_day":   86_400,
    "all_week":  7 * 86_400,
    "all_month": 30 * 86_400,
}

# Periodo por defecto cuando el nombre es desconocido (1 día).
_DEFAULT_SECONDS = 86_400


def period_seconds(period: str) -> int:
    """Segundos de la ventana ``period`` (``86_400`` si es desconocido)."""

    return PERIOD_SECONDS.get(period, _DEFAULT_SECONDS)


def filter_for_period(
    quakes: Iterable,
    period: str,
    now: Optional[float] = None,
) -> list:
    """Sismos cuyo ``timestamp_unix`` cae dentro de la ventana ``period``.

    Args:
        quakes: iterable de objetos con atributo ``timestamp_unix`` (s).
        period: nombre de periodo (ver ``PERIOD_SECONDS``).
        now: epoch en segundos; por defecto ``time.time()`` (inyectable
            para tests deterministas).
    """

    if now is None:
        now = time.time()
    cutoff = now - period_seconds(period)
    return [q for q in quakes if q.timestamp_unix >= cutoff]
