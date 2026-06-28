"""
Enriquecimiento geográfico **offline** de sismos: región sísmica
Flinn–Engdahl + país, para habilitar búsqueda multilingüe en el Centro de
eventos (ver ``docs/events-i18n-timezone.md``).

Dependencias aisladas
---------------------
Tres piezas opcionales/pesadas se aíslan tras funciones con *fallback* a
``None`` para que el resto de la app —y la suite de tests pura— sigan
funcionando aunque falten (el sandbox del asistente NO tiene ``obspy`` ni
``reverse_geocoder``):

  * ``obspy.geodetics.flinnengdahl`` → número + nombre EN de la región FE
    (cobertura global incl. océanos). Ya es dependencia dura de la app.
  * ``reverse_geocoder`` → ISO de país desde lat/lon (solo tierra, offline).
  * ``babel`` (CLDR) → nombre del país **localizado** en es/fr/zh/… de forma
    autoritativa (sin traducción manual).

Todas las búsquedas se cachean (``lru_cache``) sobre coordenadas redondeadas
para amortizar el coste cuando el feed trae cientos de sismos.
"""

from __future__ import annotations

import functools
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Redondeo de coordenadas para la clave de caché (≈1 km a ecuador con 2 dec).
_COORD_NDIGITS = 2


# ---------------------------------------------------------------------------
# Flinn–Engdahl (obspy)
# ---------------------------------------------------------------------------
@functools.lru_cache(maxsize=1)
def _fe_engine():
    """Instancia perezosa de ``FlinnEngdahl`` o ``None`` si falta obspy."""

    try:
        from obspy.geodetics.flinnengdahl import FlinnEngdahl
    except Exception as exc:  # noqa: BLE001
        logger.debug("obspy no disponible — región FE deshabilitada: %s", exc)
        return None
    try:
        return FlinnEngdahl()
    except Exception as exc:  # noqa: BLE001
        logger.debug("FlinnEngdahl() falló: %s", exc)
        return None


@functools.lru_cache(maxsize=8192)
def fe_region(lat: float, lon: float) -> Optional[Tuple[int, str]]:
    """``(número_región_FE, nombre_EN)`` para una coordenada, o ``None``.

    El número (1–757) es **independiente del idioma**; el nombre EN sirve de
    etiqueta científica y de campo buscable en inglés. Devuelve ``None`` si
    obspy no está instalado o la consulta falla.
    """

    engine = _fe_engine()
    if engine is None:
        return None
    try:
        latr = round(float(lat), _COORD_NDIGITS)
        lonr = round(float(lon), _COORD_NDIGITS)
        number = int(engine.get_number_from_lonlat(lonr, latr))
        name = str(engine.get_region_by_number(number))
        return number, name
    except Exception as exc:  # noqa: BLE001
        logger.debug("FE lookup (%s,%s) falló: %s", lat, lon, exc)
        return None


# ---------------------------------------------------------------------------
# País (reverse_geocoder → ISO) + localización (babel/CLDR)
# ---------------------------------------------------------------------------
@functools.lru_cache(maxsize=8192)
def country_iso(lat: float, lon: float) -> Optional[str]:
    """Código ISO-3166 alpha-2 del país de la coordenada, o ``None``.

    Offline vía ``reverse_geocoder`` (DB de ciudades empaquetada). Para
    epicentros en el océano devuelve el país de la ciudad más cercana, lo cual
    puede ser engañoso; el llamador debería preferir ``fe_region`` para el mar.
    Devuelve ``None`` si la librería no está instalada.
    """

    try:
        import reverse_geocoder as rg
    except Exception as exc:  # noqa: BLE001
        logger.debug("reverse_geocoder no disponible: %s", exc)
        return None
    try:
        latr = round(float(lat), _COORD_NDIGITS)
        lonr = round(float(lon), _COORD_NDIGITS)
        hit = rg.search((latr, lonr), mode=1)  # mode=1 = un solo hilo
        if hit:
            cc = (hit[0].get("cc") or "").strip().upper()
            return cc or None
    except Exception as exc:  # noqa: BLE001
        logger.debug("reverse_geocoder (%s,%s) falló: %s", lat, lon, exc)
    return None


@functools.lru_cache(maxsize=2048)
def localized_country_name(iso: str, locale: str) -> Optional[str]:
    """Nombre del país en ``locale`` (es/fr/zh/en) desde CLDR vía babel.

    ``localized_country_name("JP", "zh") -> "日本"``. Si babel falta o el ISO
    es desconocido, devuelve el propio ISO como último recurso (mejor que
    nada para buscar). ``None`` solo si ``iso`` viene vacío.
    """

    if not iso:
        return None
    code = iso.strip().upper()
    try:
        from babel import Locale
        name = Locale.parse(locale).territories.get(code)
        if name:
            return name
    except Exception as exc:  # noqa: BLE001
        logger.debug("babel localización país %s/%s falló: %s", code, locale, exc)
    return code


def search_fields_for(
    lat: float,
    lon: float,
    locale: str,
    *,
    place: str = "",
) -> list[str]:
    """Construye la lista de cadenas buscables (localizadas) de un sismo.

    Combina: ``place`` EN (USGS) + nombre EN de región FE + nombre de país
    localizado + ISO. Pensado para inyectarse como ``extra_text`` en
    ``processing.event_filter.filter_quakes``. Robusto: cualquier pieza
    ausente simplemente se omite.
    """

    fields: list[str] = []
    if place:
        fields.append(place)
    fe = fe_region(lat, lon)
    if fe is not None:
        fields.append(fe[1])
    iso = country_iso(lat, lon)
    if iso:
        fields.append(iso)
        loc_name = localized_country_name(iso, locale)
        if loc_name and loc_name != iso:
            fields.append(loc_name)
    return fields
