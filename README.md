# MusicArch

Phase 1, Phase 2, Phase 3 and Phase 4 implementation of MusicArch:

- Filename normalization (remove track prefix)
- Invalid filename character replacement and truncation
- Lyrics embedding with Mutagen for MP3/FLAC/M4A
- Cloud metadata matching (NetEase/QQMusic/Spotify adapters + confidence scoring)
- Large-folder scanning with concurrent traversal and table-ready data model
- PyQt6 GUI with QThread workers (scan -> cloud match -> apply changes)

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=src
pytest -q
python scripts/phase1_smoke_test.py
python scripts/run_gui.py
```

## Notes

- MP3 uses ID3 `USLT` frame for lyrics.
- FLAC uses Vorbis Comment `LYRICS`.
- M4A uses MP4 `©lyr` atom.
- Sidecar `.lrc` files are kept and never deleted.

## Phase 2 quick usage

```python
from musicarch.api_matcher import LocalTrackInfo, MetadataMatcher, NetEaseSearchClient

matcher = MetadataMatcher(clients=[NetEaseSearchClient()])
local = LocalTrackInfo(title="晴天", artist="周杰伦", duration_seconds=269)
decision = matcher.match(local)
print(decision.status, decision.confidence, decision.reason)
```

## Phase 3 quick usage

```python
from pathlib import Path

from musicarch.library_scanner import MusicLibraryScanner

scanner = MusicLibraryScanner(max_workers=8)
records = scanner.scan(Path("/path/to/music"))
for record in records[:3]:
	print(record.old_file_name, "->", record.new_file_name, record.status)
```

## Phase 4 GUI

- Top workspace row: folder selector + current path
- Table columns: old file name, new file name, status, cloud match result
- Action buttons: start scan, cloud match, apply changes
- Bottom area: progress bar + realtime logs
- Status filter + keyword search for table rows
- Right-click anomaly rows to mark manual confirmation before apply
- Export anomaly rows to CSV for offline review
- Sort controls (old/new name, status, match result)
- Pagination controls (200/500/1000/all) for large libraries
- Incremental scan rendering (results appear while scanning)
- Stop-current-task support for scan/match/apply (keeps partial results)
- JSONL checkpoint save/load for resume workflows
- Retry queue: re-run apply only for anomaly rows

Notes:

- GUI tasks run in QThread worker objects to avoid UI freeze on large folders.
- `apply changes` keeps sidecar `.lrc` files and only renames them with audio files.
