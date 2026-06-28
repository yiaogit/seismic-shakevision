"""
Presets de **región** para acotar la búsqueda histórica (fdsnws-event).

Como el catálogo histórico no admite búsqueda por nombre de lugar, la región
se acota con una **caja geográfica** (min/max lat-lon). Aquí mantenemos una
lista curada de países sísmicamente relevantes con su caja (redondeada con
generosidad — es para acotar, no para precisión cartográfica) más la opción
"Global" (sin caja).

Los **nombres** se localizan vía ``babel``/CLDR a partir del ISO (igual que en
``services/geo_region.py``), así no mantenemos traducciones a mano. Solo
``region.global`` es una clave i18n propia.

Caja: ``(min_lat, max_lat, min_lon, max_lon)``.
"""

from __future__ import annotations

import logging
from typing import Final, Optional

from shakevision.i18n import t

logger = logging.getLogger(__name__)

#: Sentinela para "sin restricción de región".
GLOBAL: Final[str] = "__global__"

#: ISO-3166 alpha-2 → caja ``(min_lat, max_lat, min_lon, max_lon)``.
COUNTRY_BBOX: Final[dict[str, tuple[float, float, float, float]]] = {
    "JP": (24.0, 46.0, 122.0, 146.0),
    "CL": (-56.0, -17.0, -76.0, -66.0),
    "PE": (-18.5, 0.0, -82.0, -68.0),
    "EC": (-5.0, 2.0, -81.0, -75.0),
    "MX": (14.0, 33.0, -118.0, -86.0),
    "US": (24.0, 50.0, -125.0, -66.0),
    "ID": (-11.0, 6.0, 95.0, 141.0),
    "PH": (5.0, 20.0, 117.0, 127.0),
    "NZ": (-47.0, -34.0, 166.0, 179.0),
    "PG": (-12.0, 0.0, 140.0, 156.0),
    "TR": (36.0, 42.0, 26.0, 45.0),
    "GR": (34.0, 42.0, 19.0, 28.0),
    "IT": (36.0, 47.0, 6.0, 19.0),
    "IS": (63.0, 67.0, -25.0, -13.0),
    "IR": (25.0, 40.0, 44.0, 64.0),
    "AF": (29.0, 39.0, 60.0, 75.0),
    "PK": (23.0, 37.0, 60.0, 78.0),
    "NP": (26.0, 31.0, 80.0, 89.0),
    "IN": (6.0, 36.0, 68.0, 98.0),
    "CN": (18.0, 54.0, 73.0, 135.0),
    "TW": (21.0, 26.0, 119.0, 123.0),
}

#: Orden de presentación (Global primero, luego países sísmicamente relevantes).
PRESET_ORDER: Final[tuple[str, ...]] = (
    GLOBAL,
    "JP", "CL", "US", "MX", "ID", "PH", "NZ", "TR", "GR", "IT",
    "IR", "CN", "TW", "NP", "IN", "PE", "EC", "PK", "AF", "PG", "IS",
)

#: Nombres localizados de la lista curada (en/es/fr/zh). Built-in para NO
#: depender de babel en runtime: si babel no resuelve (o no está instalado),
#: igual mostramos un nombre legible en vez del código ISO crudo.
LOCAL_NAMES: Final[dict[str, dict[str, str]]] = {
    "JP": {"en": "Japan", "es": "Japón", "fr": "Japon", "zh": "日本"},
    "CL": {"en": "Chile", "es": "Chile", "fr": "Chili", "zh": "智利"},
    "PE": {"en": "Peru", "es": "Perú", "fr": "Pérou", "zh": "秘鲁"},
    "EC": {"en": "Ecuador", "es": "Ecuador", "fr": "Équateur", "zh": "厄瓜多尔"},
    "MX": {"en": "Mexico", "es": "México", "fr": "Mexique", "zh": "墨西哥"},
    "US": {"en": "United States", "es": "Estados Unidos",
           "fr": "États-Unis", "zh": "美国"},
    "ID": {"en": "Indonesia", "es": "Indonesia",
           "fr": "Indonésie", "zh": "印度尼西亚"},
    "PH": {"en": "Philippines", "es": "Filipinas",
           "fr": "Philippines", "zh": "菲律宾"},
    "NZ": {"en": "New Zealand", "es": "Nueva Zelanda",
           "fr": "Nouvelle-Zélande", "zh": "新西兰"},
    "PG": {"en": "Papua New Guinea", "es": "Papúa Nueva Guinea",
           "fr": "Papouasie-Nouvelle-Guinée", "zh": "巴布亚新几内亚"},
    "TR": {"en": "Türkiye", "es": "Turquía", "fr": "Turquie", "zh": "土耳其"},
    "GR": {"en": "Greece", "es": "Grecia", "fr": "Grèce", "zh": "希腊"},
    "IT": {"en": "Italy", "es": "Italia", "fr": "Italie", "zh": "意大利"},
    "IS": {"en": "Iceland", "es": "Islandia", "fr": "Islande", "zh": "冰岛"},
    "IR": {"en": "Iran", "es": "Irán", "fr": "Iran", "zh": "伊朗"},
    "AF": {"en": "Afghanistan", "es": "Afganistán",
           "fr": "Afghanistan", "zh": "阿富汗"},
    "PK": {"en": "Pakistan", "es": "Pakistán", "fr": "Pakistan", "zh": "巴基斯坦"},
    "NP": {"en": "Nepal", "es": "Nepal", "fr": "Népal", "zh": "尼泊尔"},
    "IN": {"en": "India", "es": "India", "fr": "Inde", "zh": "印度"},
    "CN": {"en": "China", "es": "China", "fr": "Chine", "zh": "中国"},
    "TW": {"en": "Taiwan", "es": "Taiwán", "fr": "Taïwan", "zh": "台湾"},
}


def bbox_for(key: str) -> Optional[tuple[float, float, float, float]]:
    """Caja de un preset, o ``None`` para Global (sin restricción)."""

    if key == GLOBAL:
        return None
    return COUNTRY_BBOX.get(key)


def display_name(key: str, locale: str = "en") -> str:
    """Nombre localizado del preset (built-in → babel → ISO; i18n para Global)."""

    if key == GLOBAL:
        return t("region.global")
    lang = (locale or "en").split("-")[0].split("_")[0]
    # 1) Tabla built-in (garantiza nombre legible sin depender de babel).
    entry = LOCAL_NAMES.get(key)
    if entry:
        return entry.get(lang) or entry.get("en") or key
    # 2) babel/CLDR si está disponible.
    try:
        from babel import Locale
        name = Locale.parse(locale).territories.get(key)
        if name:
            return name
    except Exception as exc:  # noqa: BLE001
        logger.debug("babel región %s/%s falló: %s", key, locale, exc)
    return key


def display_label(key: str, locale: str = "en") -> str:
    """Etiqueta para el desplegable: ``"CL · Chile"`` (Global sin código)."""

    if key == GLOBAL:
        return t("region.global")
    return f"{key} · {display_name(key, locale)}"


def presets(locale: str = "en") -> list[tuple[str, str]]:
    """``[(key, etiqueta "ISO · nombre"), …]`` en orden de presentación."""

    out = []
    for key in PRESET_ORDER:
        if key == GLOBAL or key in COUNTRY_BBOX:
            out.append((key, display_label(key, locale)))
    return out
