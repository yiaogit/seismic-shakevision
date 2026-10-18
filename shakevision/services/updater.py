"""Actualizaciones L1 — manifest GitHub, descarga y verificación SHA-256.

No instala nada automáticamente: consulta la última release, avisa al
usuario, descarga el asset de su plataforma y verifica el checksum. La
instalación silenciosa, firma y rollback quedan para L2.
"""

from __future__ import annotations

import hashlib
import json
import platform
import re
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

GITHUB_REPO = "yiaogit/seismic-shakevision"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases/latest"
USER_AGENT = "SeismicGuard-Updater/1"
TIMEOUT_S = 10.0
_CHUNK = 256 * 1024


class UpdateError(RuntimeError):
    """Error de red, manifest o verificación."""


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    tag: str
    notes: str
    html_url: str
    assets: tuple[dict, ...]
    checksums_url: str = ""


def parse_version(text: str) -> tuple[int, ...]:
    """0.8.3.0 / v0.8.3.0 / 0.8.3-rc1 → tupla comparable."""

    nums = re.findall(r"\d+", str(text or ""))
    vals = tuple(int(n) for n in nums[:4])
    return vals + (0,) * (4 - len(vals))


def is_newer(latest: str, current: str) -> bool:
    return parse_version(latest) > parse_version(current)


def _platform_asset(assets: list[dict]) -> Optional[dict]:
    system = sys.platform
    machine = platform.machine().lower()
    if system == "darwin":
        suffix = ".dmg"
        arch = "arm64" if machine in ("arm64", "aarch64") else "x64"
    elif system.startswith("win"):
        suffix = ".zip"
        arch = "x64"
    elif system.startswith("linux"):
        suffix = ".AppImage"
        arch = "x64"
    else:
        return None
    candidates = [
        a for a in assets
        if str(a.get("name", "")).endswith(suffix)
    ]
    if not candidates:
        return None
    for a in candidates:
        name = str(a.get("name", "")).lower()
        if arch in name:
            return a
    return candidates[0]


def _checksums_url(assets: list[dict]) -> str:
    for a in assets:
        name = str(a.get("name", "")).lower()
        if name == "sha256sums.txt" or name.endswith("-checksums.txt"):
            return str(a.get("browser_download_url", ""))
    return ""


def _http_json(url: str, timeout: float = TIMEOUT_S) -> dict:
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github+json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise UpdateError(str(exc)) from exc


def check_for_update(current_version: str,
                     timeout: float = TIMEOUT_S) -> Optional[UpdateInfo]:
    """Devuelve ``UpdateInfo`` si hay una versión más nueva; si no, None."""

    data = _http_json(RELEASES_API, timeout=timeout)
    tag = str(data.get("tag_name", "")).strip()
    version = tag[1:] if tag.lower().startswith("v") else tag
    if not version or not is_newer(version, current_version):
        return None
    assets_raw = data.get("assets") or []
    assets = [
        {
            "name": str(a.get("name", "")),
            "browser_download_url": str(a.get("browser_download_url", "")),
            "size": int(a.get("size", 0) or 0),
        }
        for a in assets_raw if isinstance(a, dict)
    ]
    return UpdateInfo(
        version=version, tag=tag,
        notes=str(data.get("body", "") or ""),
        html_url=str(data.get("html_url", RELEASES_PAGE)),
        assets=tuple(assets),
        checksums_url=_checksums_url(assets),
    )


def asset_for_platform(info: UpdateInfo) -> Optional[dict]:
    return _platform_asset(list(info.assets))


def parse_checksums(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in str(text or "").splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        digest, name = parts[0].strip().lower(), parts[-1].lstrip("*").strip()
        if re.fullmatch(r"[0-9a-f]{64}", digest) and name:
            out[name] = digest
    return out


def fetch_checksums(url: str, timeout: float = TIMEOUT_S) -> dict[str, str]:
    if not url:
        raise UpdateError("No SHA256SUMS asset")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return parse_checksums(resp.read().decode("utf-8", "replace"))
    except Exception as exc:  # noqa: BLE001
        raise UpdateError(str(exc)) from exc


def download_and_verify(
    url: str, dest: Path, expected_sha256: str,
    progress: Optional[Callable[[int, int], None]] = None,
    timeout: float = 30.0,
) -> Path:
    """Descarga a ``dest.part``, verifica SHA-256 y renombra a ``dest``."""

    expected = str(expected_sha256 or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise UpdateError("Missing or invalid SHA-256")
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    h = hashlib.sha256()
    total = 0
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp, \
                open(tmp, "wb") as fh:
            length = int(resp.headers.get("Content-Length", 0) or 0)
            while True:
                chunk = resp.read(_CHUNK)
                if not chunk:
                    break
                fh.write(chunk)
                h.update(chunk)
                total += len(chunk)
                if progress is not None:
                    progress(total, length)
        actual = h.hexdigest()
        if actual != expected:
            raise UpdateError(
                f"SHA-256 mismatch: {actual[:12]}… != {expected[:12]}…")
        tmp.replace(dest)
        return dest
    except UpdateError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    except Exception as exc:  # noqa: BLE001
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise UpdateError(str(exc)) from exc
