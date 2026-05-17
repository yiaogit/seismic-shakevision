"""
Worker Qt para refrescar los feeds en segundo plano.

La UI no debe llamar directamente a los clientes síncronos
``USGSClient`` / ``ShakeNetClient`` porque cada llamada bloquea hasta
15 segundos esperando a la red. ``DataRefreshWorker`` los envuelve en
un ``QThread`` y emite señales con los resultados.

Uso típico
----------

    worker = DataRefreshWorker(usgs_client, shakenet_client)
    worker.earthquakes_ready.connect(self._on_earthquakes)
    worker.stations_ready.connect(self._on_stations)
    worker.error.connect(lambda msg: self.statusBar().showMessage(msg))
    worker.start_periodic_refresh(
        earthquakes_period_s=60,    # cada minuto
        stations_period_s=3600,     # cada hora
    )

    # Al cerrar la ventana:
    worker.stop()
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import (
    Q_ARG,
    QMetaObject,
    QObject,
    Qt,
    QThread,
    QTimer,
    Signal,
    Slot,
)

from shakevision.services.data_models import Earthquake, ShakeStation
from shakevision.services.iris import IRISClient, IRISError
from shakevision.services.shakenet import ShakeNetClient, ShakeNetError
from shakevision.services.usgs import USGSClient, USGSError

logger = logging.getLogger(__name__)


# ============================================================
# Worker (vive en su propio QThread)
# ============================================================
def _hash_earthquakes(quakes: list) -> int:
    """Hash determinista de un lote de Earthquake (id + ts) para deduplicar."""

    return hash(tuple((q.id, q.timestamp_unix) for q in quakes))


def _hash_stations(stations: list) -> int:
    """Hash determinista de un catálogo de ShakeStation."""

    return hash(tuple((s.network, s.code) for s in stations))


class _RefreshWorker(QObject):
    """Trabajo de refresco propiamente dicho, ejecutado en hilo aparte."""

    earthquakes_ready = Signal(list)  # list[Earthquake]
    stations_ready = Signal(list)     # list[ShakeStation]
    error = Signal(str)               # mensaje legible para barra de estado

    def __init__(
        self,
        usgs: USGSClient,
        shakenet: ShakeNetClient,
        period: str = "all_day",
        network: str = "AM",
        iris: Optional[IRISClient] = None,
    ) -> None:
        super().__init__()
        self._usgs = usgs
        self._shakenet = shakenet
        self._iris = iris   # opcional → si None, no se piden estaciones USGS
        self._period = period
        self._network = network

        # Hash del último payload emitido. Si el nuevo es idéntico,
        # ahorramos a la UI una re-renderización completa innecesaria.
        self._last_quakes_hash: int | None = None
        self._last_stations_hash: int | None = None

        # Backoff exponencial para reintentos tras fallos consecutivos.
        # Reseteado a 1 cada éxito.
        self._consecutive_quake_failures: int = 0
        self._consecutive_station_failures: int = 0

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------
    @Slot(str)
    def set_period(self, period: str) -> None:
        """Cambia la ventana temporal de USGS (all_hour/day/week/month).

        Resetea el hash de dedup para forzar una emisión inmediata aunque
        el contenido aparente sea el mismo.
        """

        self._period = period
        self._last_quakes_hash = None

    @Slot()
    def refresh_earthquakes(self) -> None:
        try:
            quakes = self._usgs.fetch_recent(period=self._period)
        except USGSError as exc:
            self._consecutive_quake_failures += 1
            self.error.emit(
                f"USGS: {exc}"
                + (f" (intento {self._consecutive_quake_failures})"
                   if self._consecutive_quake_failures > 1 else "")
            )
            return
        except Exception as exc:  # pragma: no cover - red de seguridad
            self.error.emit(f"USGS error inesperado: {exc}")
            return

        self._consecutive_quake_failures = 0

        # Solo emitir si los datos cambiaron (deduplicación por hash)
        new_hash = _hash_earthquakes(quakes)
        if new_hash == self._last_quakes_hash:
            return
        self._last_quakes_hash = new_hash
        self.earthquakes_ready.emit(quakes)

    @Slot()
    def refresh_stations(self) -> None:
        """Combina catálogos ShakeNet (AM) + IRIS/USGS (IU,US) en un emit.

        Cada fuente puede fallar independientemente sin abortar la otra:
        si ShakeNet está caído pero IRIS responde, igualmente se emite
        la lista de USGS (y viceversa).
        """

        combined: list[ShakeStation] = []

        # --- ShakeNet (AM) ---
        try:
            shake = self._shakenet.fetch_stations(network=self._network)
            combined.extend(shake)
        except ShakeNetError as exc:
            self.error.emit(f"ShakeNet: {exc}")
        except Exception as exc:  # pragma: no cover
            self.error.emit(f"ShakeNet error inesperado: {exc}")

        # --- IRIS/USGS (opcional, solo si se inyectó el cliente) ---
        if self._iris is not None:
            try:
                usgs = self._iris.fetch_stations()
                combined.extend(usgs)
            except IRISError as exc:
                self.error.emit(f"IRIS: {exc}")
            except Exception as exc:  # pragma: no cover
                self.error.emit(f"IRIS error inesperado: {exc}")

        # No emitir si todo falló — la UI ya recibió mensaje de error.
        if not combined:
            return

        new_hash = _hash_stations(combined)
        if new_hash == self._last_stations_hash:
            return
        self._last_stations_hash = new_hash
        self.stations_ready.emit(combined)


# ============================================================
# Fachada pública
# ============================================================
class DataRefreshWorker(QObject):
    """Envoltura amigable: gestiona el QThread + temporizadores."""

    earthquakes_ready = Signal(list)
    stations_ready = Signal(list)
    error = Signal(str)

    def __init__(
        self,
        usgs: USGSClient,
        shakenet: ShakeNetClient,
        period: str = "all_day",
        network: str = "AM",
        parent: Optional[QObject] = None,
        iris: Optional[IRISClient] = None,
    ) -> None:
        super().__init__(parent)

        self._thread = QThread(self)
        self._inner = _RefreshWorker(
            usgs, shakenet, period=period, network=network, iris=iris,
        )
        self._inner.moveToThread(self._thread)

        # Reenvío de señales desde el worker al fachada (la UI
        # solo escucha al objeto público, sin saber del hilo).
        self._inner.earthquakes_ready.connect(self.earthquakes_ready)
        self._inner.stations_ready.connect(self.stations_ready)
        self._inner.error.connect(self.error)

        # Temporizadores periódicos. Se crean en el hilo principal pero
        # los ``timeout`` están conectados a slots que viven en el hilo
        # secundario; Qt entrega esas llamadas vía cola automáticamente.
        self._earthquakes_timer = QTimer(self)
        self._earthquakes_timer.timeout.connect(self._inner.refresh_earthquakes)

        self._stations_timer = QTimer(self)
        self._stations_timer.timeout.connect(self._inner.refresh_stations)

        self._started = False

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------
    def start_periodic_refresh(
        self,
        earthquakes_period_s: float = 60.0,
        stations_period_s: float = 3600.0,
        kick_immediately: bool = True,
    ) -> None:
        """Arranca el hilo y los temporizadores periódicos."""

        if self._started:
            return
        self._started = True

        self._thread.start()

        self._earthquakes_timer.setInterval(int(earthquakes_period_s * 1000))
        self._earthquakes_timer.start()
        self._stations_timer.setInterval(int(stations_period_s * 1000))
        self._stations_timer.start()

        if kick_immediately:
            # Lanzar una primera refresca inmediata.
            # ⚠ NO llamar self._inner.refresh_earthquakes() directamente:
            # eso lo ejecutaría en el hilo de la UI (donde se invocó este
            # método), bloqueándola hasta 15 s mientras urllib hace su
            # petición. Usamos QMetaObject.invokeMethod con
            # QueuedConnection para que la llamada se enrute al hilo
            # destino del QObject (worker thread) sin bloquear al actual.
            QMetaObject.invokeMethod(
                self._inner, "refresh_earthquakes", Qt.QueuedConnection
            )
            QMetaObject.invokeMethod(
                self._inner, "refresh_stations", Qt.QueuedConnection
            )

    def refresh_now(self) -> None:
        """Dispara una refresca puntual sin alterar el calendario periódico."""

        if not self._started:
            return
        # Misma precaución: invocar vía la cola para no bloquear la UI.
        QMetaObject.invokeMethod(
            self._inner, "refresh_earthquakes", Qt.QueuedConnection
        )
        QMetaObject.invokeMethod(
            self._inner, "refresh_stations", Qt.QueuedConnection
        )

    def set_period(self, period: str) -> None:
        """Cambia la ventana temporal del feed USGS y dispara refresco.

        Acepta los nombres de feed conocidos: ``all_hour`` / ``all_day`` /
        ``all_week`` / ``all_month``.
        """

        # Reenviamos a la cola para no tocar atributos compartidos
        # desde el hilo equivocado.
        QMetaObject.invokeMethod(
            self._inner, "set_period",
            Qt.QueuedConnection,
            Q_ARG(str, period),
        )
        if self._started:
            QMetaObject.invokeMethod(
                self._inner, "refresh_earthquakes", Qt.QueuedConnection
            )

    def stop(self) -> None:
        """Detiene los temporizadores y termina el hilo."""

        if not self._started:
            return
        self._started = False
        self._earthquakes_timer.stop()
        self._stations_timer.stop()
        self._thread.quit()
        self._thread.wait(2000)
