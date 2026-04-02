# MusicArch

MusicArch 是一个用于本地音乐库整理的自动化工具，面向以下典型场景：

- 文件命名混乱（轨道号前缀、非法字符、空格杂乱）
- 标签信息缺失或不一致（标题、歌手、专辑）
- 本地歌词缺失，且需要批量补齐
- 大型音乐目录处理时，希望可中断、可恢复、可人工复核

项目以模块化方式实现扫描、匹配、应用变更和断点恢复，并提供 PyQt6 图形界面。

## 目录

- 项目能力概览
- 快速开始
- GUI 使用流程
- 核心模块说明
- 数据结构与状态字段
- 断点文件格式
- 脚本与命令速查
- 常见问题与排障
- 开发与测试
- 贡献指南
- English Summary

## 项目能力概览

当前版本支持以下能力：

1. 文件名标准化与安全重命名
2. 歌词读取与嵌入（MP3 / FLAC / M4A）
3. 云端元数据匹配与异常识别
4. 大目录并发扫描与 GUI 可视化操作
5. 检查点保存与恢复（JSONL）

## 快速开始

### 1. 环境准备

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=src
```

说明：

- 本项目源码位于 src 目录。
- 若未设置 PYTHONPATH=src，直接运行 pytest 或脚本时可能出现 ModuleNotFoundError: No module named musicarch。
- macOS/Linux 可把 export 命令写入 shell 配置文件实现持久化。

### 2. 快速验证

```bash
PYTHONPATH=src pytest -q
PYTHONPATH=src python scripts/phase1_smoke_test.py
```

phase1_smoke_test.py 会展示：

- 文件名清洗示例
- 歌词嵌入入口示例

### 3. 启动 GUI

```bash
PYTHONPATH=src python scripts/run_gui.py
```

## GUI 使用流程

推荐流程如下：

1. 选择音乐目录
2. 扫描文件，生成待处理记录
3. 云端匹配，得到 matched 或 anomaly 或 not_found
4. 人工查看异常项
5. 写入元数据（可单独执行）
6. 应用重命名（可单独执行）
7. 写入歌词（可单独执行）
8. 保存检查点，支持后续继续处理

批处理建议：

- 默认按批次执行（常见为每批 200 条）
- 每步执行后先抽样检查结果，再继续下一批

## 核心模块说明

### core_engine

职责：

- 文件名清洗与规范化
- 音频格式分发（MP3、FLAC、M4A）
- 标签写入（title、artist、album）
- 歌词嵌入（本地 LRC 或外部歌词文本）

关键行为：

- 去除轨道号前缀（例如 01、Track 07）
- 处理非法文件名字符与控制字符
- 超长文件名截断并尽量保留词边界

### library_scanner

职责：

- 递归扫描音频文件
- 并发读取基础元数据
- 构建 TrackScanRecord 列表

输出字段包括：

- 原路径、相对路径、原文件名、新文件名
- 是否存在同名 lrc
- 解析到的 title、artist、album、duration
- 初始状态与异常信息

### api_matcher

职责：

- 对接云端搜索客户端
- 计算相似度与置信度
- 决策匹配结果

内置策略：

- 标题相似度权重 0.5
- 歌手相似度权重 0.3
- 时长得分权重 0.2
- 支持网络重试和退避
- 将低置信度或时长偏差过大的结果标为 anomaly

### workflow

职责：

- 串联匹配结果与落地变更
- 分步执行元数据写入、重命名、歌词写入
- 提供 preflight 检查与错误分类

典型状态：

- pending
- success
- anomaly
- cancelled

### checkpoint_store

职责：

- 以 JSONL 保存 metadata 与 records
- 支持后续恢复继续执行
- 使用临时文件再替换，降低写入中断风险

### gui_app / view_state

职责：

- GUI 页面与任务调度
- 列表过滤、排序、分页
- 长任务在后台线程执行，避免主线程卡死

## 数据结构与状态字段

扫描记录常见字段（简化）：

- audio_path: 音频绝对路径
- relative_path: 相对扫描根目录路径
- old_file_name: 原文件名
- new_file_name: 目标文件名
- rename_needed: 是否需要重命名
- has_lrc: 是否存在同名 lrc
- lrc_path: lrc 文件路径
- status: pending 或 success 或 anomaly 或 cancelled
- cloud_match_result: 云匹配文本描述
- title 或 artist 或 album: 解析或匹配后的元数据
- error: 异常信息
- error_code: 异常分类
- retryable: 是否建议重试

## 断点文件格式

检查点文件采用 JSONL，第一行为元信息，其余行为记录。

示例：

```json
{"_meta": {"root_dir": "/music", "created_at": "2026-04-02T10:00:00"}}
{"audio_path": "/music/A/a.mp3", "status": "pending"}
{"audio_path": "/music/B/b.flac", "status": "success"}
```

恢复时会读取 metadata 与 records，供 GUI 或脚本继续处理。

## 脚本与命令速查

### 图形界面

```bash
PYTHONPATH=src python scripts/run_gui.py
```

### 阶段冒烟测试

```bash
PYTHONPATH=src python scripts/phase1_smoke_test.py
```

### 检查点恢复脚本

```bash
PYTHONPATH=src python scripts/restore_from_checkpoint.py --help
```

### 对账脚本

```bash
PYTHONPATH=src python scripts/reconcile_audio_lrc_by_longer_name.py --help
```

### 单元测试

```bash
PYTHONPATH=src pytest -q
```

## 常见问题与排障

### 1) 报错 ModuleNotFoundError: No module named musicarch

原因：未设置 PYTHONPATH=src。

解决：

```bash
export PYTHONPATH=src
```

或在命令前临时设置：

```bash
PYTHONPATH=src pytest -q
```

### 2) 云端匹配经常失败或超时

可能原因：网络环境、接口限流、目标平台临时不可用。

建议：

- 降低并发或减小批次
- 稍后重试 anomaly 或 not_found 项
- 先执行本地可完成步骤（重命名、元数据）

### 3) 处理大目录时中断

建议：

- 每批执行后保存检查点
- 重启后从检查点恢复
- 保留处理日志便于定位问题

### 4) 担心批量操作误改文件

强烈建议：

- 先备份音乐目录
- 先在小目录演练
- 先扫一批、看结果、再继续扩大范围

## 开发与测试

### 依赖

- mutagen: 音频标签读写
- httpx: 网络请求
- PyQt6: 图形界面
- pytest: 测试

### 目录结构

```text
src/musicarch/
	api_matcher.py
	checkpoint_store.py
	core_engine.py
	gui_app.py
	library_scanner.py
	view_state.py
	workflow.py

