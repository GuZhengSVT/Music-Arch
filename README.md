# MusicArch

[English Version](#english-version)

MusicArch 是一个面向本地音乐库的自动化整理工具，目标是把「大体量、命名混乱、歌词缺失、元数据不一致」的音乐目录整理为可维护的结构。

项目当前包含完整的四阶段能力：

- 文件名标准化与安全重命名
- 歌词读取与嵌入 (MP3 / FLAC / M4A)
- 云端元数据匹配与异常识别
- 大目录并发扫描 + GUI 可视化操作流

## 1. 项目简介

MusicArch 主要解决以下问题：

- 音乐文件名混杂轨道号、非法字符、冗余空格
- 本地标签不完整，难以与云端信息核对
- 单次处理目录较大时，传统脚本容易阻塞、失败后难恢复

围绕这些问题，项目采用模块化设计：

- `core_engine`: 文件名清洗、歌词嵌入、音频格式分发
- `library_scanner`: 多线程扫描本地音频并构建结构化记录
- `api_matcher`: 云端搜索客户端 + 相似度评分 + 匹配决策
- `workflow`: 扫描结果匹配并落地重命名/异常标记
- `checkpoint_store`: JSONL 断点存档与恢复
- `gui_app` / `view_state`: PyQt6 图形界面与列表过滤分页状态管理

## 2. 功能及使用方法

### 2.1 环境准备

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=src
```

依赖见 `requirements.txt`：

- `mutagen`: 音频标签读写
- `httpx`: 云端 API 请求
- `PyQt6`: GUI
- `pytest`: 测试

### 2.2 一键快速验证

```bash
pytest -q
python scripts/phase1_smoke_test.py
```

`phase1_smoke_test.py` 会演示：

- 文件名规范化效果
- 歌词嵌入调用入口

### 2.3 启动 GUI (推荐使用方式)

```bash
python scripts/run_gui.py
```

GUI 典型流程：

1. 选择音乐目录
2. 点击扫描，生成待处理记录
3. 点击云端匹配，获取 `matched/anomaly/not_found` 判断
4. 人工确认异常项 (必要时)
5. 点击应用更改，执行重命名与歌词嵌入

### 2.4 核心功能说明

#### A. 文件名清洗与重命名

- 去除常见轨道号前缀，如 `01 - `、`Track 07 `
- 替换非法文件名字符，如 `\\ / : * ? " < > |`
- 去除控制字符与多余空白
- 超长文件名按安全长度截断，尽量保持词边界
- 冲突时自动回退到安全命名 (如追加 `(1)`)

#### B. 歌词嵌入

- 自动寻找同名 `.lrc` 侧车歌词文件
- MP3: 写入 ID3 `USLT`
- FLAC: 写入 `LYRICS`
- M4A: 写入 `©lyr`
- `.lrc` 文件默认保留，仅在重命名时与音频同步改名

#### C. 云端匹配与异常判断

- 基于标题/艺术家相似度 + 时长差进行综合评分
- 支持重试与退避，降低网络波动影响
- 对低置信度/时长偏差过大记录标记异常，便于人工复核

#### D. 大库处理能力

- 并发扫描，适配大目录
- GUI 通过 `QThread` 执行任务，避免界面卡死
- 支持过滤、搜索、排序、分页
- 支持任务中断、检查点保存与恢复

### 2.5 作为 Python 库调用 (示例)

```python
from pathlib import Path

from musicarch import MusicLibraryScanner
from musicarch.api_matcher import LocalTrackInfo, MetadataMatcher, NetEaseSearchClient

scanner = MusicLibraryScanner(max_workers=8)
records = scanner.scan(Path("/path/to/music"))
print(f"scanned: {len(records)}")

matcher = MetadataMatcher(clients=[NetEaseSearchClient()])
decision = matcher.match(LocalTrackInfo(title="晴天", artist="周杰伦", duration_seconds=269))
print(decision.status, decision.confidence, decision.reason)
```

## 3. 注意事项及欢迎提 Issue

### 使用注意事项

- 建议先对音乐目录做一次备份，再执行批量应用。
- 网络 API 受目标平台可用性、频率限制和地区网络状态影响。
- 匹配结果存在统计误差，`anomaly` 项建议人工确认后再应用。
- 文件系统兼容性存在平台差异，Windows/macOS/Linux 对非法字符和路径长度限制不同。
- 本项目不会主动删除 `.lrc` 文件；默认策略是保留并与音频同步命名。

### Issue 反馈建议

欢迎提交 Issue，推荐附带以下信息，便于快速定位：

- 操作系统与 Python 版本
- 复现步骤 (尽量最小化)
- 期望结果与实际结果
- 报错日志 / 堆栈信息 / 截图
- 脱敏后的示例文件名或目录结构

可在仓库的 Issues 页面提交问题与建议，也欢迎功能请求和体验反馈。

## 4. 贡献者

本项目由本人（GuZhengSVT）在Gemini-3.1-pro与ChatGPT-5.3-Codex辅助下完成，全程Vibe Coding没有写过一行代码：）  
所以任何人可以随便使用。

如果你希望参与开发，欢迎提交 PR：

1. Fork 并创建分支
2. 编写或更新测试
3. 提交清晰的 Commit 信息
4. 发起 Pull Request 并描述变更动机与影响范围

---

如果这个项目对你有帮助，欢迎 Star 与 Issue 交流。

## English Version

MusicArch is an automation tool for organizing local music libraries. Its goal is to turn large, messy, lyric-missing, and metadata-inconsistent music folders into a maintainable structure.

The project currently includes a complete four-phase capability set:

- Filename normalization and safe renaming
- Lyric parsing and embedding (MP3 / FLAC / M4A)
- Cloud metadata matching and anomaly detection
- Concurrent large-folder scanning with a GUI-based workflow

## 1. Project Overview

MusicArch mainly solves these issues:

- Filenames mixed with track prefixes, illegal characters, and redundant spaces
- Incomplete local tags that are hard to verify against cloud metadata
- Traditional scripts blocking or failing without recovery on large directories

To address these challenges, the project uses a modular design:

- `core_engine`: filename cleaning, lyric embedding, and audio format dispatching
- `library_scanner`: multi-threaded local audio scan and structured record building
- `api_matcher`: cloud search clients, similarity scoring, and match decision logic
- `workflow`: apply matching results and perform rename/anomaly marking
- `checkpoint_store`: JSONL checkpoint save and restore
- `gui_app` / `view_state`: PyQt6 GUI and list filter/pagination state management

## 2. Features and Usage

### 2.1 Environment Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=src
```

Dependencies are listed in `requirements.txt`:

- `mutagen`: audio tag read/write
- `httpx`: cloud API requests
- `PyQt6`: GUI
- `pytest`: testing

### 2.2 Quick Validation

```bash
pytest -q
python scripts/phase1_smoke_test.py
```

`phase1_smoke_test.py` demonstrates:

- filename normalization behavior
- lyric embedding entry points

### 2.3 Launch GUI (Recommended)

```bash
python scripts/run_gui.py
```

Typical GUI workflow:

1. Select your music folder.
2. Click scan to build processing records.
3. Click cloud match to get `matched/anomaly/not_found` decisions.
4. Manually review anomaly items when needed.
5. Click apply changes to execute renaming and lyric embedding.

### 2.4 Core Features

#### A. Filename Cleaning and Renaming

- Removes common track prefixes, such as `01 - ` and `Track 07 `
- Replaces illegal filename characters, such as `\\ / : * ? " < > |`
- Removes control characters and redundant spaces
- Truncates overly long filenames safely while preserving word boundaries when possible
- Uses safe fallback naming on conflicts (for example appending `(1)`)

#### B. Lyric Embedding

- Automatically detects sidecar `.lrc` lyric files
- MP3: writes ID3 `USLT`
- FLAC: writes `LYRICS`
- M4A: writes `©lyr`
- `.lrc` files are preserved by default and renamed together with audio files when needed

#### C. Cloud Matching and Anomaly Detection

- Uses title/artist similarity plus duration difference for composite scoring
- Supports retry and backoff to reduce impact from network instability
- Marks low-confidence or high-duration-difference records as anomalies for manual review

#### D. Large Library Processing

- Concurrent scanning for large folders
- Uses `QThread` in GUI to avoid UI freezing
- Supports filtering, searching, sorting, and pagination
- Supports task interruption, checkpoint save, and restore

### 2.5 Use as a Python Library (Example)

```python
from pathlib import Path

from musicarch import MusicLibraryScanner
from musicarch.api_matcher import LocalTrackInfo, MetadataMatcher, NetEaseSearchClient

scanner = MusicLibraryScanner(max_workers=8)
records = scanner.scan(Path("/path/to/music"))
print(f"scanned: {len(records)}")

matcher = MetadataMatcher(clients=[NetEaseSearchClient()])
decision = matcher.match(LocalTrackInfo(title="Qing Tian", artist="Jay Chou", duration_seconds=269))
print(decision.status, decision.confidence, decision.reason)
```

## 3. Notes and Welcome to Open Issues

### Usage Notes

- It is recommended to back up your music directory before batch applying changes.
- Cloud APIs may be affected by service availability, rate limits, and regional network conditions.
- Matching results are probabilistic; anomaly items should be reviewed manually before applying.
- Filesystem constraints differ across platforms. Windows/macOS/Linux have different limits on illegal characters and path length.
- This project does not proactively delete `.lrc` files; by default they are preserved and renamed together with the audio files.

### Issue Reporting Guidelines

Issues are welcome. To help troubleshooting, please include:

- OS and Python version
- Reproduction steps (preferably minimal)
- Expected behavior vs actual behavior
- Error logs / stack traces / screenshots
- Sanitized sample filenames or directory structures

You can submit issues and suggestions on the repository Issues page. Feature requests and UX feedback are also welcome.

## 4. Contributors

This project was completed by me (GuZhengSVT) with assistance from Gemini-3.1-pro and ChatGPT-5.3-Codex, using a full vibe-coding workflow without writing code manually :)
So anyone is free to use it.

If you would like to contribute, feel free to open a PR:

1. Fork and create a branch.
2. Add or update tests.
3. Write clear commit messages.
4. Open a Pull Request and describe motivation and impact.

---

If this project helps you, a Star and an Issue are always appreciated.
