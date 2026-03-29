from __future__ import annotations

import csv
from copy import deepcopy
import sys
from pathlib import Path

from PyQt6.QtCore import QObject, QPoint, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
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
from .view_state import RecordViewState
from .workflow import MusicArchWorkflow


class ScanWorker(QObject):
    batch_ready = pyqtSignal(list)
    finished = pyqtSignal(list)
    progress = pyqtSignal(int, str)
    error = pyqtSignal(str)

    def __init__(self, scanner: MusicLibraryScanner, root_dir: str):
        super().__init__()
        self.scanner = scanner
        self.root_dir = root_dir
        self._stop_requested = False

    def run(self) -> None:
        try:
            records = self.scanner.scan_stream_as_dicts(
                Path(self.root_dir),
                batch_callback=self._on_batch,
                progress_callback=self._on_progress,
                should_stop=self._should_stop,
                batch_size=200,
            )
            self.finished.emit(records)
        except Exception as exc:
            self.error.emit(str(exc))

    def request_stop(self) -> None:
        self._stop_requested = True

    def _should_stop(self) -> bool:
        return self._stop_requested

    def _on_batch(self, batch: list[dict]) -> None:
        self.batch_ready.emit(batch)

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
        self._stop_requested = False

    def run(self) -> None:
        try:
            updated = self.workflow.match_records(
                self.records,
                progress_callback=self._on_progress,
                should_stop=self._should_stop,
            )
            self.finished.emit(updated)
        except Exception as exc:
            self.error.emit(str(exc))

    def request_stop(self) -> None:
        self._stop_requested = True

    def _should_stop(self) -> bool:
        return self._stop_requested

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
        self._stop_requested = False

    def run(self) -> None:
        try:
            updated = self.workflow.apply_changes(
                self.records,
                progress_callback=self._on_progress,
                should_stop=self._should_stop,
            )
            self.finished.emit(updated)
        except Exception as exc:
            self.error.emit(str(exc))

    def request_stop(self) -> None:
        self._stop_requested = True

    def _should_stop(self) -> bool:
        return self._stop_requested

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
        self.filtered_indices: list[int] = []
        self.page_index = 0
        self.task_cancel_requested = False
        self.current_worker: QObject | None = None
        self.view_state = RecordViewState()
        self.sort_field_map = {
            "旧文件名": "old_file_name",
            "新文件名": "new_file_name",
            "状态": "status",
            "匹配结果": "cloud_match_result",
        }

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
        self.stop_button = QPushButton("停止当前任务")
        self.export_button = QPushButton("导出异常CSV")

        self.scan_button.clicked.connect(self._on_start_scan)
        self.match_button.clicked.connect(self._on_start_match)
        self.apply_button.clicked.connect(self._on_start_apply)
        self.stop_button.clicked.connect(self._on_stop_task)
        self.export_button.clicked.connect(self._on_export_anomaly_csv)

        action_layout.addWidget(self.scan_button)
        action_layout.addWidget(self.match_button)
        action_layout.addWidget(self.apply_button)
        action_layout.addWidget(self.stop_button)
        action_layout.addWidget(self.export_button)

        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("状态筛选"))
        self.status_filter = QComboBox()
        self.status_filter.addItems(["全部", "pending", "success", "anomaly"])
        self.status_filter.currentTextChanged.connect(self._on_filter_changed)

        filter_layout.addWidget(self.status_filter)
        filter_layout.addWidget(QLabel("搜索"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("按旧文件名/新文件名/匹配结果搜索")
        self.search_input.textChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.search_input, stretch=1)

        filter_layout.addWidget(QLabel("排序"))
        self.sort_by = QComboBox()
        self.sort_by.addItems(["旧文件名", "新文件名", "状态", "匹配结果"])
        self.sort_by.currentTextChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.sort_by)

        self.sort_order = QComboBox()
        self.sort_order.addItems(["升序", "降序"])
        self.sort_order.currentTextChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.sort_order)

        filter_layout.addWidget(QLabel("每页"))
        self.page_size = QComboBox()
        self.page_size.addItems(["200", "500", "1000", "全部"])
        self.page_size.currentTextChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.page_size)

        self.prev_page_button = QPushButton("上一页")
        self.next_page_button = QPushButton("下一页")
        self.page_label = QLabel("第 1 / 1 页")
        self.prev_page_button.clicked.connect(self._on_prev_page)
        self.next_page_button.clicked.connect(self._on_next_page)
        filter_layout.addWidget(self.prev_page_button)
        filter_layout.addWidget(self.next_page_button)
        filter_layout.addWidget(self.page_label)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_table_context_menu)

        self.progress = QProgressBar()
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)

        main_layout.addLayout(top_layout)
        main_layout.addLayout(action_layout)
        main_layout.addLayout(filter_layout)
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

        self.records = []
        self.page_index = 0
        self._refresh_table()

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

        payload = deepcopy(self.records)
        skipped = 0
        confirmed = 0
        for record in payload:
            record["skip_apply"] = False
            if str(record.get("status", "")) == "anomaly":
                if bool(record.get("manual_confirmed")):
                    record["status"] = "pending"
                    confirmed += 1
                else:
                    record["skip_apply"] = True
                    skipped += 1

        if skipped == len(payload):
            QMessageBox.information(self, "提示", "全部为未确认异常项，请先右键标记手动确认")
            return

        worker = ApplyWorker(self.workflow, payload)
        self._start_worker(
            worker=worker,
            start_log=f"开始应用修改 (已确认异常: {confirmed}, 跳过未确认异常: {skipped})",
            finish_log="应用修改完成",
            on_finished=self._handle_apply_finished,
        )

    def _start_worker(self, worker: QObject, start_log: str, finish_log: str, on_finished) -> None:
        if self.worker_thread and self.worker_thread.isRunning():
            QMessageBox.information(self, "提示", "已有任务正在执行")
            return

        self.progress.setValue(0)
        self.task_cancel_requested = False
        self._set_actions_enabled(False)
        self.stop_button.setEnabled(True)
        self._log(start_log)

        thread = QThread(self)
        self.worker_thread = thread
        self.current_worker = worker
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.progress.connect(self._on_worker_progress)
        worker.error.connect(self._on_worker_error)
        if isinstance(worker, ScanWorker):
            worker.batch_ready.connect(self._handle_scan_batch)
        worker.finished.connect(on_finished)
        worker.finished.connect(lambda _payload: self._on_worker_done(finish_log))

        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        thread.start()

    def _handle_scan_finished(self, records: list[dict]) -> None:
        # Use final sorted payload returned by scanner for deterministic order.
        for record in records:
            record.setdefault("manual_confirmed", False)
            record.setdefault("skip_apply", False)
        self.records = records
        self.page_index = 0
        self._refresh_table()
        self._log(f"扫描结果数量: {len(records)}")

    def _handle_scan_batch(self, batch: list[dict]) -> None:
        for record in batch:
            record["manual_confirmed"] = False
            record["skip_apply"] = False
            self.records.append(record)

        self._refresh_table()
        self._log(f"扫描中: 已发现 {len(self.records)} 条")

    def _handle_match_finished(self, records: list[dict]) -> None:
        for record in records:
            record.setdefault("manual_confirmed", False)
            record["skip_apply"] = False
        self.records = records
        self.page_index = 0
        self._refresh_table()

    def _handle_apply_finished(self, records: list[dict]) -> None:
        for record in records:
            record["skip_apply"] = False
        self.records = records
        self.page_index = 0
        self._refresh_table()

    def _on_worker_progress(self, value: int, message: str) -> None:
        self.progress.setValue(value)
        self._log(message)

    def _on_worker_error(self, message: str) -> None:
        self._log(f"错误: {message}")
        QMessageBox.critical(self, "任务失败", message)
        self._set_actions_enabled(True)
        self.stop_button.setEnabled(False)

    def _on_worker_done(self, finish_log: str) -> None:
        self.progress.setValue(100)
        self._set_actions_enabled(True)
        self.stop_button.setEnabled(False)
        if self.task_cancel_requested:
            self._log("任务已停止，已保留当前已完成结果")
        else:
            self._log(finish_log)
        self.current_worker = None

    def _set_actions_enabled(self, enabled: bool) -> None:
        self.select_button.setEnabled(enabled)
        self.scan_button.setEnabled(enabled)
        self.match_button.setEnabled(enabled)
        self.apply_button.setEnabled(enabled)
        self.stop_button.setEnabled(False)
        self.export_button.setEnabled(enabled)
        self.status_filter.setEnabled(enabled)
        self.search_input.setEnabled(enabled)
        self.sort_by.setEnabled(enabled)
        self.sort_order.setEnabled(enabled)
        self.page_size.setEnabled(enabled)
        self.prev_page_button.setEnabled(enabled)
        self.next_page_button.setEnabled(enabled)

    def _refresh_table(self) -> None:
        sort_key = self.sort_field_map[self.sort_by.currentText()]
        descending = self.sort_order.currentText() == "降序"
        selected_size = self.page_size.currentText()
        page_size = len(self.records) if selected_size == "全部" else int(selected_size)

        self.view_state.set_records(self.records)
        page = self.view_state.build(
            status_filter=self.status_filter.currentText(),
            keyword=self.search_input.text(),
            sort_key=sort_key,
            descending=descending,
            page_size=page_size,
            page_index=self.page_index,
        )

        self.page_index = page.page_index
        self.filtered_indices = page.indices
        self.table.setRowCount(len(self.filtered_indices))

        for row, record_idx in enumerate(self.filtered_indices):
            record = self.records[record_idx]
            values = [
                str(record.get("old_file_name", "")),
                str(record.get("new_file_name", "")),
                self._status_for_display(record),
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

        self.page_label.setText(f"第 {page.page_index + 1} / {page.total_pages} 页")
        self.prev_page_button.setEnabled(page.page_index > 0)
        self.next_page_button.setEnabled(page.page_index < (page.total_pages - 1))

    def _status_for_display(self, record: dict) -> str:
        status = str(record.get("status", ""))
        if status == "anomaly" and bool(record.get("manual_confirmed")):
            return "anomaly (已确认)"
        return status

    def _on_filter_changed(self, *_args) -> None:
        self.page_index = 0
        self._refresh_table()

    def _on_prev_page(self) -> None:
        if self.page_index > 0:
            self.page_index -= 1
            self._refresh_table()

    def _on_next_page(self) -> None:
        self.page_index += 1
        self._refresh_table()

    def _on_table_context_menu(self, pos: QPoint) -> None:
        row = self.table.rowAt(pos.y())
        if row < 0 or row >= len(self.filtered_indices):
            return

        record_idx = self.filtered_indices[row]
        record = self.records[record_idx]
        if str(record.get("status", "")) != "anomaly":
            return

        menu = QMenu(self)
        if bool(record.get("manual_confirmed")):
            action = menu.addAction("取消手动确认")
        else:
            action = menu.addAction("标记为手动确认")

        selected = menu.exec(self.table.viewport().mapToGlobal(pos))
        if selected == action:
            record["manual_confirmed"] = not bool(record.get("manual_confirmed"))
            if record["manual_confirmed"]:
                self._log(f"已手动确认异常项: {record.get('old_file_name', '')}")
            else:
                self._log(f"已取消手动确认: {record.get('old_file_name', '')}")
            self._refresh_table()

    def _on_export_anomaly_csv(self) -> None:
        anomalies = [item for item in self.records if str(item.get("status", "")) == "anomaly"]
        if not anomalies:
            QMessageBox.information(self, "提示", "当前没有异常项可导出")
            return

        default_name = "musicarch_anomalies.csv"
        target, _ = QFileDialog.getSaveFileName(
            self,
            "导出异常项 CSV",
            str(Path(self.current_dir or ".") / default_name),
            "CSV Files (*.csv)",
        )
        if not target:
            return

        headers = [
            "audio_path",
            "old_file_name",
            "new_file_name",
            "status",
            "manual_confirmed",
            "cloud_match_result",
            "error",
        ]

        with open(target, "w", newline="", encoding="utf-8-sig") as fp:
            writer = csv.DictWriter(fp, fieldnames=headers)
            writer.writeheader()
            for row in anomalies:
                writer.writerow({key: row.get(key, "") for key in headers})

        self._log(f"异常项已导出: {target}")

    def _on_stop_task(self) -> None:
        if not (self.worker_thread and self.worker_thread.isRunning()):
            QMessageBox.information(self, "提示", "当前没有进行中的任务")
            return

        self.task_cancel_requested = True
        if self.current_worker and hasattr(self.current_worker, "request_stop"):
            self.current_worker.request_stop()
        self._log("已请求停止当前任务，等待正在执行的批次收尾")

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
