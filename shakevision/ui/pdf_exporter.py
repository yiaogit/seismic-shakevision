"""
Exportador de reportes a PDF.

En lugar de añadir WeasyPrint o ReportLab (que arrastran Cairo y
otras dependencias nativas), aprovechamos que ``QWebEngineView`` ya
sabe imprimir cualquier HTML a PDF de forma nativa
(``page().printToPdf(...)``). Es el mismo motor (Chromium) que usa
Chrome cuando eliges "Guardar como PDF" en su diálogo de impresión.

Flujo
-----

  generator.render(quakes, ...)        # → str HTML completo
        │
        ▼
  PdfExporter.export(html, output_path)
        │
        ├── crea un QWebEngineView temporal (oculto)
        ├── carga el HTML con setHtml(...)
        ├── espera loadFinished
        ├── llama a page().printToPdf(callback)
        ├── recibe los bytes en el callback
        └── escribe el fichero + emit finished(path)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QMarginsF, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QPageLayout, QPageSize

logger = logging.getLogger(__name__)


# v0.7-B: márgenes A4 alineados con @page del template (styles.css)
# para que el CSS y Qt coincidan al milímetro y no haya "doble margen"
# (Qt aplica el suyo + Chromium aplica el del @page).
DEFAULT_MARGINS_MM = (18, 18, 18, 18)

# v0.7-B: tamaño del view aproximadamente al ancho imprimible de A4
# (210 mm - 2×18 mm = 174 mm ≈ 657 px a 96 dpi) para minimizar el
# escalado que Chromium hace al imprimir. Mantenemos un alto generoso
# para que el contenido fluya naturalmente y Chromium pagine bien.
_PDF_VIEW_WIDTH_PX: int = 794      # A4 width 210mm a 96dpi (sin margen)
_PDF_VIEW_HEIGHT_PX: int = 1123    # A4 height 297mm a 96dpi


class PdfExportError(Exception):
    """Error al generar un PDF."""


class PdfExporter(QObject):
    """Renderiza un HTML a PDF usando QWebEngineView en segundo plano."""

    finished = Signal(Path)              # ruta del PDF cuando termina con éxito
    failed = Signal(str)                 # mensaje legible cuando falla

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._view = None     # QWebEngineView (creado bajo demanda)
        self._target: Optional[Path] = None

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def export(self, html: str, output_path: Path) -> None:
        """Inicia la generación asíncrona del PDF.

        El método regresa inmediatamente; cuando el PDF está listo se
        emite ``finished(path)``. En caso de error, ``failed(msg)``.
        """

        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView
        except ImportError as exc:
            self.failed.emit(f"QtWebEngine no disponible: {exc}")
            return

        target = Path(output_path).expanduser()
        if target.suffix.lower() != ".pdf":
            target = target.with_suffix(".pdf")
        target.parent.mkdir(parents=True, exist_ok=True)
        self._target = target

        # Crear el view oculto. v0.7-B: el tamaño coincide con A4 full
        # a 96dpi (sin descontar márgenes — la CSS @page se encarga).
        # Esto reduce el escalado de Chromium y evita que las columnas
        # fijas de la tabla se vean comprimidas/cortadas.
        self._view = QWebEngineView()
        self._view.setAttribute = getattr(self._view, "setAttribute", lambda *a, **k: None)
        self._view.resize(_PDF_VIEW_WIDTH_PX, _PDF_VIEW_HEIGHT_PX)

        # Conectar el evento "carga terminada" para disparar la impresión
        self._view.loadFinished.connect(self._on_load_finished)

        # Cargar el HTML (URL base = directorio actual para resolver imágenes)
        self._view.setHtml(html, baseUrl=QUrl.fromLocalFile(
            str(Path.cwd()) + "/"
        ))

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------
    @Slot(bool)
    def _on_load_finished(self, ok: bool) -> None:
        if not ok:
            self._cleanup()
            self.failed.emit("Falló la carga del HTML")
            return
        if self._view is None or self._target is None:
            return

        # Configurar el layout A4 con márgenes
        layout = QPageLayout(
            QPageSize(QPageSize.A4),
            QPageLayout.Portrait,
            QMarginsF(*DEFAULT_MARGINS_MM),
            QPageLayout.Millimeter,
        )
        self._view.page().printToPdf(
            self._on_pdf_ready,
            layout,
        )

    def _on_pdf_ready(self, data: bytes) -> None:
        if self._target is None:
            return
        target = self._target
        try:
            if not data:
                raise PdfExportError("printToPdf devolvió 0 bytes")
            target.write_bytes(bytes(data))
            logger.info("PDF escrito en %s (%d bytes)", target, target.stat().st_size)
            self.finished.emit(target)
        except Exception as exc:
            self.failed.emit(f"Error al escribir el PDF: {exc}")
        finally:
            self._cleanup()

    def _cleanup(self) -> None:
        if self._view is not None:
            try:
                self._view.deleteLater()
            except Exception:
                pass
        self._view = None
        self._target = None
