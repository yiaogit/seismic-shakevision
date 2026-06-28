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
_TEMPLATE_ANALYSIS_HTML: Path = _TEMPLATE_DIR / "template_analysis.html"
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
        # Plantilla del reporte de ANÁLISIS (estadístico). Opcional: si falta,
        # el modo análisis cae al reporte en vivo (degradación elegante).
        self._template_analysis = (
            _TEMPLATE_ANALYSIS_HTML.read_text(encoding="utf-8")
            if _TEMPLATE_ANALYSIS_HTML.is_file() else None
        )

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def render(
        self,
        quakes: Iterable[Earthquake],
        station_label: str = "—",
        version: str = "0.0.0",
        now_unix: Optional[float] = None,
        context: Optional[dict] = None,
    ) -> str:
        """Devuelve el HTML completo del reporte como string.

        Dos diseños según ``context["mode"]``:
        * ``"analysis"`` → reporte **estadístico** (catálogo histórico
          seleccionado: KPIs de Mc/b/energía + gráficas pro + tabla). Ruta PURA
          (no importa la UI Qt).
        * cualquier otro → reporte **de monitoreo en vivo** (24 h + ranking).
        """

        quakes_list = list(quakes)
        now = now_unix if now_unix is not None else time.time()

        if (context or {}).get("mode") == "analysis" and self._template_analysis:
            return self._render_analysis(
                quakes_list, version, now, context or {})

        # ---- Reporte EN VIVO (monitoreo) ----
        # Importación tardía para evitar acoplar este módulo con la UI Qt.
        from shakevision.ui.dashboard_view import (
            aggregate_by_country,
            aggregate_depth_buckets,
            aggregate_magnitude_buckets,
            build_timeline_24h,
        )
        last_24h = [q for q in quakes_list if q.timestamp_unix >= now - 24 * 3600]

        countries = aggregate_by_country(quakes_list, top_n=10)
        mag_buckets = aggregate_magnitude_buckets(last_24h)
        depth_buckets = aggregate_depth_buckets(last_24h)
        timeline = build_timeline_24h(quakes_list, now_unix=now, min_magnitude=3.0)
        period_s = float((context or {}).get("period_seconds") or 86400)

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
            "{{SUBTITLE}}":          _esc(t("report.html.subtitle",
                                            window=_humanize_window(period_s))),
            "{{META_GENERATED}}":    _esc(t("report.html.meta.generated")),
            "{{META_STATION}}":      _esc(t("report.html.meta.station")),
            "{{META_VERSION}}":      _esc(t("report.html.meta.version")),
            "{{SECTION_COUNTRIES}}": _esc(t("report.html.section.countries",
                                            window=_humanize_window(period_s))),
            "{{SECTION_MAGNITUDE}}": _esc(t("report.html.section.magnitude")),
            "{{SECTION_DEPTH}}":     _esc(t("report.html.section.depth")),
            "{{SECTION_TIMELINE}}":  _esc(t("report.html.section.timeline")),
            "{{SECTION_EVENTS}}":    _esc(t("report.html.section.events")),
            "{{SECTION_SUMMARY}}":   _esc(t("report.live.summary.title")),
            "{{SECTION_NOTES}}":     _esc(t("report.live.notes.title")),
            "{{CAP_TIMELINE}}":      _esc(t("report.live.cap.timeline")),
            # El footer trae <strong> intencional → NO escapar
            "{{FOOTER_SOURCES}}":    t("report.html.footer.sources"),
            # Bloques dinámicos
            "{{INLINE_STYLES}}":  self._styles,
            "{{GENERATED_AT}}":   _format_now(now),
            "{{STATION_LABEL}}":  _esc(station_label),
            "{{VERSION}}":        _esc(version),
            "{{KPI_CARDS}}":      _render_kpi_cards(last_24h, countries, now),
            "{{COUNTRY_BARS}}":   _render_country_bars(countries),
            "{{MAGNITUDE_BARS}}": _render_magnitude_bars(mag_buckets),
            "{{DEPTH_BARS}}":     _render_depth_bars(depth_buckets),
            "{{TIMELINE_SVG}}":   _render_timeline_svg(timeline, now=now),
            "{{EVENT_TABLE}}":    _render_event_table(last_24h, min_mag=3.0),
            # Contexto (modo en vivo / análisis + región + rango seleccionado).
            "{{REPORT_CONTEXT}}":    _render_context_block(context, now),
            # (La capa estadística "pro" — GR/b, Mc, energía — vive ahora SOLO
            # en el reporte de análisis: el reporte en vivo es monitoreo puro.)
            "{{LIVE_SUMMARY}}":      _render_live_summary(
                quakes_list, countries, period_s, now),
            "{{NOTES_BLOCK}}":       _render_live_notes(
                now, period_s, station_label),
        }

        out = self._template
        for key, value in substitutions.items():
            out = out.replace(key, value)
        return out

    # ------------------------------------------------------------------
    # Reporte de ANÁLISIS (estadístico, ruta pura sin Qt)
    # ------------------------------------------------------------------
    def _render_analysis(
        self, quakes_list: list[Earthquake], version: str, now: float,
        context: dict,
    ) -> str:
        try:
            from shakevision.i18n import LocaleService
            lang_code = LocaleService.current_language()
        except Exception:  # noqa: BLE001
            lang_code = "en"

        subs = {
            "{{LANG}}":            _esc(lang_code),
            "{{HTML_TITLE}}":      _esc(t("report.an.title")),
            "{{H1}}":              _esc(t("report.an.h1")),
            "{{SUBTITLE}}":        _esc(t("report.an.subtitle")),
            "{{META_GENERATED}}":  _esc(t("report.html.meta.generated")),
            "{{META_SOURCE}}":     _esc(t("report.an.meta.source")),
            "{{META_VERSION}}":    _esc(t("report.html.meta.version")),
            "{{SECTION_SUMMARY}}": _esc(t("report.an.section.summary")),
            "{{SECTION_FINDINGS}}": _esc(t("report.an.findings.title")),
            "{{SECTION_CHARTS}}":  _esc(t("report.an.section.charts")),
            "{{SECTION_METHODS}}": _esc(t("report.an.methods.title")),
            "{{SECTION_EVENTS}}":  _esc(t("report.an.section.events")),
            "{{TITLE_GR}}":         _esc(t("report.pro.gr")),
            "{{TITLE_ENERGY}}":     _esc(t("report.an.chart.energy")),
            "{{TITLE_MCB}}":        _esc(t("report.an.chart.mcb")),
            "{{TITLE_SPATIAL}}":    _esc(t("report.an.chart.spatial")),
            "{{TITLE_DEPTH}}":      _esc(t("report.pro.depth_hist")),
            "{{TITLE_SECTION}}":    _esc(t("report.an.chart.section")),
            "{{TITLE_INTEREVENT}}": _esc(t("report.an.chart.interevent")),
            "{{CAP_GR}}":           _esc(t("report.an.cap.gr")),
            "{{CAP_ENERGY}}":       _esc(t("report.an.cap.energy")),
            "{{CAP_MCB}}":          _esc(t("report.an.cap.mcb")),
            "{{CAP_SPATIAL}}":      _esc(t("report.an.cap.spatial")),
            "{{CAP_DEPTH}}":        _esc(t("report.an.cap.depth")),
            "{{CAP_SECTION}}":      _esc(t("report.an.cap.section")),
            "{{CAP_INTEREVENT}}":   _esc(t("report.an.cap.interevent")),
            "{{FOOTER_SOURCES}}":   t("report.html.footer.sources"),
            "{{INLINE_STYLES}}":    self._styles,
            "{{GENERATED_AT}}":     _format_now(now),
            "{{SOURCE_LABEL}}":     "USGS / ANSS",
            "{{VERSION}}":          _esc(version),
            "{{REPORT_CONTEXT}}":   _render_context_block(context, now),
            "{{STATS_KPIS}}":       _render_stats_kpis(quakes_list, context),
            "{{FINDINGS}}":         _render_findings(quakes_list, context),
            "{{GR_SVG}}":           _or_empty(_render_gr_svg(quakes_list)),
            "{{ENERGY_SVG}}":       _or_empty(_render_energy_svg(quakes_list)),
            "{{MCB_SVG}}":          _or_empty(_render_mcb_svg(quakes_list)),
            "{{SPATIAL_SVG}}":      _or_empty(_render_spatial_svg(quakes_list)),
            "{{DEPTH_HIST_SVG}}":   _or_empty(_render_depth_hist_svg(quakes_list)),
            "{{SECTION_SVG}}":      _or_empty(_render_cross_section_svg(quakes_list)),
            "{{INTEREVENT_SVG}}":   _or_empty(_render_inter_event_svg(quakes_list)),
            "{{METHODS_BLOCK}}":    _render_methods_block(quakes_list, context, now),
            "{{EVENT_TABLE}}":      _render_event_table_an(quakes_list),
        }
        out = self._template_analysis
        for key, value in subs.items():
            out = out.replace(key, value)
        return out

    def generate(
        self,
        quakes: Iterable[Earthquake],
        station_label: str,
        version: str,
        output_path: Path,
        now_unix: Optional[float] = None,
        context: Optional[dict] = None,
    ) -> Path:
        """Renderiza el HTML y lo escribe en ``output_path``.

        Crea los directorios padres si no existen. Devuelve el ``Path``
        absoluto del fichero creado.
        """

        html = self.render(quakes, station_label, version, now_unix, context)
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


