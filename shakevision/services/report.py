"""
Generador del reporte de actividad sísmica en HTML.

Diseño
------
* Salida = **un único fichero HTML** con CSS embebido. Sin JS,
  sin imágenes externas, sin red. Se abre igual en Safari, Chrome,
  Firefox y se exporta a PDF desde "Imprimir → Guardar como PDF".
* La plantilla vive en ``shakevision/web/report/template.html`` y los
  estilos en ``styles.css``. El generador hace solo *substitución*
  de marcadores ``{{NOMBRE}}`` (sin ``str.format`` para evitar conflictos
  con las llaves del CSS).
* Toda la lógica de agregación se reutiliza de
  ``shakevision.ui.dashboard_view`` para que el reporte y el panel
  cuenten la misma historia.

Uso
---

    from shakevision.services.report import ReportGenerator

    gen = ReportGenerator()
    out = gen.generate(
        quakes=earthquakes,
        station_label="AM.R0E05",
        version=__version__,
        output_path=Path("~/Desktop/reporte.html").expanduser(),
    )
"""

from __future__ import annotations

import html as _html
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from shakevision.i18n import t
from shakevision.services.data_models import Earthquake

logger = logging.getLogger(__name__)


# Carpeta de la plantilla (instalada como package_data)
_TEMPLATE_DIR: Path = (
    Path(__file__).resolve().parent.parent / "web" / "report"
)
_TEMPLATE_HTML: Path = _TEMPLATE_DIR / "template.html"
_TEMPLATE_CSS: Path = _TEMPLATE_DIR / "styles.css"


# ============================================================
# Codificación visual de magnitudes (mismo orden que mag_buckets)
# ============================================================
_MAG_BAR_CLASSES: list[str] = [
    "mag-1", "mag-2", "mag-3", "mag-4", "mag-5"
]


# ============================================================
# Generador
# ============================================================
class ReportError(Exception):
    """Error general al generar el reporte."""


class ReportGenerator:
    """Genera reportes HTML auto-contenidos a partir de datos USGS."""

    def __init__(
        self,
        template_html: Path = _TEMPLATE_HTML,
        styles_css: Path = _TEMPLATE_CSS,
    ) -> None:
        if not template_html.is_file():
            raise FileNotFoundError(template_html)
        if not styles_css.is_file():
            raise FileNotFoundError(styles_css)
        self._template = template_html.read_text(encoding="utf-8")
        self._styles = styles_css.read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def render(
        self,
        quakes: Iterable[Earthquake],
        station_label: str = "—",
        version: str = "0.0.0",
        now_unix: Optional[float] = None,
    ) -> str:
        """Devuelve el HTML completo del reporte como string."""

        # Importación tardía para evitar acoplar este módulo con la UI
        from shakevision.ui.dashboard_view import (
            aggregate_by_country,
            aggregate_depth_buckets,
            aggregate_magnitude_buckets,
            build_timeline_24h,
        )

        quakes_list = list(quakes)
        now = now_unix if now_unix is not None else time.time()
        last_24h = [q for q in quakes_list if q.timestamp_unix >= now - 24 * 3600]

        countries = aggregate_by_country(quakes_list, top_n=10)
        mag_buckets = aggregate_magnitude_buckets(last_24h)
        depth_buckets = aggregate_depth_buckets(last_24h)
        timeline = build_timeline_24h(quakes_list, now_unix=now, min_magnitude=3.0)

        # Idioma actual para etiquetar <html lang="..."> (no traduce: solo
        # informa al navegador/lector de pantalla del idioma del contenido).
        try:
            from shakevision.i18n import LocaleService
            lang_code = LocaleService.current_language()
        except Exception:  # noqa: BLE001
            lang_code = "en"

        substitutions = {
            # Lengua + cabecera traducidas
            "{{LANG}}":              _esc(lang_code),
            "{{HTML_TITLE}}":        _esc(t("report.html.title")),
            "{{H1}}":                _esc(t("report.html.h1")),
            "{{SUBTITLE}}":          _esc(t("report.html.subtitle")),
            "{{META_GENERATED}}":    _esc(t("report.html.meta.generated")),
            "{{META_STATION}}":      _esc(t("report.html.meta.station")),
            "{{META_VERSION}}":      _esc(t("report.html.meta.version")),
            "{{SECTION_COUNTRIES}}": _esc(t("report.html.section.countries")),
            "{{SECTION_MAGNITUDE}}": _esc(t("report.html.section.magnitude")),
            "{{SECTION_DEPTH}}":     _esc(t("report.html.section.depth")),
            "{{SECTION_TIMELINE}}":  _esc(t("report.html.section.timeline")),
            "{{SECTION_EVENTS}}":    _esc(t("report.html.section.events")),
            # El footer trae <strong> intencional → NO escapar
            "{{FOOTER_SOURCES}}":    t("report.html.footer.sources"),
            # Bloques dinámicos
            "{{INLINE_STYLES}}":  self._styles,
            "{{GENERATED_AT}}":   _format_now(now),
            "{{STATION_LABEL}}":  _esc(station_label),
            "{{VERSION}}":        _esc(version),
            "{{KPI_CARDS}}":      _render_kpi_cards(last_24h, countries),
            "{{COUNTRY_BARS}}":   _render_country_bars(countries),
            "{{MAGNITUDE_BARS}}": _render_magnitude_bars(mag_buckets),
            "{{DEPTH_BARS}}":     _render_depth_bars(depth_buckets),
            "{{TIMELINE_SVG}}":   _render_timeline_svg(timeline, now=now),
            "{{EVENT_TABLE}}":    _render_event_table(last_24h, min_mag=3.0),
        }

        out = self._template
        for key, value in substitutions.items():
            out = out.replace(key, value)
        return out

    def generate(
        self,
        quakes: Iterable[Earthquake],
        station_label: str,
        version: str,
        output_path: Path,
        now_unix: Optional[float] = None,
    ) -> Path:
        """Renderiza el HTML y lo escribe en ``output_path``.

        Crea los directorios padres si no existen. Devuelve el ``Path``
        absoluto del fichero creado.
        """

        html = self.render(quakes, station_label, version, now_unix)
        output_path = Path(output_path).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
        logger.info("Reporte HTML escrito en %s (%d bytes)",
                    output_path, output_path.stat().st_size)
        return output_path


