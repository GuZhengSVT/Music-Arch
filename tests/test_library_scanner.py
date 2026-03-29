from pathlib import Path

from musicarch.library_scanner import MusicLibraryScanner


def test_scan_collects_audio_and_builds_rename_preview(tmp_path: Path):
    artist_dir = tmp_path / "Artist" / "Album"
    artist_dir.mkdir(parents=True)

    audio_path = artist_dir / "01 - My:Song?.mp3"
    lrc_path = artist_dir / "01 - My:Song?.lrc"
    audio_path.write_bytes(b"fake-mp3")
    lrc_path.write_text("[00:01.00]hello", encoding="utf-8")

    scanner = MusicLibraryScanner(max_workers=2)
    scanner._read_basic_metadata = lambda _: {
        "title": "My Song",
        "artist": "Artist",
        "album": "Album",
        "duration_seconds": 180.0,
    }

    records = scanner.scan(tmp_path)

    assert len(records) == 1
    record = records[0]
    assert record.old_file_name == "01 - My:Song?.mp3"
    assert record.new_file_name == "My-Song-.mp3"
    assert record.rename_needed is True
    assert record.has_lrc is True
    assert record.lrc_new_file_name == "My-Song-.lrc"
    assert record.status == "pending"
    assert record.cloud_match_result == "待匹配"
    assert record.duration_seconds == 180.0


def test_scan_ignores_non_audio_files(tmp_path: Path):
    (tmp_path / "note.txt").write_text("x", encoding="utf-8")
    (tmp_path / "cover.jpg").write_bytes(b"img")

    scanner = MusicLibraryScanner()
    records = scanner.scan(tmp_path)

    assert records == []


def test_scan_marks_anomaly_on_metadata_error(tmp_path: Path):
    audio_path = tmp_path / "Track 03 Demo.flac"
    audio_path.write_bytes(b"fake-flac")

    scanner = MusicLibraryScanner(max_workers=1)

    def _raise(_: Path):
        raise RuntimeError("metadata read failed")

    scanner._read_basic_metadata = _raise

    records = scanner.scan(tmp_path)
    assert len(records) == 1
    record = records[0]
    assert record.status == "anomaly"
    assert "metadata read failed" in (record.error or "")


def test_scan_as_dicts_returns_serializable_payload(tmp_path: Path):
    audio_path = tmp_path / "Song.m4a"
    audio_path.write_bytes(b"fake-m4a")

    scanner = MusicLibraryScanner()
    scanner._read_basic_metadata = lambda _: {}

    payload = scanner.scan_as_dicts(tmp_path)
    assert isinstance(payload, list)
    assert isinstance(payload[0], dict)
    assert payload[0]["old_file_name"] == "Song.m4a"