scripts/
	phase1_smoke_test.py
	reconcile_audio_lrc_by_longer_name.py
	restore_from_checkpoint.py
	run_gui.py

tests/
	test_api_matcher.py
	test_checkpoint_store.py
	test_core_engine.py
	test_library_scanner.py
	test_view_state.py
	test_workflow.py
```

### 开发建议流程

1. 先补测试，再改实现
2. 保持单次改动聚焦一个问题
3. 处理批量文件前先做小样本验证
4. 提交前运行完整测试

## 贡献指南

欢迎 Issue 与 PR。

提交 Issue 时建议提供：

- 操作系统与 Python 版本
- 最小复现步骤
- 期望结果与实际结果
- 错误日志或堆栈
- 脱敏后的样例文件名或目录

提交 PR 建议流程：

1. Fork 仓库并创建分支
2. 编写或更新测试
3. 使用清晰提交信息
4. 在 PR 描述中说明动机、影响范围、回归风险

---

如果这个项目对你有帮助，欢迎 Star 和反馈。

## English Summary

MusicArch is a local music library organizer with modular processing:

- filename normalization and safe rename
- metadata writing for MP3 or FLAC or M4A
- cloud matching and anomaly detection
- lyric embedding from local lrc or online source
- checkpoint save and restore in JSONL
- GUI workflow for scan, review, and apply

Quick start:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=src pytest -q
PYTHONPATH=src python scripts/run_gui.py
```

Note: because source files are under src, set PYTHONPATH=src before running tests or scripts.
