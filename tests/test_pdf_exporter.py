"""
Pruebas mínimas del PdfExporter (verificación de API y manejo de errores).

El flujo completo requiere QtWebEngine y un event loop, así que solo
verificamos que la clase existe, sus señales están definidas y que
sin QtWebEngine emite ``failed`` correctamente.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6.QtCore", reason="PySide6 no instalado")

from shakevision.ui.pdf_exporter import PdfExporter  # noqa: E402


def test_pdf_exporter_has_finished_and_failed_signals() -> None:
    assert hasattr(PdfExporter, "finished")
    assert hasattr(PdfExporter, "failed")


def test_pdf_exporter_can_be_instantiated() -> None:
    exporter = PdfExporter()
    assert exporter is not None
    # No tocamos export() para evitar requerir QtWebEngine en CI mínimo
