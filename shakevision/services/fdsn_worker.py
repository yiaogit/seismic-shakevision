"""
Worker en hilo para consultas históricas ``fdsnws-event``.

Las consultas al catálogo completo pueden tardar varios segundos y devolver
miles de eventos, así que NO deben correr en el hilo de UI. Este módulo envuelve
``FDSNEventClient`` en un ``QThread`` y expone señales:

  * ``results(list)``        — lista de ``Earthquake`` (éxito)
  * ``failed(str, bool)``    — mensaje legible + flag ``too_many`` (para que la
                               UI sugiera acotar la búsqueda)

Patrón idéntico a ``services/worker.py``: un objeto interno vive en el hilo;
la fachada pública reenvía sus señales y dispara el trabajo vía una señal en
cola (``_request``), de modo que ``run`` se ejecuta SIEMPRE en el hilo worker.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal, Slot

from shakevision.services.cache import FileCache
from shakevision.services.fdsn_event import (
    FDSNEventClient,
    FDSNEventError,
    FDSNTooManyError,
)

logger = logging.getLogger(__name__)


class _FDSNInner(QObject):
    results = Signal(list)
    failed = Signal(str, bool)   # (mensaje, too_many)
    counted = Signal(int, dict)  # (n_eventos, params) — pre-chequeo del tope

    def __init__(self, client: FDSNEventClient) -> None:
        super().__init__()
        self._client = client

    @Slot(dict)
    def run(self, params: dict) -> None:
        try:
            quakes = self._client.query(**params)
            self.results.emit(quakes)
        except FDSNTooManyError as exc:
            self.failed.emit(str(exc), True)
        except FDSNEventError as exc:
            self.failed.emit(str(exc), False)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Consulta fdsnws falló inesperadamente")
            self.failed.emit(str(exc), False)

    @Slot(dict)
    def run_count(self, params: dict) -> None:
        try:
            n = self._client.count(**params)
            self.counted.emit(int(n), params)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Conteo fdsnws falló: %s", exc)
            self.counted.emit(-1, params)     # -1 = no se pudo contar


class FDSNQueryWorker(QObject):
    """Fachada: gestiona el ``QThread`` y reenvía resultados/errores."""

    results = Signal(list)
    failed = Signal(str, bool)
    counted = Signal(int, dict)
    _request = Signal(dict)
    _request_count = Signal(dict)

    def __init__(self, client: Optional[FDSNEventClient] = None,
                 parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._client = client or FDSNEventClient(cache=FileCache())
        self._thread = QThread(self)
        self._inner = _FDSNInner(self._client)
        self._inner.moveToThread(self._thread)
        self._inner.results.connect(self.results)
        self._inner.failed.connect(self.failed)
        self._inner.counted.connect(self.counted)
        self._request.connect(self._inner.run)
        self._request_count.connect(self._inner.run_count)
        self._thread.start()

        # Cerrar el hilo limpiamente al salir de la app.
        try:
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is not None:
                app.aboutToQuit.connect(self.stop)
        except Exception:  # noqa: BLE001
            pass

    def query(self, params: dict) -> None:
        """Encola una consulta (se ejecuta en el hilo worker)."""

        self._request.emit(dict(params))

    def count(self, params: dict) -> None:
        """Encola un pre-chequeo de conteo (emite ``counted(n, params)``)."""

        self._request_count.emit(dict(params))

    def stop(self) -> None:
        if self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(2000)
