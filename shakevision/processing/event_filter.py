"""
Filtrado puro de sismos (sin Qt) — usado por la barra de filtros del Centro de
eventos y por "Mi colección".

Se mantiene libre de dependencias de UI a propósito: así la lógica de filtrado
(magnitud / profundidad / rango temporal / texto multilingüe) se puede probar
con pytest sin un ``QApplication`` (el sandbox del asistente no tiene Qt).

Búsqueda multilingüe
--------------------
La cadena ``place`` de USGS es texto inglés ("26 km W of Anchorage"). Para que
un usuario en chino/español/francés pueda buscar, el llamador pasa además los
nombres **localizados** de región/país (vocabulario cerrado, traducido aparte)
vía ``extra_text``. La consulta se compara contra TODOS esos campos a la vez,
tras una normalización que:

  * pasa a minúsculas,
  * pliega acentos (``"Japón" → "japon"``) para que coincida con o sin tilde,
  * tokeniza por espacios y exige que CADA token aparezca (AND) en algún campo.

Para CJK (中文/日本語) el plegado de acentos es un no-op y el substring funciona
directamente, así que "日本" coincide con el nombre de región/país localizado.
"""

from __future__ import annotations

import datetime as _dt
import unicodedata
from typing import Callable, Iterable, Optional, Sequence


def structured_tokens(
    *,
    eventid: str = "",
    magnitude: Optional[float] = None,
    timestamp_unix: Optional[float] = None,
    depth_km: Optional[float] = None,
) -> list[str]:
    """Cadenas buscables derivadas de los campos NO textuales de un sismo.

    Permite que el cuadro de búsqueda confirme un evento por ID, magnitud,
    año/fecha o profundidad — p. ej. ``"japan 6"``, ``"us7000abcd"``,
    ``"2011"``, ``"30km"``. Pensado para sumarse a los campos de
    ``search_fields_for``.
    """

    toks: list[str] = []
    if eventid:
        toks.append(str(eventid))
    if magnitude is not None:
        try:
            toks.append(f"m{float(magnitude):.1f}")
            toks.append(f"{float(magnitude):.1f}")
        except (TypeError, ValueError):
            pass
    if timestamp_unix is not None:
        try:
            dt = _dt.datetime.fromtimestamp(
                float(timestamp_unix), tz=_dt.timezone.utc)
            toks.append(dt.strftime("%Y"))
            toks.append(dt.strftime("%Y-%m-%d"))
        except (TypeError, ValueError, OSError, OverflowError):
            pass
    if depth_km is not None:
        try:
            toks.append(f"{float(depth_km):.0f}km")
        except (TypeError, ValueError):
            pass
    return toks


def fold(text: str) -> str:
    """Normaliza para comparar: minúsculas + sin acentos (combining marks).

    ``"Île-de-France" → "ile-de-france"``, ``"Japón" → "japon"``.
    CJK queda intacto (no tiene marcas combinantes que quitar).
    """

    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    no_marks = "".join(c for c in decomposed if not unicodedata.combining(c))
    return no_marks.casefold()


def _haystack(fields: Iterable[str]) -> str:
    return fold("   ".join(f for f in fields if f))


def text_matches(query: str, fields: Sequence[str]) -> bool:
    """¿Coinciden TODOS los tokens de ``query`` en alguno de los ``fields``?

    Vacío/espacios → siempre ``True`` (sin filtro de texto).
    """

    q = fold(query).strip()
    if not q:
        return True
    hay = _haystack(fields)
    return all(tok in hay for tok in q.split())


def passes(
    *,
    magnitude: float,
    timestamp_unix: float,
    place: str,
    depth_km: Optional[float] = None,
    min_mag: Optional[float] = None,
    max_mag: Optional[float] = None,
    min_depth: Optional[float] = None,
    max_depth: Optional[float] = None,
    t_from: Optional[float] = None,
    t_to: Optional[float] = None,
    query: str = "",
    extra_fields: Sequence[str] = (),
) -> bool:
    """Devuelve ``True`` si un sismo (sus campos sueltos) pasa los filtros.

    ``extra_fields`` son cadenas adicionales buscables (nombre de región /
    país localizados). El texto se compara contra ``place`` + ``extra_fields``.
    """

    m = float(magnitude)
    if min_mag is not None and m < float(min_mag):
        return False
    if max_mag is not None and m > float(max_mag):
        return False

    if depth_km is not None:
        d = float(depth_km)
        if min_depth is not None and d < float(min_depth):
            return False
        if max_depth is not None and d > float(max_depth):
            return False

    ts = float(timestamp_unix)
    if t_from is not None and ts < float(t_from):
        return False
    if t_to is not None and ts > float(t_to):
        return False

    fields = [place or "", *(extra_fields or ())]
    return text_matches(query, fields)


def filter_quakes(
    quakes,
    *,
    min_mag: Optional[float] = None,
    max_mag: Optional[float] = None,
    min_depth: Optional[float] = None,
    max_depth: Optional[float] = None,
    t_from: Optional[float] = None,
    t_to: Optional[float] = None,
    query: str = "",
    extra_text: Optional[Callable[[object], Sequence[str]]] = None,
):
    """Filtra una lista de objetos tipo ``Earthquake``.

    Cada elemento debe exponer ``magnitude``, ``timestamp_unix``, ``place`` y
    (opcional) ``depth_km``. Filtros (todos opcionales, AND): magnitud
    [min,max], profundidad [min,max], rango temporal ``[t_from, t_to]`` (epoch
    UTC) y texto multilingüe.

    ``extra_text(ev) -> [región_localizada, país_localizado, …]`` permite a la
    capa de UI inyectar nombres localizados sin acoplar este módulo a i18n.
    """

    out = []
    for ev in quakes:
        extra = tuple(extra_text(ev)) if extra_text is not None else ()
        if passes(
            magnitude=getattr(ev, "magnitude", 0.0),
            timestamp_unix=getattr(ev, "timestamp_unix", 0.0),
            place=getattr(ev, "place", "") or "",
            depth_km=getattr(ev, "depth_km", None),
            min_mag=min_mag, max_mag=max_mag,
            min_depth=min_depth, max_depth=max_depth,
            t_from=t_from, t_to=t_to, query=query,
            extra_fields=extra,
        ):
            out.append(ev)
    return out
