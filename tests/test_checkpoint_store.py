from pathlib import Path

from musicarch.checkpoint_store import CheckpointStore


def test_checkpoint_save_and_load_roundtrip(tmp_path: Path):
    store = CheckpointStore()
    checkpoint_path = tmp_path / "checkpoint.jsonl"

    records = [
        {"audio_path": "/a.mp3", "status": "pending"},
        {"audio_path": "/b.mp3", "status": "anomaly"},
    ]
    metadata = {"root_dir": "/music", "version": 1}

    store.save(checkpoint_path, records, metadata)
    loaded_meta, loaded_records = store.load(checkpoint_path)

    assert loaded_meta["root_dir"] == "/music"
    assert len(loaded_records) == 2
    assert loaded_records[1]["status"] == "anomaly"


def test_checkpoint_load_without_meta_header(tmp_path: Path):
    path = tmp_path / "legacy.jsonl"
    path.write_text('{"audio_path": "/x.mp3", "status": "pending"}\n', encoding="utf-8")

    store = CheckpointStore()
    meta, records = store.load(path)

    assert meta == {}
    assert len(records) == 1


def test_checkpoint_load_missing_file_raises(tmp_path: Path):
    store = CheckpointStore()
    missing = tmp_path / "none.jsonl"

    try:
        store.load(missing)
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("Expected FileNotFoundError")


def test_checkpoint_save_is_atomic_and_no_tmp_left(tmp_path: Path):
    store = CheckpointStore()
    path = tmp_path / "atomic.jsonl"

    store.save(path, [{"audio_path": "/z.mp3", "status": "pending"}], {"root_dir": "/music"})

    assert path.exists()
    assert not (tmp_path / "atomic.jsonl.tmp").exists()
