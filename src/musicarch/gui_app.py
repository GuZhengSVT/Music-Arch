from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .api_matcher import MetadataMatcher, NetEaseSearchClient, QQMusicSearchClient
from .core_engine import MusicArchEngine
from .library_scanner import MusicLibraryScanner
from .workflow import MusicArchWorkflow


class ScanWorker(QObject):
    finished = pyqtSignal(list)
    progress = pyqtSignal(int, str)
    error = pyqtSignal(str)

    def __init__(self, scanner: MusicLibraryScanner, root_dir: str):
        super().__init__()
        self.scanner = scanner
        self.root_dir = root_dir

    def run(self) -> None:
        try:
            records = self.scanner.scan_as_dicts(Path(self.root_dir), progress_callback=self._on_progress)
            self.finished.emit(records)
        except Exception as exc:
            self.error.emit(str(exc))

    def _on_progress(self, current: int, total: int, message: str) -> None:
        percent = int((current / total) * 100) if total else 0
        self.progress.emit(percent, message)


class MatchWorker(QObject):
    finished = pyqtSignal(list)
    progress = pyqtSignal(int, str)
    error = pyqtSignal(str)

    def __init__(self, workflow: MusicArchWorkflow, records: list[dict]):
        super().__init__()
        self.workflow = workflow
        self.records = records

    def run(self) -> None:
        try:
            updated = self.workflow.match_records(self.records, progress_callback=self._on_progress)
            self.finished.emit(updated)
        except Exception as exc:
            self.error.emit(str(exc))

    def _on_progress(self, current: int, total: int, message: str) -> None:
        percent = int((current / total) * 100) if total else 0
        self.progress.emit(percent, message)


class ApplyWorker(QObject):
    finished = pyqtSignal(list)
    progress = pyqtSignal(int, str)
    error = pyqtSignal(str)

    def __init__(self, workflow: MusicArchWorkflow, records: list[dict]):
        super().__init__()
        self.workflow = workflow
        self.records = records

    def run(self) -> None:
        try:
            updated = self.workflow.apply_changes(self.records, progress_callback=self._on_progress)
            self.finished.emit(updated)
        except Exception as exc:
            self.error.emit(str(exc))

    def _on_progress(self, current: int, total: int, message: str) -> None:
        percent = int((current / total) * 100) if total else 0
        self.progress.emit(percent, message)


