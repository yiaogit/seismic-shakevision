"""
Pruebas del ``FileCache``: TTL, escritura atómica, sanitización de
claves y estado tras invalidación.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from shakevision.services.cache import FileCache


# ============================================================
# Construcción
# ============================================================
def test_cache_rejects_invalid_ttl(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        FileCache(cache_dir=tmp_path, default_ttl_s=0)
    with pytest.raises(ValueError):
        FileCache(cache_dir=tmp_path, default_ttl_s=-1)


def test_cache_directory_is_settable(tmp_path: Path) -> None:
    c = FileCache(cache_dir=tmp_path)
    assert c.directory == tmp_path


# ============================================================
# get / set
# ============================================================
def test_get_missing_returns_none(tmp_path: Path) -> None:
    c = FileCache(cache_dir=tmp_path)
    assert c.get("never_set") is None


def test_set_then_get_returns_bytes(tmp_path: Path) -> None:
    c = FileCache(cache_dir=tmp_path, default_ttl_s=10)
    c.set("k", b"hello world")
    assert c.get("k") == b"hello world"


def test_get_returns_none_when_expired(tmp_path: Path) -> None:
    """Manipulamos el mtime para forzar caducidad sin esperar."""

    c = FileCache(cache_dir=tmp_path, default_ttl_s=1)
    c.set("k", b"abc")
    path = next(tmp_path.glob("k.bin"))

    # Forzar que el fichero parezca de hace 1 hora
    long_ago = time.time() - 3600
    os.utime(path, (long_ago, long_ago))

    assert c.get("k") is None
    # Pero seguir disponible si se pide ttl infinito (caché obsoleta)
    assert c.get("k", ttl_s=float("inf")) == b"abc"


def test_age_seconds(tmp_path: Path) -> None:
    c = FileCache(cache_dir=tmp_path)
    assert c.age_seconds("nope") is None
    c.set("k", b"x")
    age = c.age_seconds("k")
    assert age is not None and 0 <= age <= 1


def test_invalidate_removes_file(tmp_path: Path) -> None:
    c = FileCache(cache_dir=tmp_path)
    c.set("k", b"x")
    c.invalidate("k")
    assert c.get("k", ttl_s=float("inf")) is None
    # idempotente
    c.invalidate("k")


def test_clear_removes_all_bin_files(tmp_path: Path) -> None:
    c = FileCache(cache_dir=tmp_path)
    c.set("a", b"1")
    c.set("b", b"2")
    c.clear()
    assert c.get("a", ttl_s=float("inf")) is None
    assert c.get("b", ttl_s=float("inf")) is None


# ============================================================
# Sanitización de claves
# ============================================================
def test_keys_with_unsafe_characters_are_sanitized(tmp_path: Path) -> None:
    """Una clave con barras o ":" no debe escapar del directorio."""

    c = FileCache(cache_dir=tmp_path)
    c.set("usgs/all_day:geojson", b"data")

    # No debe haber ningún subdirectorio creado
    children = [p for p in tmp_path.iterdir()]
    assert all(p.is_file() for p in children)
    # Y el get debe seguir funcionando con la misma clave
    assert c.get("usgs/all_day:geojson") == b"data"
