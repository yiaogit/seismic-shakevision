"""
Modelos de datos compartidos por la capa de servicios.

Todos son ``frozen`` para que sean hashables y se puedan usar como
clave en sets/dicts (útil para diffs incrementales del globo: "qué
sismos nuevos han aparecido desde la última actualización").
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Optional


# ============================================================
# PAGER alert levels
# ============================================================
class PagerLevel(Enum):
    """Niveles oficiales de alerta del sistema USGS PAGER.

    El sistema PAGER evalúa el impacto humano y económico potencial
    poco después de cada sismo y publica un color de alerta de cuatro
    niveles, de menor a mayor severidad.
    """

    GREEN  = "green"   # < 1 muerto, < $1M
    YELLOW = "yellow"  # 1–100 muertos, $1M–$100M
    ORANGE = "orange" # 100–1000 muertos, $100M–$1B
    RED    = "red"     # > 1000 muertos, > $1B

    @classmethod
    def parse(cls, raw: Optional[str]) -> Optional["PagerLevel"]:
        """Convierte la cadena del feed USGS al enum, o ``None`` si falta."""

        if not raw:
            return None
        try:
            return cls(raw.lower())
        except ValueError:
            return None


# Codificación visual del nivel PAGER (color hex + radio relativo de
# punto en el globo). Se centraliza aquí para que la UI no duplique.
PAGER_VISUAL: Final[dict[PagerLevel, tuple[str, float]]] = {
    PagerLevel.GREEN:  ("#10b981", 0.6),
    PagerLevel.YELLOW: ("#facc15", 0.9),
    PagerLevel.ORANGE: ("#fb923c", 1.3),
    PagerLevel.RED:    ("#ef4444", 1.8),
}


# ============================================================
# Earthquake
# ============================================================
@dataclass(frozen=True)
class Earthquake:
    """Un sismo reportado en el feed USGS."""

    id: str                     # Identificador único USGS (ej. "us7000m9p2")
    timestamp_unix: float       # Hora del origen, en segundos UNIX
    longitude: float
    latitude: float
    depth_km: float
    magnitude: float
    place: str                  # Descripción humana, ej. "26 km W of Anchorage"
    url: str                    # URL del detalle en earthquake.usgs.gov
    pager: Optional[PagerLevel] = None
    significance: int = 0       # Campo "sig" del feed (0–1000+, mayor = más relevante)

    # ------------------------------------------------------------------
    # Categorización
    # ------------------------------------------------------------------
    def severity_bucket(self) -> str:
        """Etiqueta corta del rango de magnitud para agrupaciones en UI.

        Usa la clasificación clásica de Richter ("micro/menor/ligero/
        moderado/fuerte/mayor/grande/devastador"), pero **independiente
        del PAGER** para que sea siempre disponible.
        """

        m = self.magnitude
        if m < 3.0:   return "micro"
        if m < 4.0:   return "minor"
        if m < 5.0:   return "light"
        if m < 6.0:   return "moderate"
        if m < 7.0:   return "strong"
        if m < 8.0:   return "major"
        return "great"

    def is_recent(self, now_unix: float, hours: float = 24.0) -> bool:
        """¿El evento ocurrió en las últimas ``hours`` horas?"""

        return (now_unix - self.timestamp_unix) <= hours * 3600.0


# ============================================================
# ShakeStation
# ============================================================
@dataclass(frozen=True)
class ShakeStation:
    """Estación sísmica de cualquier red (citizen science o profesional).

    ``provider`` distingue la fuente para visualización:
      * ``"shakenet"`` — red AM de Raspberry Shake (citizen science)
      * ``"usgs"``     — redes profesionales IRIS/USGS (IU, US, etc.)
    """

    network: str                 # Código FDSN, p.ej. "AM", "IU", "US"
    code: str                    # Código de la estación, p.ej. "R0E05"
    latitude: float
    longitude: float
    elevation_m: float
    site_name: str = ""          # Descripción libre cuando exista
    provider: str = "shakenet"   # Categoría visual (shakenet / usgs)

    @property
    def nslc_prefix(self) -> str:
        """Prefijo NSL (sin canal) para mostrar en la UI."""

        return f"{self.network}.{self.code}"