# ============================================================
# Renderers privados (puros, testeables)
# ============================================================
def _esc(text: str) -> str:
    """Escape HTML básico."""

    return _html.escape(str(text), quote=True)


def _format_now(unix_ts: float) -> str:
    dt = datetime.fromtimestamp(unix_ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def _render_kpi_cards(
    last_24h: list[Earthquake], countries: list[dict]
) -> str:
    count = len(last_24h)
    max_mag = max((q.magnitude for q in last_24h), default=None)
    countries_24h = len({_country(q) for q in last_24h})
    if last_24h:
        latest = max(last_24h, key=lambda q: q.timestamp_unix)
        ago_min = max(0, int((time.time() - latest.timestamp_unix) / 60))
        latest_str = (t("report.minutes_ago", n=ago_min) if ago_min < 60
                      else t("report.hours_ago", n=ago_min/60))
        latest_card = t("report.kpi.latest_value", ago=latest_str)
    else:
        latest_card = "—"

    cards = [
        (t("report.kpi.count_24h"),  f"{count}"),
        (t("report.kpi.max_mag"),    f"M {max_mag:.1f}" if max_mag else "—"),
        (t("report.kpi.latest"),     latest_card),
        (t("report.kpi.countries"),  str(countries_24h)),
    ]
    return "\n".join(
        f'<div class="kpi-card">'
        f'<div class="label">{_esc(label)}</div>'
        f'<div class="value">{_esc(value)}</div>'
        f'</div>'
        for label, value in cards
    )


def _country(quake: Earthquake) -> str:
    """Reaprovecha la heurística del dashboard sin importar Qt."""

    from shakevision.ui.dashboard_view import extract_country
    return extract_country(quake.place)


def _render_country_bars(countries: list[dict]) -> str:
    if not countries:
        return f'<p style="color:#71717a">{_esc(t("report.no_data"))}</p>'
    max_count = max(c["count"] for c in countries)
    rows = []
    for c in countries:
        pct = (c["count"] / max_count) * 100
        rows.append(
            f'<div class="bar-row">'
            f'<span class="bar-label">{_esc(c["name"])}</span>'
            f'<div class="bar-track">'
            f'<div class="bar-fill" style="width: {pct:.1f}%"></div>'
            f'</div>'
            f'<span class="bar-value">{c["count"]}</span>'
            f'</div>'
        )
    return "\n".join(rows)


def _render_magnitude_bars(buckets: list[dict]) -> str:
    if not buckets or all(b["count"] == 0 for b in buckets):
        return f'<p style="color:#71717a">{_esc(t("report.no_24h"))}</p>'
    max_count = max(b["count"] for b in buckets) or 1
    rows = []
    for i, b in enumerate(buckets):
        pct = (b["count"] / max_count) * 100
        cls = _MAG_BAR_CLASSES[i] if i < len(_MAG_BAR_CLASSES) else "mag-1"
        rows.append(
            f'<div class="bar-row">'
            f'<span class="bar-label mono">{_esc(b["label"])}</span>'
            f'<div class="bar-track">'
            f'<div class="bar-fill {cls}" style="width: {pct:.1f}%"></div>'
            f'</div>'
            f'<span class="bar-value">{b["count"]}</span>'
            f'</div>'
        )
    return "\n".join(rows)


def _render_depth_bars(buckets: list[dict]) -> str:
    if not buckets or all(b["count"] == 0 for b in buckets):
        return f'<p style="color:#71717a">{_esc(t("report.no_24h"))}</p>'
    max_count = max(b["count"] for b in buckets) or 1
    rows = []
    for b in buckets:
        pct = (b["count"] / max_count) * 100
        label = t("report.depth_unit_km", label=b["label"])
        rows.append(
            f'<div class="bar-row">'
            f'<span class="bar-label mono">{_esc(label)}</span>'
            f'<div class="bar-track">'
            f'<div class="bar-fill depth" style="width: {pct:.1f}%"></div>'
            f'</div>'
            f'<span class="bar-value">{b["count"]}</span>'
            f'</div>'
        )
    return "\n".join(rows)


def _render_event_table(
    quakes: list[Earthquake], min_mag: float = 3.0
) -> str:
    rows_data = sorted(
        (q for q in quakes if q.magnitude >= min_mag),
        key=lambda q: q.timestamp_unix, reverse=True,
    )
    if not rows_data:
        return f'<p style="color:#71717a">{_esc(t("report.no_above_threshold"))}</p>'

    rows = []
    for q in rows_data[:30]:  # cap a 30 filas para no inflar el reporte
        ts_str = datetime.fromtimestamp(
            q.timestamp_unix, tz=timezone.utc
        ).strftime("%Y-%m-%d %H:%M:%S")
        pager = ""
        pager_class = ""
        if q.pager:
            pager = q.pager.value.upper()
            pager_class = f"pager-{q.pager.value}"
        rows.append(
            f"<tr>"
            f"<td class='time'>{_esc(ts_str)}</td>"
            f"<td class='mag'>M {q.magnitude:.1f}</td>"
            f"<td>{_esc(q.place) or '—'}</td>"
            f"<td class='depth'>{q.depth_km:.1f} km</td>"
            f"<td class='pager {pager_class}'>{_esc(pager) or '—'}</td>"
            f"</tr>"
        )

    return (
        "<table class='events'><thead><tr>"
        f"<th>{_esc(t('report.table.time_utc'))}</th>"
        f"<th>{_esc(t('report.table.magnitude'))}</th>"
        f"<th>{_esc(t('report.table.location'))}</th>"
        f"<th>{_esc(t('report.table.depth'))}</th>"
        f"<th>{_esc(t('report.table.pager'))}</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _render_timeline_svg(
    events: list[dict], now: float, width: int = 880, height: int = 180,
) -> str:
    """Sparkline SVG simple: X = tiempo, Y = magnitud, color por bucket."""

    if not events:
        return f'<p style="color:#71717a">{_esc(t("report.no_24h_to_chart"))}</p>'

    pad_l, pad_r, pad_t, pad_b = 40, 20, 16, 28
    inner_w = width - pad_l - pad_r
    inner_h = height - pad_t - pad_b

    t_min = now - 24 * 3600
    t_max = now
    m_max = max(7.5, max(e["mag"] for e in events))

    def x(ts: float) -> float:
        return pad_l + ((ts - t_min) / (t_max - t_min)) * inner_w

    def y(mag: float) -> float:
        return pad_t + (1.0 - (mag / m_max)) * inner_h

    def color_for(mag: float) -> str:
        if mag < 3.0:  return "#38bdf8"
        if mag < 4.5:  return "#facc15"
        if mag < 6.0:  return "#fb923c"
        if mag < 7.5:  return "#ef4444"
        return "#a855f7"

    # Líneas del eje Y para magnitudes 3, 5, 7
    grid = []
    for mag in (3.0, 5.0, 7.0):
        if mag > m_max:
            continue
        gy = y(mag)
        grid.append(
            f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{pad_l+inner_w}" y2="{gy:.1f}" '
            f'stroke="rgba(255,255,255,0.06)" stroke-width="1" />'
            f'<text x="{pad_l-6}" y="{gy+3:.1f}" fill="#71717a" '
            f'font-size="10" text-anchor="end" font-family="JetBrains Mono">M {int(mag)}</text>'
        )

    # Marcas del eje X cada 6 horas
    for h in range(0, 25, 6):
        ts = t_min + h * 3600
        gx = x(ts)
        label = (t("report.timeline.x_now") if h == 24
                 else t("report.timeline.x_hours_ago", h=24 - h))
        grid.append(
            f'<text x="{gx:.1f}" y="{height-pad_b+18}" fill="#71717a" '
            f'font-size="10" text-anchor="middle" font-family="JetBrains Mono">{label}</text>'
        )

    # Puntos
    dots = []
    for e in events:
        cx = x(e["ts"])
        cy = y(e["mag"])
        r = max(2.5, e["mag"] * 1.4)
        col = color_for(e["mag"])
        dots.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" '
            f'fill="{col}" fill-opacity="0.85" />'
        )

    return (
        f'<svg class="timeline-svg" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet">'
        + "".join(grid)
        + "".join(dots)
        + "</svg>"
    )
