# MusicArch

Phase 1, Phase 2 and Phase 3 implementation of MusicArch core engine (non-GUI):

- Filename normalization (remove track prefix)
- Invalid filename character replacement and truncation
- Lyrics embedding with Mutagen for MP3/FLAC/M4A
- Cloud metadata matching (NetEase/QQMusic/Spotify adapters + confidence scoring)
- Large-folder scanning with concurrent traversal and table-ready data model

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=src
pytest -q
python scripts/phase1_smoke_test.py
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
