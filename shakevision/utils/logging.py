"""
Configuración centralizada del sistema de logs.

Proporciona un único punto de inicialización (``setup_logging``) que
configura el logger raíz con un formato uniforme y un nivel sensato por
defecto. Cualquier módulo puede obtener su logger con
``logging.getLogger(__name__)`` sin preocuparse por la configuración.
"""

from __future__ import annotations

import logging
import sys
from logging import Logger


# Formato común para todos los mensajes
_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


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
        handler = logging.StreamHandler(stream=sys.stdout)
        handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
        root.addHandler(handler)

    root.setLevel(level)

    # Devolver el logger específico del paquete para uso conveniente
    return logging.getLogger("shakevision")
