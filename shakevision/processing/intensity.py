"""
Traducción del movimiento del suelo a una escala humana (MMI).

Este módulo convierte la señal sísmica cruda en algo que un usuario sin
formación puede entender de un vistazo: una etiqueta del tipo
"perceptible" / "fuerte" / "muy fuerte" en lugar de "0.42 cm/s" o
"STA/LTA = 6.7".

Cadena de conversión
--------------------
  cuentas en EHZ
       │ × ganancia (cm·s⁻¹ / cuenta)         depende del instrumento
       ▼
  velocidad en cm/s
       │ pico absoluto sobre la ventana
       ▼
  PGV (Peak Ground Velocity)
       │ Worden 2012:
       │ MMI = 3.78 + 1.47 · log10(PGV)
       ▼
  intensidad MMI (1 – 12)
       │ tabla de descripciones humanas
       ▼
  IntensityLevel  →  pintado por la UI

Referencias
-----------
* Worden et al., 2012, "Probabilistic relationships between ground
  motion parameters and modified Mercalli intensity in California."
  Seismological Research Letters 83.5.
* USGS Modified Mercalli Intensity scale, descripciones oficiales.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np


# ============================================================
# Niveles MMI 1–12 (etiqueta + descripción + color)
# ============================================================
@dataclass(frozen=True)
class IntensityLevel:
    """Nivel de intensidad MMI con sus metadatos visuales."""

    mmi: int
    label: str         # Etiqueta corta (≤ 14 caracteres)
    description: str   # Descripción de una línea para el usuario común
    color: str         # Color del fondo de la tarjeta (hex)
    icon: str          # Emoji representativo (con caída a "·" si la fuente no soporta)


# Paleta y descripciones inspiradas en el "Did You Feel It?" de USGS.
INTENSITY_LEVELS: dict[int, IntensityLevel] = {
    1:  IntensityLevel( 1, "Imperceptible",
                       "Solo lo registran los instrumentos.",
                       "#404040", "·"),
    2:  IntensityLevel( 2, "Muy débil",
                       "Sentido por personas inmóviles en pisos altos.",
                       "#52525b", "·"),
    3:  IntensityLevel( 3, "Débil",
                       "Vibración interior parecida a un camión pasando.",
                       "#0ea5e9", "•"),
    4:  IntensityLevel( 4, "Ligero",
                       "La mayoría lo siente; cristalería tintinea.",
                       "#06b6d4", "•"),
    5:  IntensityLevel( 5, "Moderado",
                       "Despierta a quien duerme; objetos pequeños caen.",
                       "#10b981", "▴"),
    6:  IntensityLevel( 6, "Fuerte",
                       "Sentido por todos; muebles se desplazan.",
                       "#eab308", "▴"),
    7:  IntensityLevel( 7, "Muy fuerte",
                       "Daño leve en construcciones ordinarias.",
                       "#f97316", "▴"),
    8:  IntensityLevel( 8, "Severo",
                       "Daño considerable; chimeneas caídas.",
                       "#ef4444", "▲"),
    9:  IntensityLevel( 9, "Violento",
                       "Daño general en edificios.",
                       "#dc2626", "▲"),
    10: IntensityLevel(10, "Extremo",
                       "La mayoría de la mampostería queda destruida.",
                       "#991b1b", "▲"),
    11: IntensityLevel(11, "Catastrófico",
                       "Pocas estructuras quedan en pie.",
                       "#7f1d1d", "■"),
    12: IntensityLevel(12, "Devastador",
                       "Destrucción total; el terreno se ondula.",
                       "#0a0a0a", "■"),
}


# ============================================================
# Conversión PGV → MMI (Worden 2012)
# ============================================================
def pgv_to_mmi(pgv_cm_s: float) -> float:
    """Devuelve el MMI continuo (1.0 – 12.0) para un PGV dado.

    La fórmula clásica de Worden et al. (2012):

        MMI = 3.78 + 1.47 · log10(PGV)        si PGV > 0.0
              1.0                              si PGV ≈ 0

    Valores resultantes acotados al rango [1, 12].
    """

    if pgv_cm_s <= 0.001:
        return 1.0
    mmi = 3.78 + 1.47 * float(np.log10(pgv_cm_s))
    return max(1.0, min(12.0, mmi))


def classify(pgv_cm_s: float) -> IntensityLevel:
    """Devuelve el ``IntensityLevel`` correspondiente al PGV indicado."""

    mmi_int = int(round(pgv_to_mmi(pgv_cm_s)))
    mmi_int = max(1, min(12, mmi_int))
    return INTENSITY_LEVELS[mmi_int]


# ============================================================
# Cálculo del PGV a partir de muestras crudas
# ============================================================
def estimate_pgv(
    samples: np.ndarray,
    gain_cm_s_per_count: float,
    detrend: bool = True,
) -> float:
    """Estima el PGV en cm/s a partir de muestras en cuentas brutas.

    Parameters
    ----------
    samples:
        Vector 1-D del canal vertical (EHZ) en cuentas instrumentales.
    gain_cm_s_per_count:
        Factor de calibración: cm·s⁻¹ por cada cuenta. Para una
        Raspberry Shake típica EHZ ≈ ``2.22e-7`` (1 / 4.5×10⁸
        cuentas/(m/s) × 100 cm/m). Para datos sintéticos del Mock se
        utiliza un factor empírico que hace que un evento simulado
        caiga en torno a MMI 4–5.
    detrend:
        Resta la media antes de calcular el pico para evitar que un
        offset DC se confunda con velocidad real.
    """

    if samples.size == 0:
        return 0.0
    x = np.asarray(samples, dtype=np.float64)
    if detrend:
        x = x - np.mean(x)
    peak_counts = float(np.max(np.abs(x)))
    return peak_counts * float(gain_cm_s_per_count)


# ============================================================
# Helper: PGV → MMI en una sola llamada
# ============================================================
def estimate_intensity(
    samples: np.ndarray,
    gain_cm_s_per_count: float,
) -> tuple[float, IntensityLevel]:
    """Atajo: devuelve ``(pgv_cm_s, IntensityLevel)``."""

    pgv = estimate_pgv(samples, gain_cm_s_per_count)
    return pgv, classify(pgv)


# ============================================================
# Ganancias por defecto
# ============================================================
# Calibración aproximada para Raspberry Shake EHZ (geófono SS-4.5 con
# digitalizador de 24 bits y sensibilidad nominal de ~4.5×10⁸ cuentas
# por (m/s)). Es suficientemente buena para visualización; un usuario
# avanzado puede sustituir el valor con la calibración real de su
# estación leyéndola del fichero RESP/Stationxml.
RASPBERRY_SHAKE_EHZ_GAIN: float = 1.0 / 4.5e8 * 100.0  # cm/s por cuenta

# Para el generador Mock cuyo "evento sintético" tiene amplitud ~1.4
# en unidades arbitrarias, usamos una ganancia que sitúe el pico en
# aproximadamente 2 cm/s → MMI ≈ 5 (moderado).
MOCK_GAIN: float = 1.4  # cm/s por unidad arbitraria del generador


def default_gain_for(network: str, station: str) -> float:
    """Devuelve una ganancia por defecto según el preset de estación.

    El criterio actual es muy simple: si la red es ``XX`` (Mock)
    devolvemos la ganancia empírica del generador; en cualquier otro
    caso asumimos una Raspberry Shake estándar.
    """

    if network.upper() == "XX":
        return MOCK_GAIN
    return RASPBERRY_SHAKE_EHZ_GAIN


# ============================================================
# Histéresis / suavizado (opcional, para evitar parpadeo)
# ============================================================
class IntensitySmoother:
    """Aplica un decaimiento exponencial al PGV para no parpadear.

    El PGV instantáneo varía mucho entre frames si la señal contiene
    ruido. Mantener el máximo reciente con decaimiento (estilo "VU
    meter") da una lectura estable y aún reactiva.
    """

    def __init__(self, decay_per_second: float = 0.2, refresh_hz: float = 30.0) -> None:
        # Factor multiplicativo aplicado en cada tick para que la
        # caída total al cabo de 1 s sea ``decay_per_second``.
        self._decay = float(decay_per_second) ** (1.0 / refresh_hz)
        self._value: float = 0.0

    def update(self, sample_pgv: float) -> float:
        """Devuelve el PGV suavizado tras incorporar una nueva medición."""

        decayed = self._value * self._decay
        self._value = max(decayed, float(sample_pgv))
        return self._value

    def reset(self) -> None:
        self._value = 0.0

    @property
    def value(self) -> float:
        return self._value


# ============================================================
# Snapshot público (lo que envía la lógica a la tarjeta UI)
# ============================================================
@dataclass(frozen=True)
class IntensitySnapshot:
    """Lo que la UI necesita para pintar un frame de la tarjeta."""

    pgv_cm_s: float
    mmi: float
    level: IntensityLevel
    gain_cm_s_per_count: float

    @classmethod
    def from_samples(
        cls,
        samples: np.ndarray,
        gain_cm_s_per_count: float,
        smoother: Optional[IntensitySmoother] = None,
    ) -> "IntensitySnapshot":
        pgv = estimate_pgv(samples, gain_cm_s_per_count)
        if smoother is not None:
            pgv = smoother.update(pgv)
        return cls(
            pgv_cm_s=pgv,
            mmi=pgv_to_mmi(pgv),
            level=classify(pgv),
            gain_cm_s_per_count=gain_cm_s_per_count,
        )
