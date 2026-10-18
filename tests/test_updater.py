"""Tests puros del updater L1 (sin red real)."""

from __future__ import annotations

import hashlib
import io

import pytest

from shakevision.services import updater


def test_parse_version_and_newer() -> None:
    assert updater.parse_version("v0.8.4.0") == (0, 8, 4, 0)
    assert updater.parse_version("0.8.3") == (0, 8, 3, 0)
    assert updater.is_newer("0.8.4.0", "0.8.3.0")
    assert not updater.is_newer("0.8.3.0", "0.8.3.0")
    assert not updater.is_newer("0.8.2.9", "0.8.3.0")


def test_parse_checksums() -> None:
    h = "a" * 64
    parsed = updater.parse_checksums(f"{h}  file.dmg\n{h}  *other.zip\nbad\n")
    assert parsed["file.dmg"] == h
    assert parsed["other.zip"] == h
    assert "bad" not in parsed


def test_platform_asset(monkeypatch) -> None:
    info = updater.UpdateInfo(
        version="1.0", tag="v1.0", notes="", html_url="",
        assets=(
            {"name": "x-windows-x64.zip", "browser_download_url": "w"},
            {"name": "x-macos-arm64.dmg", "browser_download_url": "m"},
            {"name": "x-linux-x64.AppImage", "browser_download_url": "l"},
        ),
    )
    monkeypatch.setattr(updater.sys, "platform", "linux")
    assert updater.asset_for_platform(info)["name"].endswith(".AppImage")
    monkeypatch.setattr(updater.sys, "platform", "darwin")
    monkeypatch.setattr(updater.platform, "machine", lambda: "arm64")
    assert updater.asset_for_platform(info)["name"].endswith(".dmg")


class _FakeResponse:
    def __init__(self, data: bytes) -> None:
        self._buf = io.BytesIO(data)
        self.headers = {"Content-Length": str(len(data))}

    def read(self, n: int = -1) -> bytes:
        return self._buf.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_download_and_verify(tmp_path, monkeypatch) -> None:
    payload = b"mini seed" * 1000
    digest = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(
        updater.urllib.request, "urlopen",
        lambda *a, **k: _FakeResponse(payload))
    dest = tmp_path / "download.zip"
    updater.download_and_verify("https://example/x", dest, digest)
    assert dest.read_bytes() == payload
    assert not (tmp_path / "download.zip.part").exists()


def test_download_rejects_bad_hash(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        updater.urllib.request, "urlopen",
        lambda *a, **k: _FakeResponse(b"tampered"))
    dest = tmp_path / "bad.zip"
    with pytest.raises(updater.UpdateError):
        updater.download_and_verify("https://example/x", dest, "0" * 64)
    assert not dest.exists()
    assert not (tmp_path / "bad.zip.part").exists()
