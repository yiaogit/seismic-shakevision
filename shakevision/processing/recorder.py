"""
Grabador de eventos sísmicos en formato MiniSEED.

Cuando el detector STA/LTA dispara un evento, ``EventRecorder`` extrae
del búfer circular una ventana que abarca ``pre_event_seconds`` segundos
antes del disparo y guarda los tres canales en un fichero ``.mseed``.

Por sencillez, esta primera versión hace **un único snapshot** justo en
el momento del disparo. La ventana ``pre_event_seconds`` ya está dentro
del búfer (5 minutos por defecto), así que basta con extraerla en ese
instante. La extensión a "guardar también ``post_event_seconds`` después
del disparo" se puede añadir en una iteración posterior usando un
``QTimer`` de un solo disparo.

Diseño
------
* Carpeta de destino: ``~/SeismicGuard/recordings/`` (creada bajo
  demanda). El usuario puede sobrescribirla por argumento.
* Formato: MiniSEED (estándar de la sismología, leído por ObsPy,
  Madagascar, SAC, etc.).
* Nombre de fichero:
  ``YYYYMMDDTHHMMSS_<network>_<station>.mseed``.
* Errores: cualquier excepción se captura y se devuelve en el
  resultado para no detener la UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from shakevision.processing.buffer import RingBuffer


# Carpeta por defecto donde se guardan los eventos.
DEFAULT_RECORDINGS_DIR: Path = Path.home() / "SeismicGuard" / "recordings"

# Mapeo canal interno -> sufijo del nombre estándar SEED
CHANNEL_TO_SEED: dict[str, str] = {"Z": "EHZ", "N": "EHN", "E": "EHE"}


@dataclass(frozen=True)
class RecordingResult:
    """Resultado de intentar grabar un evento."""

    success: bool
    path: Optional[Path]
    error: Optional[str]


class EventRecorder:
    """Persistencia de eventos sísmicos en MiniSEED."""

    def __init__(
        self,
        sample_rate_hz: int,
        pre_event_seconds: float,
        recordings_dir: Optional[Path] = None,
    ) -> None:
        if sample_rate_hz <= 0:
            raise ValueError("sample_rate_hz debe ser positivo")
        if pre_event_seconds <= 0:
            raise ValueError("pre_event_seconds debe ser positivo")

        self._sample_rate = int(sample_rate_hz)
        self._pre_event_s = float(pre_event_seconds)
        self._recordings_dir = recordings_dir or DEFAULT_RECORDINGS_DIR

    # ------------------------------------------------------------------
    # Configuración
    # ------------------------------------------------------------------
    @property
    def recordings_dir(self) -> Path:
        return self._recordings_dir

    def update_pre_event_seconds(self, seconds: float) -> None:
        """Cambia la ventana previa al evento."""

        if seconds <= 0:
            raise ValueError("seconds debe ser positivo")
        self._pre_event_s = float(seconds)

    # ------------------------------------------------------------------
    # Grabación
    # ------------------------------------------------------------------
    def record_event(
        self,
        buffer: RingBuffer,
        network: str,
        station: str,
        location: str = "",
        trigger_time_unix: Optional[float] = None,
    ) -> RecordingResult:
        """Extrae la ventana previa al evento y la guarda en disco."""

        # 1. Obtener la ventana de muestras
        snapshot = buffer.read_window(seconds=self._pre_event_s)
        if all(s.size == 0 for s in snapshot.samples.values()):
            return RecordingResult(False, None, "búfer vacío")

        # 2. Construir el flujo ObsPy (importación tardía)
        try:
            from obspy import Stream, Trace, UTCDateTime
        except Exception as exc:
            return RecordingResult(False, None, f"ObsPy no disponible: {exc}")

        # Marca de tiempo del primer sample de la ventana en UTC
        end_ts = trigger_time_unix or snapshot.latest_timestamp_unix
        n_samples = next(iter(snapshot.samples.values())).size
        start_ts = end_ts - (n_samples - 1) / self._sample_rate

        traces = []
        for channel_letter, samples in snapshot.samples.items():
            if samples.size == 0:
                continue
            seed_channel = CHANNEL_TO_SEED.get(channel_letter, f"EH{channel_letter}")
            stats = {
                "network": network,
                "station": station,
                "location": location,
                "channel": seed_channel,
                "sampling_rate": float(self._sample_rate),
                "starttime": UTCDateTime(start_ts),
            }
            # MiniSEED soporta float32; convertimos para conservar tipo
            traces.append(Trace(data=np.asarray(samples, dtype=np.float32),
                                header=stats))

        stream = Stream(traces=traces)

        # 3. Calcular ruta de salida y crear directorio
        try:
            self._recordings_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return RecordingResult(False, None, f"no se pudo crear el directorio: {exc}")

        timestamp_str = UTCDateTime(end_ts).strftime("%Y%m%dT%H%M%S")
        filename = f"{timestamp_str}_{network}_{station}.mseed"
        out_path = self._recordings_dir / filename

        # 4. Escribir
        try:
            stream.write(str(out_path), format="MSEED")
        except Exception as exc:
            return RecordingResult(False, None, f"error al escribir MiniSEED: {exc}")

        return RecordingResult(success=True, path=out_path, error=None)


# ============================================================
# Helper público
# ============================================================
def build_event_filename(
    network: str, station: str, end_ts: float
) -> str:
    """Devuelve el nombre estándar de fichero para un evento.

    Se expone para que los tests puedan validarlo sin crear un
    ``EventRecorder`` ni tocar disco.
    """

    # Importación tardía para que esta utilidad no fuerce la carga de ObsPy
    from obspy import UTCDateTime

    timestamp_str = UTCDateTime(end_ts).strftime("%Y%m%dT%H%M%S")
    return f"{timestamp_str}_{network}_{station}.mseed"


def build_event_filename_local(
    network: str, station: str, end_ts: float
) -> str:
    """Variante de ``build_event_filename`` que no necesita ObsPy.

    Usa ``datetime`` puro (UTC). Útil en tests sin ObsPy y como
    respaldo en plataformas donde ObsPy aún no esté instalado.
    """

    from datetime import datetime, timezone

    dt = datetime.fromtimestamp(end_ts, tz=timezone.utc)
    timestamp_str = dt.strftime("%Y%m%dT%H%M%S")
    return f"{timestamp_str}_{network}_{station}.mseed"