def _fmt_date(epoch) -> str:
    try:
        return datetime.fromtimestamp(
            float(epoch), tz=timezone.utc).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError, OverflowError):
        return "—"


def _render_context_block(context: Optional[dict], now: float) -> str:
    """Cabecera de contexto: modo (en vivo / análisis) + región + rango."""

    if not context:
        return ""
    if context.get("mode") == "analysis":
        chips = [
            f'<span class="ctx-mode ctx-analysis">{_esc(t("report.ctx.analysis"))}</span>',
            f'<span class="ctx-chip">{_esc(context.get("region") or "")}</span>',
            f'<span class="ctx-chip">{_fmt_date(context.get("from"))} → '
            f'{_fmt_date(context.get("to"))}</span>',
        ]
        mm = context.get("min_mag")
        if mm:
            chips.append(f'<span class="ctx-chip">M ≥ {float(mm):.1f}</span>')
    else:
        ps = float(context.get("period_seconds") or 86400)
        win = (f"{ps/86400:.0f} d" if ps >= 86400 else f"{ps/3600:.0f} h")
        chips = [
            f'<span class="ctx-mode ctx-live">{_esc(t("report.ctx.live"))}</span>',
            f'<span class="ctx-chip">{_esc(t("report.ctx.window", window=win))}</span>',
        ]
        if context.get("region"):
            chips.append(f'<span class="ctx-chip">{_esc(context["region"])}</span>')
    return '<div class="report-context">' + "".join(chips) + "</div>"