class MusicArchMainWindow(QMainWindow):
    COLUMNS = ["旧文件名", "新文件名", "状态", "云端匹配结果"]

    def __init__(self):
        super().__init__()
        self.setWindowTitle("MusicArch")
        self.resize(1200, 760)

        self.engine = MusicArchEngine()
        self.scanner = MusicLibraryScanner(engine=self.engine, max_workers=8)
        self.matcher = MetadataMatcher(
            clients=[NetEaseSearchClient(), QQMusicSearchClient()],
            duration_tolerance_seconds=5,
            min_confidence=0.60,
        )
        self.workflow = MusicArchWorkflow(engine=self.engine, matcher=self.matcher)

        self.current_dir: str = ""
        self.records: list[dict] = []

        self._build_ui()

        self.worker_thread: QThread | None = None

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        main_layout = QVBoxLayout(root)

        top_layout = QHBoxLayout()
        self.select_button = QPushButton("选择文件夹")
        self.select_button.clicked.connect(self._on_select_folder)
        self.path_label = QLabel("未选择目录")

        top_layout.addWidget(self.select_button)
        top_layout.addWidget(self.path_label, stretch=1)

        action_layout = QHBoxLayout()
        self.scan_button = QPushButton("开始扫描")
        self.match_button = QPushButton("云端匹配")
        self.apply_button = QPushButton("应用修改")

        self.scan_button.clicked.connect(self._on_start_scan)
        self.match_button.clicked.connect(self._on_start_match)
        self.apply_button.clicked.connect(self._on_start_apply)

        action_layout.addWidget(self.scan_button)
        action_layout.addWidget(self.match_button)
        action_layout.addWidget(self.apply_button)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.horizontalHeader().setStretchLastSection(True)

        self.progress = QProgressBar()
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)

        main_layout.addLayout(top_layout)
        main_layout.addLayout(action_layout)
        main_layout.addWidget(self.table)
        main_layout.addWidget(self.progress)
        main_layout.addWidget(self.log_box)

    def _on_select_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择音乐目录")
        if not folder:
            return
        self.current_dir = folder
        self.path_label.setText(folder)
        self._log(f"已选择目录: {folder}")

    def _on_start_scan(self) -> None:
        if not self.current_dir:
            QMessageBox.warning(self, "提示", "请先选择文件夹")
            return

        worker = ScanWorker(self.scanner, self.current_dir)
        self._start_worker(
            worker=worker,
            start_log="开始扫描目录",
            finish_log="扫描完成",
            on_finished=self._handle_scan_finished,
        )

    def _on_start_match(self) -> None:
        if not self.records:
            QMessageBox.warning(self, "提示", "请先扫描目录")
            return

        worker = MatchWorker(self.workflow, self.records)
        self._start_worker(
            worker=worker,
            start_log="开始云端匹配",
            finish_log="云端匹配完成",
            on_finished=self._handle_match_finished,
        )

    def _on_start_apply(self) -> None:
        if not self.records:
            QMessageBox.warning(self, "提示", "请先扫描目录")
            return

        worker = ApplyWorker(self.workflow, self.records)
        self._start_worker(
            worker=worker,
            start_log="开始应用修改",
            finish_log="应用修改完成",
            on_finished=self._handle_apply_finished,
        )

    def _start_worker(self, worker: QObject, start_log: str, finish_log: str, on_finished) -> None:
        if self.worker_thread and self.worker_thread.isRunning():
            QMessageBox.information(self, "提示", "已有任务正在执行")
            return

        self.progress.setValue(0)
        self._set_actions_enabled(False)
        self._log(start_log)

        thread = QThread(self)
        self.worker_thread = thread
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.progress.connect(self._on_worker_progress)
        worker.error.connect(self._on_worker_error)
        worker.finished.connect(on_finished)
        worker.finished.connect(lambda _payload: self._on_worker_done(finish_log))

        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        thread.start()

    def _handle_scan_finished(self, records: list[dict]) -> None:
        self.records = records
        self._refresh_table()
        self._log(f"扫描结果数量: {len(records)}")

    def _handle_match_finished(self, records: list[dict]) -> None:
        self.records = records
        self._refresh_table()

    def _handle_apply_finished(self, records: list[dict]) -> None:
        self.records = records
        self._refresh_table()

    def _on_worker_progress(self, value: int, message: str) -> None:
        self.progress.setValue(value)
        self._log(message)

    def _on_worker_error(self, message: str) -> None:
        self._log(f"错误: {message}")
        QMessageBox.critical(self, "任务失败", message)
        self._set_actions_enabled(True)

    def _on_worker_done(self, finish_log: str) -> None:
        self.progress.setValue(100)
        self._set_actions_enabled(True)
        self._log(finish_log)

    def _set_actions_enabled(self, enabled: bool) -> None:
        self.select_button.setEnabled(enabled)
        self.scan_button.setEnabled(enabled)
        self.match_button.setEnabled(enabled)
        self.apply_button.setEnabled(enabled)

    def _refresh_table(self) -> None:
        self.table.setRowCount(len(self.records))

        for row, record in enumerate(self.records):
            values = [
                str(record.get("old_file_name", "")),
                str(record.get("new_file_name", "")),
                str(record.get("status", "")),
                str(record.get("cloud_match_result", "")),
            ]

            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                self.table.setItem(row, col, item)

            status = str(record.get("status", ""))
            if status == "anomaly":
                self._paint_row(row, QColor(255, 227, 227))
            elif status == "success":
                self._paint_row(row, QColor(232, 255, 232))

    def _paint_row(self, row: int, color: QColor) -> None:
        for col in range(self.table.columnCount()):
            item = self.table.item(row, col)
            if item:
                item.setBackground(color)

    def _log(self, message: str) -> None:
        self.log_box.append(message)


def run_gui() -> int:
    app = QApplication(sys.argv)
    window = MusicArchMainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run_gui())
