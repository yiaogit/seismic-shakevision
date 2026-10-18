"""Diálogo de actualización L1: notas, descarga y verificación SHA-256."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QStandardPaths, QThread, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QProgressBar,
    QPushButton, QTextBrowser, QVBoxLayout,
)

from shakevision import __version__
from shakevision.i18n import t
from shakevision.services import updater


class _DownloadWorker(QObject):
    progress = Signal(int, int)
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, info: updater.UpdateInfo, asset: dict,
                 dest: Path) -> None:
        super().__init__()
        self._info = info
        self._asset = asset
        self._dest = Path(dest)

    @Slot()
    def run(self) -> None:
        try:
            checks = updater.fetch_checksums(self._info.checksums_url)
            name = str(self._asset.get("name", ""))
            expected = checks.get(name, "")
            if not expected:
                raise updater.UpdateError(t("update.checksums_missing"))
            url = str(self._asset.get("browser_download_url", ""))
            path = updater.download_and_verify(
                url, self._dest, expected,
                progress=lambda cur, total: self.progress.emit(cur, total),
            )
            self.done.emit(str(path))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class UpdateDialog(QDialog):
    """Muestra la release y permite descargar el asset de la plataforma."""

    def __init__(self, info: updater.UpdateInfo, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("update.title"))
        self.setMinimumSize(560, 420)
        self._info = info
        self._asset = updater.asset_for_platform(info)
        self._thread: Optional[QThread] = None
        self._worker: Optional[_DownloadWorker] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(10)

        title = QLabel(t("update.available",
                         version=info.version, current=__version__))
        title.setObjectName("SectionTitle")
        title.setWordWrap(True)
        root.addWidget(title)

        notes_label = QLabel(t("update.notes"))
        notes_label.setObjectName("Caption")
        root.addWidget(notes_label)
        notes = QTextBrowser()
        notes.setOpenExternalLinks(True)
        try:
            notes.setMarkdown(info.notes or "—")
        except Exception:  # noqa: BLE001
            notes.setPlainText(info.notes or "—")
        root.addWidget(notes, stretch=1)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setRange(0, 100)
        root.addWidget(self.progress)
        self.status = QLabel("")
        self.status.setObjectName("Caption")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        row = QHBoxLayout()
        self.release_btn = QPushButton(t("update.release_page"))
        self.release_btn.clicked.connect(self._open_release_page)
        row.addWidget(self.release_btn)
        self.folder_btn = QPushButton(t("update.open_folder"))
        self.folder_btn.setVisible(False)
        self.folder_btn.clicked.connect(self._open_folder)
        row.addWidget(self.folder_btn)
        row.addStretch(1)
        self.download_btn = QPushButton(t("update.download"))
        self.download_btn.setObjectName("PrimaryButton")
        self.download_btn.clicked.connect(self._start_download)
        row.addWidget(self.download_btn)
        self.close_btn = QPushButton(t("update.close"))
        self.close_btn.clicked.connect(self.accept)
        row.addWidget(self.close_btn)
        root.addLayout(row)

        if self._asset is None or not info.checksums_url:
            self.download_btn.setEnabled(False)
            self.status.setText(t("update.no_asset"))
        self._download_dir = Path(
            QStandardPaths.writableLocation(
                QStandardPaths.DownloadLocation) or Path.home())
        self._verified_path: Optional[Path] = None

    def _open_release_page(self) -> None:
        QDesktopServices.openUrl(QUrl(self._info.html_url or updater.RELEASES_PAGE))

    def _start_download(self) -> None:
        if self._asset is None or self._thread is not None:
            return
        name = str(self._asset.get("name", "SeismicGuard-update"))
        suggested = str(self._download_dir / name)
        path, _ = QFileDialog.getSaveFileName(
            self, t("update.download"), suggested,
            "All files (*)")
        if not path:
            return
        self.download_btn.setEnabled(False)
        self.close_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.status.setText(t("update.downloading", name=name))
        self._worker = _DownloadWorker(self._info, self._asset, Path(path))
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.done.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._on_thread_finished)
        self._thread.start()

    @Slot(int, int)
    def _on_progress(self, current: int, total: int) -> None:
        if total > 0:
            self.progress.setRange(0, 100)
            self.progress.setValue(min(100, int(current * 100 / total)))
        else:
            self.progress.setRange(0, 0)

    @Slot(str)
    def _on_done(self, path: str) -> None:
        self._verified_path = Path(path)
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.status.setText(t("update.verified", path=path))
        self.folder_btn.setVisible(True)
        self.close_btn.setEnabled(True)

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        self.progress.setVisible(False)
        self.status.setText(t("update.failed", error=message))
        self.download_btn.setEnabled(True)
        self.close_btn.setEnabled(True)

    @Slot()
    def _on_thread_finished(self) -> None:
        self._thread = None
        self._worker = None
        if self.download_btn.isEnabled() is False and self._verified_path is None:
            self.download_btn.setEnabled(True)

    def _open_folder(self) -> None:
        if self._verified_path is None:
            return
        QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self._verified_path.parent)))

    def reject(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            return  # no cerrar mientras se descarga
        super().reject()