def _render_kpi_cards(
    last_24h: list[Earthquake], countries: list[dict],
    now: Optional[float] = None,
) -> str:
    ref = now if now is not None else time.time()
    count = len(last_24h)
    max_mag = max((q.magnitude for q in last_24h), default=None)
    countries_24h = len({_country(q) for q in last_24h})
    if last_24h:
        latest = max(last_24h, key=lambda q: q.timestamp_unix)
        ago_min = max(0, int((ref - latest.timestamp_unix) / 60))
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
    quakes: list[Earthquake], min_mag: float = 3.0, order: str = "time"
) -> str:
    key = ((lambda q: q.magnitude) if order == "magnitude"
           else (lambda q: q.timestamp_unix))
    rows_data = sorted(
        (q for q in quakes if q.magnitude >= min_mag),
        key=key, reverse=True,
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
        if mag < 3.0:
            return "#38bdf8"
        if mag < 4.5:
            return "#facc15"
        if mag < 6.0:
            return "#fb923c"
        if mag < 7.5:
            return "#ef4444"
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


# ============================================================
# Análisis profesional (snapshot estadístico) — SVG inline, sin JS
# ============================================================
def _fmt_energy(joules: float) -> str:
    return f"{joules:.2e} J"


def _render_pro_summary(quakes: list[Earthquake]) -> str:
    """Bloque de parámetros: N, b±err, Mc, rango de magnitud, energía total."""

    from shakevision.processing import seismic_stats as ss
    if not quakes:
        return f'<p style="color:#71717a">{_esc(t("report.pro.insufficient"))}</p>'
    mags = [q.magnitude for q in quakes]
    bv = ss.b_value(mags)
    total_e = sum(ss.energy_joules(m) for m in mags)
    items = [(_esc(t("report.pro.n")), str(len(quakes)))]
    if bv:
        items.append(("b", f"{bv['b']:.2f} ± {bv['b_err']:.2f}"))
        items.append(("Mc", f"{bv['mc']:.1f}"))
    items.append((_esc(t("report.pro.mag_range")),
                  f"M {min(mags):.1f}–{max(mags):.1f}"))
    items.append((_esc(t("report.pro.energy")), _fmt_energy(total_e)))
    cells = "".join(
        f"<div class='pro-kpi'><span>{lbl}</span><strong>{_esc(val)}</strong></div>"
        for lbl, val in items)
    return f"<div class='pro-kpis'>{cells}</div>"


def _render_gr_svg(quakes: list[Earthquake], width: int = 430,
                   height: int = 240) -> str:
    """Diagrama Gutenberg–Richter: N(≥M) en log10 + recta de ajuste b."""

    import math

    from shakevision.processing import seismic_stats as ss
    if len(quakes) < 10:
        return ""
    f = ss.fmd([q.magnitude for q in quakes])
    pts = [(m, c) for m, c in zip(f["mag"], f["cumulative"]) if c > 0]
    if len(pts) < 2:
        return ""
    bv = ss.b_value([q.magnitude for q in quakes])
    pad_l, pad_r, pad_t, pad_b = 46, 12, 12, 28
    iw, ih = width - pad_l - pad_r, height - pad_t - pad_b
    xs = [p[0] for p in pts]
    x_min, x_max = min(xs), max(xs) + 0.1
    ly_max = max(math.log10(c) for _m, c in pts)

    def X(m):
        return pad_l + (m - x_min) / (x_max - x_min) * iw

    def Y(logy):
        return pad_t + (1 - (logy / ly_max if ly_max > 0 else 0)) * ih

    grid = []
    for k in range(0, int(math.floor(ly_max)) + 1):
        gy = Y(k)
        grid.append(
            f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{pad_l+iw}" y2="{gy:.1f}" '
            f'stroke="rgba(255,255,255,0.06)"/>'
            f'<text x="{pad_l-6}" y="{gy+3:.1f}" fill="#71717a" font-size="9" '
            f'text-anchor="end" font-family="JetBrains Mono">10^{k}</text>')
    dots = "".join(
        f'<circle cx="{X(m):.1f}" cy="{Y(math.log10(c)):.1f}" r="3" '
        f'fill="#0a84ff"/>' for m, c in pts)
    fit = ""
    if bv:
        m1, m2 = bv["mc"], x_max
        n1, n2 = bv["a"] - bv["b"] * m1, bv["a"] - bv["b"] * m2
        mcx = X(bv["mc"])
        fit = (
            # Línea vertical en Mc (umbral de completitud).
            f'<line x1="{mcx:.1f}" y1="{pad_t}" x2="{mcx:.1f}" '
            f'y2="{pad_t+ih}" stroke="#9ca3af" stroke-width="1" '
            f'stroke-dasharray="2 3"/>'
            f'<text x="{mcx+3:.1f}" y="{pad_t+9:.1f}" fill="#8a8a8a" '
            f'font-size="8" font-family="JetBrains Mono">Mc {bv["mc"]:.1f}</text>'
            # Recta de ajuste b sobre Mc.
            f'<line x1="{X(m1):.1f}" y1="{Y(n1):.1f}" x2="{X(m2):.1f}" '
            f'y2="{Y(n2):.1f}" stroke="#3395ff" stroke-width="2" '
            f'stroke-dasharray="4 3"/>'
            # Anotación b / a sobre el plano.
            f'<text x="{pad_l+iw-4:.1f}" y="{pad_t+10:.1f}" fill="#3395ff" '
            f'font-size="9" text-anchor="end" font-family="JetBrains Mono">'
            f'b={bv["b"]:.2f} a={bv["a"]:.1f}</text>')
    xlabel = (f'<text x="{pad_l+iw/2:.0f}" y="{height-6}" fill="{_LABEL}" '
              f'font-size="10" text-anchor="middle" '
              f'font-family="JetBrains Mono">M</text>'
              f'<text x="11" y="{pad_t+ih/2:.1f}" fill="{_LABEL}" font-size="9" '
              f'text-anchor="middle" transform="rotate(-90 11 {pad_t+ih/2:.1f})">'
              f'N(≥M)</text>')
    return (f'<svg viewBox="0 0 {width} {height}" '
            f'xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet">'
            + "".join(grid) + fit + dots + xlabel + "</svg>")


def _render_depth_hist_svg(quakes: list[Earthquake], width: int = 430,
                           height: int = 240) -> str:
    """Histograma de profundidad (barras verticales)."""

    from shakevision.processing import seismic_stats as ss
    if not quakes:
        return ""
    h = ss.depth_histogram([q.depth_km for q in quakes], bin_km=25.0)
    counts = h["counts"]
    edges = h["edges"]
    if not counts or max(counts) == 0:
        return ""
    pad_l, pad_r, pad_t, pad_b = 40, 12, 12, 30
    iw, ih = width - pad_l - pad_r, height - pad_t - pad_b
    n = len(counts)
    cmax = max(counts)
    bw = iw / n
    bars = []
    for i, c in enumerate(counts):
        bh = (c / cmax) * ih
        bx = pad_l + i * bw
        by = pad_t + (ih - bh)
        bars.append(
            f'<rect x="{bx+1:.1f}" y="{by:.1f}" width="{bw-2:.1f}" '
            f'height="{bh:.1f}" fill="#0a84ff" fill-opacity="0.8"/>')
        if i % max(1, n // 6) == 0:
            bars.append(
                f'<text x="{bx+bw/2:.1f}" y="{height-8}" fill="#71717a" '
                f'font-size="9" text-anchor="middle" '
                f'font-family="JetBrains Mono">{int(edges[i])}</text>')
    return (f'<svg viewBox="0 0 {width} {height}" '
            f'xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet">'
            + "".join(bars) + "</svg>")


# ============================================================
# Reporte de ANÁLISIS — KPIs + SVGs estadísticos (puros, sin Qt)
# ============================================================
_SVG_HEAD = (
    '<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" '
    'preserveAspectRatio="xMidYMid meet">'
)
# Rampa secuencial conteo bajo→alto (azul→rojo) para la densidad espacial.
_DENSITY_RAMP = ["#1e3a8a", "#3b82f6", "#10b981", "#f59e0b", "#ef4444"]


def _ramp_color(frac: float) -> str:
    i = int(max(0.0, min(1.0, frac)) * (len(_DENSITY_RAMP) - 1) + 0.5)
    return _DENSITY_RAMP[i]


def _legend(x: int, items: list[tuple[str, str]]) -> str:
    """Mini-leyenda SVG: lista de (color, etiqueta) en la esquina superior."""

    out, cx = [], x
    for color, label in items:
        out.append(
            f'<rect x="{cx}" y="6" width="9" height="9" fill="{color}"/>'
            f'<text x="{cx + 13}" y="14" fill="#a1a1aa" font-size="10" '
            f'font-family="JetBrains Mono">{_esc(label)}</text>')
        cx += 28 + 9 * len(label)
    return "".join(out)


def _or_empty(svg: str) -> str:
    """Si el renderer devolvió '' (datos insuficientes), muestra un marcador
    dentro de la tarjeta en vez de dejarla vacía."""

    return svg if svg else (
        f'<p class="fig-empty">{_esc(t("report.pro.insufficient"))}</p>')


# Colores de ejes legibles tanto en pantalla (tema oscuro) como impresos
# (fondo blanco): grises medios + rejilla semitransparente.
_AXIS = "#9ca3af"
_GRID = "rgba(127,127,127,0.20)"
_LABEL = "#8a8a8a"


def _plot_frame(pad_l, pad_t, iw, ih, x_ticks, y_ticks,
                x_title: str = "", y_title: str = "") -> str:
    """Dibuja ejes + rejilla + ticks/etiquetas. ``x_ticks``/``y_ticks`` son
    listas de ``(pixel, etiqueta)``."""

    p = []
    for py, lbl in y_ticks:
        p.append(f'<line x1="{pad_l}" y1="{py:.1f}" x2="{pad_l+iw}" '
                 f'y2="{py:.1f}" stroke="{_GRID}" stroke-width="1"/>')
        if lbl:
            p.append(f'<text x="{pad_l-6}" y="{py+3:.1f}" fill="{_LABEL}" '
                     f'font-size="9" text-anchor="end" '
                     f'font-family="JetBrains Mono">{_esc(lbl)}</text>')
    p.append(f'<line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{pad_t+ih}" '
             f'stroke="{_AXIS}" stroke-width="1"/>')
    p.append(f'<line x1="{pad_l}" y1="{pad_t+ih}" x2="{pad_l+iw}" '
             f'y2="{pad_t+ih}" stroke="{_AXIS}" stroke-width="1"/>')
    for px, lbl in x_ticks:
        p.append(f'<line x1="{px:.1f}" y1="{pad_t+ih}" x2="{px:.1f}" '
                 f'y2="{pad_t+ih+4}" stroke="{_AXIS}" stroke-width="1"/>')
        if lbl:
            p.append(f'<text x="{px:.1f}" y="{pad_t+ih+15:.1f}" fill="{_LABEL}" '
                     f'font-size="9" text-anchor="middle" '
                     f'font-family="JetBrains Mono">{_esc(lbl)}</text>')
    if x_title:
        p.append(f'<text x="{pad_l+iw/2:.1f}" y="{pad_t+ih+27:.1f}" '
                 f'fill="{_LABEL}" font-size="9" text-anchor="middle">'
                 f'{_esc(x_title)}</text>')
    if y_title:
        cy = pad_t + ih / 2
        p.append(f'<text x="11" y="{cy:.1f}" fill="{_LABEL}" font-size="9" '
                 f'text-anchor="middle" transform="rotate(-90 11 {cy:.1f})">'
                 f'{_esc(y_title)}</text>')
    return "".join(p)


def _time_ticks(t0: float, t1: float, x_func, n: int = 4) -> list:
    span_d = (t1 - t0) / 86400.0
    fmt = "%Y-%m" if span_d > 120 else "%m-%d"
    out = []
    for i in range(n + 1):
        tt = t0 + (t1 - t0) * i / n
        lbl = datetime.fromtimestamp(tt, tz=timezone.utc).strftime(fmt)
        out.append((x_func(tt), lbl))
    return out


def _lin_ticks(lo: float, hi: float, y_func, n: int = 4,
               fmt: str = "{:.0f}") -> list:
    if hi <= lo:
        hi = lo + 1.0
    return [(y_func(lo + (hi - lo) * i / n), fmt.format(lo + (hi - lo) * i / n))
            for i in range(n + 1)]


def _fmt_hours(h: float) -> str:
    if h < 1 / 60:
        return f"{round(h * 3600)}s"
    if h < 1:
        return f"{round(h * 60)}m"
    if h < 48:
        return f"{h:.0f}h"
    return f"{h / 24:.0f}d"


def _render_stats_kpis(quakes: list[Earthquake], context: dict) -> str:
    """KPIs estadísticos del catálogo: N, b±err, Mc, rango, energía, periodo."""

    from shakevision.processing import seismic_stats as ss
    if not quakes:
        return f'<p style="color:#71717a">{_esc(t("report.pro.insufficient"))}</p>'
    mags = [q.magnitude for q in quakes]
    times = [q.timestamp_unix for q in quakes]
    bv = ss.b_value(mags)
    total_e = sum(ss.energy_joules(m) for m in mags)
    if context.get("from") and context.get("to"):
        span_d = max(0.0, (float(context["to"]) - float(context["from"])) / 86400.0)
    else:
        span_d = (max(times) - min(times)) / 86400.0 if times else 0.0

    items = [(_esc(t("report.pro.n")), str(len(quakes)))]
    if bv:
        items.append((_esc(t("report.an.kpi.bvalue")),
                      f"{bv['b']:.2f} ± {bv['b_err']:.2f}"))
        items.append((_esc(t("report.an.kpi.mc")), f"M {bv['mc']:.1f}"))
    items.append((_esc(t("report.pro.mag_range")),
                  f"M {min(mags):.1f}–{max(mags):.1f}"))
    items.append((_esc(t("report.pro.energy")), _fmt_energy(total_e)))
    items.append((_esc(t("report.an.kpi.timespan")),
                  _esc(t("report.an.kpi.span_days", n=int(round(span_d))))))
    cells = "".join(
        f"<div class='pro-kpi'><span>{lbl}</span><strong>{_esc(val)}</strong></div>"
        for lbl, val in items)
    return f"<div class='an-kpis'>{cells}</div>"


def _render_findings(quakes: list[Earthquake], context: dict) -> str:
    """Párrafo de interpretación auto-generado a partir de la estadística."""

    import statistics as _st

    from shakevision.processing import seismic_stats as ss
    if len(quakes) < 10:
        return ""
    mags = [q.magnitude for q in quakes]
    times = [q.timestamp_unix for q in quakes]
    depths = [q.depth_km for q in quakes]
    n = len(quakes)
    if context.get("from") and context.get("to"):
        days = int(round((float(context["to"]) - float(context["from"])) / 86400))
    else:
        days = int(round((max(times) - min(times)) / 86400))
    parts = [t("report.an.findings.overview", n=n, mmin=f"{min(mags):.1f}",
              mmax=f"{max(mags):.1f}", days=days,
              region=context.get("region") or "—")]
    bv = ss.b_value(mags)
    if bv:
        b = bv["b"]
        cmp_key = ("b_typical" if 0.85 <= b <= 1.15
                   else ("b_high" if b > 1.15 else "b_low"))
        parts.append(t("report.an.findings.bvalue", b=f"{b:.2f}",
                       err=f"{bv['b_err']:.2f}", mc=f"{bv['mc']:.1f}",
                       cmp=t(f"report.an.findings.{cmp_key}")))
    energies = sorted((ss.energy_joules(m) for m in mags), reverse=True)
    top_share = energies[0] / (sum(energies) or 1.0) * 100
    if top_share >= 50:
        parts.append(t("report.an.findings.energy_dom",
                       m=f"{max(mags):.1f}", pct=f"{top_share:.0f}"))
    else:
        parts.append(t("report.an.findings.energy_dist", pct=f"{top_share:.0f}"))
    s = ss.mc_b_timeseries(times, mags)
    if s and len(s["b"]) >= 3:
        bm = _st.mean(s["b"])
        stable = (_st.pstdev(s["b"]) / bm < 0.15) if bm else True
        parts.append(t("report.an.findings.mcb_stable" if stable
                       else "report.an.findings.mcb_var"))
    sp = ss.spatial_density([q.longitude for q in quakes],
                            [q.latitude for q in quakes], mags)
    if sp and sp["cells"]:
        share = max(c[2] for c in sp["cells"]) / n * 100
        key = "spatial_clustered" if share >= 12 else "spatial_dispersed"
        parts.append(t(f"report.an.findings.{key}", pct=f"{share:.0f}"))
    dp = ss.depth_percentiles(depths)
    if dp:
        shallow = sum(1 for d in depths if d < 70) / len(depths) * 100
        parts.append(t("report.an.findings.depth", md=f"{dp['p50']:.0f}",
                       pct=f"{shallow:.0f}"))
    return ('<div class="findings"><p>'
            + " ".join(_esc(p) for p in parts) + "</p></div>")


def _render_methods_block(quakes: list[Earthquake], context: dict,
                          now: float) -> str:
    """Advertencias de validez + lista de métodos + tabla de procedencia."""

    from shakevision.processing import seismic_stats as ss
    mags = [q.magnitude for q in quakes] if quakes else []
    bv = ss.b_value(mags) if mags else None
    minmag = context.get("min_mag")

    warns = []
    span = (max(mags) - min(mags)) if mags else 0.0
    if bv and (span < 2.5
               or (minmag is not None and bv["mc"] - float(minmag) < 0.5)):
        warns.append(t("report.an.warn.bvalue",
                       minmag=(f"{float(minmag):.1f}" if minmag is not None
                               else f"{min(mags):.1f}")))
    warns.append(t("report.an.warn.magtype"))
    if mags:
        en = sorted((ss.energy_joules(m) for m in mags), reverse=True)
        if en[0] / (sum(en) or 1.0) >= 0.5:
            warns.append(t("report.an.warn.energy"))
    warn_html = ""
    if warns:
        lis = "".join(f"<li>{_esc(w)}</li>" for w in warns)
        warn_html = (f'<div class="warn-box"><div class="warn-title">⚠ '
                     f'{_esc(t("report.an.warn.title"))}</div><ul>{lis}'
                     f"</ul></div>")

    step = "—"
    extent = "—"
    if quakes:
        sp = ss.spatial_density([q.longitude for q in quakes],
                                [q.latitude for q in quakes], mags)
        if sp:
            step = f'{sp["step"]:.1f}'
        la = [q.latitude for q in quakes]
        lo = [q.longitude for q in quakes]
        extent = (f"{min(la):.1f}…{max(la):.1f}°N, "
                  f"{min(lo):.1f}…{max(lo):.1f}°E")
    methods = [t("report.an.methods.mc"), t("report.an.methods.b"),
               t("report.an.methods.energy"), t("report.an.methods.moment"),
               t("report.an.methods.section"),
               t("report.an.methods.spatial", step=step)]
    methods_html = ('<ul class="methods-list">'
                    + "".join(f"<li>{_esc(m)}</li>" for m in methods) + "</ul>")

    rng = "—"
    if context.get("from") and context.get("to"):
        rng = f'{_fmt_date(context["from"])} → {_fmt_date(context["to"])}'
    mm = context.get("min_mag")

    def _row(label, value):
        return (f"<tr><th>{_esc(label)}</th>"
                f"<td>{_esc(value)}</td></tr>")

    rows = [
        _row(t("report.an.params.region"), context.get("region") or "—"),
        _row(t("report.an.params.range"), rng),
        _row(t("report.an.params.minmag"),
             f"M ≥ {float(mm):.1f}" if mm is not None else "—"),
        _row(t("report.an.params.extent"), extent),
        _row(t("report.an.params.catalog"), "USGS ANSS ComCat"),
        _row(t("report.an.params.accessed"), _format_now(now)),
        _row(t("report.an.params.magtype"), t("report.an.params.magtype_val")),
    ]
    params_html = (f'<h3>{_esc(t("report.an.params.title"))}</h3>'
                   f'<table class="params-table">{"".join(rows)}</table>')
    return warn_html + methods_html + params_html


def _render_event_table_an(quakes: list[Earthquake], top: int = 30) -> str:
    """Tabla de mayores eventos para el reporte de análisis: añade
    coordenadas (lat/lon) e ID de evento sobre la tabla en vivo."""

    rows_data = sorted(quakes, key=lambda q: q.magnitude, reverse=True)[:top]
    if not rows_data:
        return f'<p style="color:#71717a">{_esc(t("report.no_above_threshold"))}</p>'
    rows = []
    for q in rows_data:
        ts = datetime.fromtimestamp(
            q.timestamp_unix, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        pager, pager_class = "", ""
        if q.pager:
            pager = q.pager.value.upper()
            pager_class = f"pager-{q.pager.value}"
        eid = f'<br><span class="evid">{_esc(q.id)}</span>' if q.id else ""
        rows.append(
            "<tr>"
            f"<td class='time'>{_esc(ts)}{eid}</td>"
            f"<td class='mag'>M {q.magnitude:.1f}</td>"
            f"<td class='coord'>{q.latitude:.2f}</td>"
            f"<td class='coord'>{q.longitude:.2f}</td>"
            f"<td class='depth'>{q.depth_km:.1f} km</td>"
            f"<td>{_esc(q.place) or '—'}</td>"
            f"<td class='pager {pager_class}'>{_esc(pager) or '—'}</td>"
            "</tr>")
    return (
        "<table class='events'><thead><tr>"
        f"<th>{_esc(t('report.table.time_utc'))}</th>"
        f"<th>{_esc(t('report.table.magnitude'))}</th>"
        f"<th>{_esc(t('report.table.lat'))}</th>"
        f"<th>{_esc(t('report.table.lon'))}</th>"
        f"<th>{_esc(t('report.table.depth'))}</th>"
        f"<th>{_esc(t('report.table.location'))}</th>"
        f"<th>{_esc(t('report.table.pager'))}</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>")


def _humanize_window(period_seconds) -> str:
    ps = float(period_seconds or 86400)
    return f"{ps/86400:.0f} d" if ps >= 86400 else f"{ps/3600:.0f} h"


def _render_live_summary(events: list[Earthquake], countries: list[dict],
                         period_seconds, now: float) -> str:
    """Resumen situacional auto-generado para el reporte en vivo (puro).

    ``events`` debe ser el catálogo de la **ventana seleccionada** (el mismo
    universo que el ranking de países), para que el conteo, el mayor evento y
    la región más activa sean coherentes con la etiqueta de ventana.
    """

    win = _humanize_window(period_seconds)
    if not events:
        return ('<div class="findings"><p>'
                + _esc(t("report.live.sum.none", window=win)) + "</p></div>")
    n = len(events)
    mx = max(events, key=lambda q: q.magnitude)
    parts = [t("report.live.sum.overview", window=win, n=n,
              max=f"{mx.magnitude:.1f}")]
    ago_min = max(0, int((now - mx.timestamp_unix) / 60))
    ago = (t("report.minutes_ago", n=ago_min) if ago_min < 60
           else t("report.hours_ago", n=ago_min / 60))
    parts.append(t("report.live.sum.largest", m=f"{mx.magnitude:.1f}",
                   place=mx.place or "—", ago=ago))
    nsig = sum(1 for q in events if q.magnitude >= 4.5)
    if nsig:
        parts.append(t("report.live.sum.significant", n=nsig, thr="4.5"))
    if countries:
        parts.append(t("report.live.sum.active", region=countries[0]["name"],
                       n=countries[0]["count"]))
    return ('<div class="findings"><p>'
            + " ".join(_esc(p) for p in parts) + "</p></div>")


def _render_live_notes(now: float, period_seconds, station_label: str) -> str:
    """Fuentes + advertencia de datos preliminares + tabla de procedencia.

    (El reporte en vivo es monitoreo puro: sin capa estadística pro, así que
    aquí no hay métodos de b-value ni advertencia de tipo de magnitud para el
    ajuste — solo la naturaleza preliminar de los datos en tiempo real.)
    """

    win = _humanize_window(period_seconds)
    warn_html = (f'<div class="warn-box"><div class="warn-title">⚠ '
                 f'{_esc(t("report.an.warn.title"))}</div>'
                 f'<ul><li>{_esc(t("report.live.notes.preliminary"))}</li></ul>'
                 f"</div>")

    def _row(label, value):
        return f"<tr><th>{_esc(label)}</th><td>{_esc(value)}</td></tr>"

    rows = [
        _row(t("report.live.params.source"),
             t("report.live.notes.source", window=win)),
        _row(t("report.live.params.window"), win),
        _row(t("report.an.params.accessed"), _format_now(now)),
        _row(t("report.html.meta.station").rstrip(":"), station_label or "—"),
    ]
    params_html = (f'<h3>{_esc(t("report.an.params.title"))}</h3>'
                   f'<table class="params-table">{"".join(rows)}</table>')
    return warn_html + params_html


def _render_energy_svg(quakes: list[Earthquake], width: int = 430,
                       height: int = 230) -> str:
    """Liberación de energía: nº acumulado (eje izq.) + energía acumulada
    (eje der., J) en el tiempo. Doble eje Y."""

    from shakevision.processing import seismic_stats as ss
    if len(quakes) < 5:
        return ""
    cum = ss.cumulative_series(
        [q.timestamp_unix for q in quakes], [q.magnitude for q in quakes])
    ts = cum["t"]
    if len(ts) < 2:
        return ""
    count, energy = cum["count"], cum["energy_cum"]
    t0, t1 = ts[0], ts[-1]
    if t1 <= t0:
        return ""
    pad_l, pad_r, pad_t, pad_b = 38, 48, 20, 30
    iw, ih = width - pad_l - pad_r, height - pad_t - pad_b
    cmax = count[-1] or 1
    emax = energy[-1] or 1.0

    def _x(tt):
        return pad_l + (tt - t0) / (t1 - t0) * iw

    def _yl(c):
        return pad_t + (1 - c / cmax) * ih

    def _yr(e):
        return pad_t + (1 - e / emax) * ih

    pc = " ".join(f"{_x(ts[i]):.1f},{_yl(count[i]):.1f}" for i in range(len(ts)))
    pe = " ".join(f"{_x(ts[i]):.1f},{_yr(energy[i]):.1f}" for i in range(len(ts)))
    frame = _plot_frame(pad_l, pad_t, iw, ih, _time_ticks(t0, t1, _x),
                        _lin_ticks(0, cmax, _yl, 4, "{:.0f}"))
    # Eje derecho (energía, J) en naranja.
    rax = [f'<line x1="{pad_l+iw}" y1="{pad_t}" x2="{pad_l+iw}" '
           f'y2="{pad_t+ih}" stroke="{_AXIS}" stroke-width="1"/>']
    for i in range(5):
        e = emax * i / 4
        rax.append(f'<text x="{pad_l+iw+5}" y="{_yr(e)+3:.1f}" fill="#d97706" '
                   f'font-size="8" text-anchor="start" '
                   f'font-family="JetBrains Mono">{e:.0e}</text>')
    return (
        _SVG_HEAD.format(w=width, h=height) + frame + "".join(rax)
        + _legend(pad_l, [("#3b82f6", "N"), ("#f59e0b", "J")])
        + f'<polyline points="{pc}" fill="none" stroke="#3b82f6" stroke-width="2"/>'
        + f'<polyline points="{pe}" fill="none" stroke="#f59e0b" stroke-width="2"/>'
        + "</svg>")


def _render_mcb_svg(quakes: list[Earthquake], width: int = 430,
                    height: int = 240) -> str:
    """Calidad del catálogo: b(t) azul + Mc(t) naranja en ventanas temporales."""

    from shakevision.processing import seismic_stats as ss
    s = ss.mc_b_timeseries(
        [q.timestamp_unix for q in quakes], [q.magnitude for q in quakes])
    if not s or len(s["t"]) < 2:
        return ""
    ts, b, mc = s["t"], s["b"], s["mc"]
    be = s.get("b_err") or [0.0] * len(b)
    t0, t1 = ts[0], ts[-1]
    if t1 <= t0:
        return ""
    pad_l, pad_r, pad_t, pad_b = 34, 38, 20, 30
    iw, ih = width - pad_l - pad_r, height - pad_t - pad_b

    def _rng(v):
        lo, hi = min(v), max(v)
        return (lo, hi + 1.0) if hi <= lo else (lo, hi)

    blo, bhi = _rng([b[i] - be[i] for i in range(len(b))]
                    + [b[i] + be[i] for i in range(len(b))])
    mlo, mhi = _rng(mc)

    def _x(tt):
        return pad_l + (tt - t0) / (t1 - t0) * iw

    def _yb(v):
        return pad_t + (1 - (v - blo) / (bhi - blo)) * ih

    def _ym(v):
        return pad_t + (1 - (v - mlo) / (mhi - mlo)) * ih

    pb = " ".join(f"{_x(ts[i]):.1f},{_yb(b[i]):.1f}" for i in range(len(ts)))
    pm = " ".join(f"{_x(ts[i]):.1f},{_ym(mc[i]):.1f}" for i in range(len(ts)))
    # Banda ±1σ alrededor de b(t).
    up = [f"{_x(ts[i]):.1f},{_yb(b[i]+be[i]):.1f}" for i in range(len(ts))]
    dn = [f"{_x(ts[i]):.1f},{_yb(b[i]-be[i]):.1f}" for i in range(len(ts))]
    band = (f'<polygon points="{" ".join(up + dn[::-1])}" '
            f'fill="#3b82f6" fill-opacity="0.12" stroke="none"/>')
    frame = _plot_frame(pad_l, pad_t, iw, ih, _time_ticks(t0, t1, _x),
                        _lin_ticks(blo, bhi, _yb, 4, "{:.1f}"))
    rax = [f'<line x1="{pad_l+iw}" y1="{pad_t}" x2="{pad_l+iw}" '
           f'y2="{pad_t+ih}" stroke="{_AXIS}" stroke-width="1"/>']
    for i in range(5):
        v = mlo + (mhi - mlo) * i / 4
        rax.append(f'<text x="{pad_l+iw+5}" y="{_ym(v)+3:.1f}" fill="#d97706" '
                   f'font-size="8" text-anchor="start" '
                   f'font-family="JetBrains Mono">{v:.1f}</text>')
    return (
        _SVG_HEAD.format(w=width, h=height) + frame + "".join(rax) + band
        + _legend(pad_l, [("#3b82f6", "b"), ("#f59e0b", "Mc")])
        + f'<polyline points="{pb}" fill="none" stroke="#3b82f6" stroke-width="2"/>'
        + f'<polyline points="{pm}" fill="none" stroke="#f59e0b" stroke-width="2" '
        + 'stroke-dasharray="4 3"/>'
        + "</svg>")


def _render_spatial_svg(quakes: list[Earthquake], width: int = 430,
                        height: int = 240) -> str:
    """Densidad espacial: rejilla lon × lat con celdas coloreadas por conteo."""

    from shakevision.processing import seismic_stats as ss
    sp = ss.spatial_density(
        [q.longitude for q in quakes], [q.latitude for q in quakes],
        [q.magnitude for q in quakes])
    if not sp or not sp["cells"]:
        return ""
    lon0, lon1 = sp["lon"]
    lat0, lat1 = sp["lat"]
    step = sp["step"] or 1.0
    pad_l, pad_r, pad_t, pad_b = 40, 14, 20, 30
    iw, ih = width - pad_l - pad_r, height - pad_t - pad_b
    dlon = (lon1 - lon0) + step
    dlat = (lat1 - lat0) + step
    sx = iw / dlon
    sy = ih / dlat
    cw = max(2.0, step * sx)
    ch = max(2.0, step * sy)
    maxc = max(c[2] for c in sp["cells"]) or 1

    def _xc(lon):
        return pad_l + (lon - (lon0 - step / 2)) * sx

    def _yc(lat):
        return pad_t + ih - (lat - (lat0 - step / 2)) * sy

    rects = []
    for lon, lat, cnt, _mx in sp["cells"]:
        x = _xc(lon) - cw / 2
        y = _yc(lat) - ch / 2
        col = _ramp_color((cnt - 1) / max(1, maxc - 1))
        rects.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{cw:.1f}" '
                     f'height="{ch:.1f}" fill="{col}" fill-opacity="0.9"/>')
    midlon, midlat = (lon0 + lon1) / 2, (lat0 + lat1) / 2
    x_ticks = [(_xc(lon0), f"{lon0:.0f}"), (_xc(midlon), f"{midlon:.0f}"),
               (_xc(lon1), f"{lon1:.0f}")]
    y_ticks = [(_yc(lat0), f"{lat0:.0f}"), (_yc(midlat), f"{midlat:.0f}"),
               (_yc(lat1), f"{lat1:.0f}")]
    frame = _plot_frame(pad_l, pad_t, iw, ih, x_ticks, y_ticks,
                        t("web.dashboard.axis.longitude"),
                        t("web.dashboard.axis.latitude"))
    # Leyenda de color (conteo bajo→alto) arriba a la derecha.
    lg = []
    lx = pad_l + iw - len(_DENSITY_RAMP) * 11 - 4
    for i, col in enumerate(_DENSITY_RAMP):
        lg.append(f'<rect x="{lx + i*11:.1f}" y="6" width="11" height="7" '
                  f'fill="{col}"/>')
    lg.append(f'<text x="{lx-3:.1f}" y="13" fill="{_LABEL}" font-size="8" '
              f'text-anchor="end" font-family="JetBrains Mono">1</text>')
    lg.append(f'<text x="{lx + len(_DENSITY_RAMP)*11 + 2:.1f}" y="13" '
              f'fill="{_LABEL}" font-size="8" text-anchor="start" '
              f'font-family="JetBrains Mono">{maxc}</text>')
    return (_SVG_HEAD.format(w=width, h=height) + frame + "".join(rects)
            + "".join(lg) + "</svg>")


def _render_cross_section_svg(quakes: list[Earthquake], width: int = 430,
                              height: int = 240) -> str:
    """Sección de profundidad: distancia ⊥ a la fosa (PCA) × profundidad."""

    from shakevision.processing import seismic_stats as ss
    sec = ss.cross_section(
        [q.latitude for q in quakes], [q.longitude for q in quakes],
        [q.depth_km for q in quakes], [q.magnitude for q in quakes])
    if not sec:
        return ""
    xs = [p[0] for p in sec]
    ds = [p[1] for p in sec]
    xmin, xmax = min(xs), max(xs)
    if xmax <= xmin:
        xmax = xmin + 1.0
    dmax = max(ds) or 1.0
    pad_l, pad_r, pad_t, pad_b = 42, 14, 16, 30
    iw, ih = width - pad_l - pad_r, height - pad_t - pad_b

    def _x(d):
        return pad_l + (d - xmin) / (xmax - xmin) * iw

    def _y(depth):
        return pad_t + (depth / dmax) * ih          # profundidad hacia abajo

    frame = _plot_frame(
        pad_l, pad_t, iw, ih,
        _lin_ticks(xmin, xmax, _x, 4, "{:.0f}"),
        _lin_ticks(0, dmax, _y, 4, "{:.0f}"),
        "km", t("web.dashboard.axis.depth_km"))
    dots = []
    for dist, depth, mag in sec:
        r = max(1.8, (mag if mag > 0 else 1.5) * 1.0)
        dots.append(f'<circle cx="{_x(dist):.1f}" cy="{_y(depth):.1f}" '
                    f'r="{r:.1f}" fill="#2563eb" fill-opacity="0.6"/>')
    return _SVG_HEAD.format(w=width, h=height) + frame + "".join(dots) + "</svg>"


def _render_inter_event_svg(quakes: list[Earthquake], width: int = 430,
                            height: int = 240) -> str:
    """Histograma (log) de intervalos entre eventos consecutivos."""

    from shakevision.processing import seismic_stats as ss
    ie = ss.inter_event_times([q.timestamp_unix for q in quakes])
    if not ie or not ie["counts"]:
        return ""
    counts = ie["counts"]
    hours = ie["hours"]
    cmax = max(counts) or 1
    n = len(counts)
    pad_l, pad_r, pad_t, pad_b = 34, 12, 16, 30
    iw, ih = width - pad_l - pad_r, height - pad_t - pad_b
    bw = iw / n

    def _y(c):
        return pad_t + (1 - c / cmax) * ih

    bars = []
    for i, c in enumerate(counts):
        bx = pad_l + i * bw
        by = _y(c)
        bars.append(f'<rect x="{bx + 0.6:.1f}" y="{by:.1f}" '
                    f'width="{bw - 1.2:.1f}" height="{pad_t + ih - by:.1f}" '
                    f'fill="#a855f7" fill-opacity="0.85"/>')
    x_ticks = [(pad_l + (i + 0.5) * bw, _fmt_hours(hours[i]))
               for i in {0, n // 3, 2 * n // 3, n - 1}]
    x_ticks.sort()
    frame = _plot_frame(pad_l, pad_t, iw, ih, x_ticks,
                        _lin_ticks(0, cmax, _y, 4, "{:.0f}"),
                        t("web.dashboard.axis.gap"),
                        t("web.dashboard.axis.count"))
    return _SVG_HEAD.format(w=width, h=height) + frame + "".join(bars) + "</svg>"
