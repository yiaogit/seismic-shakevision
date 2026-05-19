"""
Configuración centralizada del sistema de logs.

Proporciona un único punto de inicialización (``setup_logging``) que
configura el logger raíz con un formato uniforme y un nivel sensato por
defecto. Cualquier módulo puede obtener su logger con
``logging.getLogger(__name__)`` sin preocuparse por la configuración.
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from logging import Logger


# Formato común para todos los mensajes
_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def _make_stream_handler() -> logging.Handler:
    """Crea un StreamHandler robusto contra el bug PyInstaller-windowed.

    v0.7.2 fix: en .exe construido con --noconsole (Windows GUI sin
    terminal), ``sys.stdout`` y ``sys.stderr`` son ``None``.
    ``StreamHandler(stream=None)`` revienta con
       "RuntimeError: sys.stderr is None" / "AttributeError: NoneType
        object has no attribute 'write'"
    al primer log emitido (típicamente la línea "Iniciando SeismicGuard
    v0.7.x" en main()).

    Solución: si ambos son None, dirigimos los logs a un fichero en
    ``%TEMP%/seismicguard.log`` (Windows %TEMP%, macOS/Linux /tmp).
    El usuario lo encuentra fácilmente para reportar bugs.
    """

    if sys.stdout is not None:
        return logging.StreamHandler(stream=sys.stdout)
    if sys.stderr is not None:
        return logging.StreamHandler(stream=sys.stderr)
    # Ningún stream disponible — caer a fichero
    log_path = os.path.join(tempfile.gettempdir(), "seismicguard.log")
    try:
        return logging.FileHandler(log_path, mode="a", encoding="utf-8")
    except Exception:  # noqa: BLE001
        # Último recurso: NullHandler para que la app no crashee
        return logging.NullHandler()


def setup_logging(level: int = logging.INFO) -> Logger:
    """Configura el logger raíz y devuelve el logger principal.

    Parameters
    ----------
    level:
        Nivel de severidad mínimo. ``logging.INFO`` por defecto.
    """

    root = logging.getLogger()

    # Evitar añadir varios handlers si se llama más de una vez
    if not root.handlers:
        handler = _make_stream_handler()
        handler.setFormatter(
            logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
        root.addHandler(handler)

    root.setLevel(level)

    # Devolver el logger específico del paquete para uso conveniente
    return logging.getLogger("shakevision")
