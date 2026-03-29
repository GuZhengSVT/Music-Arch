# MusicArch

Phase 1 implementation of MusicArch core engine (non-GUI):

- Filename normalization (remove track prefix)
- Invalid filename character replacement and truncation
- Lyrics embedding with Mutagen for MP3/FLAC/M4A

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
