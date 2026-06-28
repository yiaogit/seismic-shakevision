"""
Escala de color por magnitud (pura, sin Qt).

Un degradado intuitivo verde→rojo alineado con los buckets de
``Earthquake.severity_bucket``: cuanto mayor la magnitud, más cálido/intenso
el color. Se usa para pintar la celda de magnitud en la tabla de eventos, los
marcadores del globo y la leyenda.

Mantenido aquí (en ``processing``) para poder testearlo sin ``QApplication``.
"""

from __future__ import annotations

from typing import Final

#: Tramos ``(umbral_inferior_inclusive, color_hex, clave_i18n_etiqueta)``.
#: El último tramo (≥7.0) no tiene techo. Orden ascendente por magnitud.
MAGNITUDE_SCALE: Final[tuple[tuple[float, str, str], ...]] = (
    (0.0, "#66bb6a", "mag.scale.micro"),       # < 3   verde
    (3.0, "#c0ca33", "mag.scale.minor"),       # 3–4   lima
    (4.0, "#fbc02d", "mag.scale.light"),       # 4–5   ámbar
    (5.0, "#fb8c00", "mag.scale.moderate"),    # 5–6   naranja
    (6.0, "#f4511e", "mag.scale.strong"),      # 6–7   naranja-rojo
    (7.0, "#c62828", "mag.scale.major"),       # ≥ 7   rojo intenso
)

_DEFAULT_COLOR: Final[str] = "#9aa0a6"  # gris — magnitud desconocida/NaN


def magnitude_color(magnitude: float) -> str:
    """Devuelve el color hex ``#rrggbb`` para una magnitud.

    Magnitudes negativas usan el primer tramo; ``NaN``/no-numérico → gris.
    """

    try:
        m = float(magnitude)
    except (TypeError, ValueError):
        return _DEFAULT_COLOR
    if m != m:  # NaN
        return _DEFAULT_COLOR
    color = MAGNITUDE_SCALE[0][1]
    for threshold, hex_color, _key in MAGNITUDE_SCALE:
        if m >= threshold:
            color = hex_color
        else:
            break
    return color


def magnitude_scale_legend() -> list[tuple[str, str]]:
    """Lista ``[(color_hex, clave_i18n), …]`` para construir la leyenda."""

    return [(hex_color, key) for _thr, hex_color, key in MAGNITUDE_SCALE]
