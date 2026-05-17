"""
Caché en disco con TTL para los feeds externos.

Ahorra solicitudes a la red repetidas y permite que la UI tenga
contenido inicial en menos de 100 ms aunque la red no esté disponible.

Diseño
------
* Un único directorio raíz (``~/.cache/shakevision/`` por defecto).
* Cada entrada se guarda como ``<key>.bin`` + ``<key>.meta.json``.
* La frescura se determina por la diferencia entre ``time.time()`` y
  el ``mtime`` del fichero: si pasa de ``ttl_s`` se considera stale.
* No usamos ningún backend SQLite ni clase compleja; basta con
  archivos binarios para feeds < 1 MB.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional


# Directorio por defecto. El usuario puede sobrescribirlo en el
# constructor de ``FileCache``.
DEFAULT_CACHE_DIR: Path = Path.home() / ".cache" / "shakevision"


class FileCache:
    """Caché clave→bytes con TTL basado en mtime."""

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        default_ttl_s: float = 300.0,  # 5 min
    ) -> None:
        if default_ttl_s <= 0:
            raise ValueError("default_ttl_s debe ser positivo")
        self._dir = Path(cache_dir or DEFAULT_CACHE_DIR)
        self._default_ttl = float(default_ttl_s)

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------
    @property
    def directory(self) -> Path:
        return self._dir

    def get(self, key: str, ttl_s: Optional[float] = None) -> Optional[bytes]:
        """Devuelve el contenido si está fresco, o ``None`` en otro caso.

        No se elimina la entrada caducada; simplemente no se devuelve.
        Una llamada posterior a ``set`` la sobrescribe.
        """

        path = self._path_for(key)
        if not path.exists():
            return None

        ttl = float(ttl_s if ttl_s is not None else self._default_ttl)
        age = time.time() - path.stat().st_mtime
        if age > ttl:
            return None

        try:
            return path.read_bytes()
        except OSError:
            return None

    def set(self, key: str, data: bytes) -> None:
        """Guarda los bytes bajo la clave indicada (atómico)."""

        self._dir.mkdir(parents=True, exist_ok=True)
        target = self._path_for(key)
        # Escritura atómica: tmp + os.replace
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, target)

    def age_seconds(self, key: str) -> Optional[float]:
        """Devuelve la edad de la entrada o ``None`` si no existe."""

        path = self._path_for(key)
        if not path.exists():
            return None
        return time.time() - path.stat().st_mtime

    def invalidate(self, key: str) -> None:
        """Elimina explícitamente la entrada (sin error si ya no existe)."""

        path = self._path_for(key)
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    def clear(self) -> None:
        """Vacía completamente el directorio (cuidado: borra todo)."""

        if not self._dir.exists():
            return
        for child in self._dir.iterdir():
            if child.is_file() and child.suffix == ".bin":
                try:
                    child.unlink()
                except OSError:
                    pass

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------
    def _path_for(self, key: str) -> Path:
        # Sanitizar la clave para que pueda ser un nombre de archivo
        # seguro en cualquier sistema. Reemplazamos cualquier carácter
        # no alfanumérico (más "_-.") por un guion bajo.
        safe = "".join(
            c if c.isalnum() or c in "_-." else "_" for c in key
        )
        return self._dir / f"{safe}.bin"
