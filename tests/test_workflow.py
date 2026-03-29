from pathlib import Path

from musicarch.api_matcher import CloudTrackCandidate, MatchDecision
from musicarch.workflow import MusicArchWorkflow


class FakeMatcher:
    def __init__(self, decision: MatchDecision):
        self.decision = decision

    def match(self, _local):
        return self.decision


def test_match_records_marks_anomaly_on_not_found():
    decision = MatchDecision(
        status="not_found",
        confidence=0.0,
        reason="No cloud candidate found",
        best_candidate=None,
    )
    workflow = MusicArchWorkflow(matcher=FakeMatcher(decision))

    records = [
        {
            "audio_path": "/tmp/a.mp3",
            "relative_path": "Artist/Album/a.mp3",
            "old_file_name": "a.mp3",
            "new_file_name": "a.mp3",
            "status": "pending",
            "cloud_match_result": "待匹配",
        }
    ]

    out = workflow.match_records(records)
    assert out[0]["status"] == "anomaly"
    assert "未找到云端结果" in out[0]["cloud_match_result"]


def test_apply_changes_renames_audio_and_lrc(tmp_path: Path):
    old_audio = tmp_path / "01 - demo.mp3"
    old_lrc = tmp_path / "01 - demo.lrc"
    old_audio.write_bytes(b"audio")
    old_lrc.write_text("[00:01.00]line", encoding="utf-8")

    workflow = MusicArchWorkflow()
    workflow.engine.embed_lrc_for_audio = lambda _path: True

    records = [
        {
            "audio_path": str(old_audio),
            "relative_path": "Artist/Album/01 - demo.mp3",
            "old_file_name": "01 - demo.mp3",
            "new_file_name": "demo.mp3",
            "rename_needed": True,
            "has_lrc": True,
            "lrc_path": str(old_lrc),
            "lrc_new_file_name": "demo.lrc",
            "status": "pending",
            "cloud_match_result": "待匹配",
        }
    ]

    out = workflow.apply_changes(records)

    assert out[0]["status"] == "success"
    assert (tmp_path / "demo.mp3").exists()
    assert (tmp_path / "demo.lrc").exists()
    assert not old_audio.exists()
    assert not old_lrc.exists()


def test_match_records_formats_matched_result():
    candidate = CloudTrackCandidate(
        source="fake",
        track_id="1",
        title="Song",
        artists=["Artist"],
        duration_seconds=100,
    )
    decision = MatchDecision(
        status="matched",
        confidence=0.88,
        reason="High confidence match",
        best_candidate=candidate,
    )

    workflow = MusicArchWorkflow(matcher=FakeMatcher(decision))
    records = [
        {
            "audio_path": "/tmp/b.mp3",
            "relative_path": "Artist/Album/b.mp3",
            "old_file_name": "b.mp3",
            "new_file_name": "b.mp3",
            "status": "pending",
            "cloud_match_result": "待匹配",
            "title": "Song",
            "artist": "Artist",
        }
    ]

    out = workflow.match_records(records)
    assert out[0]["status"] == "pending"
    assert "匹配:" in out[0]["cloud_match_result"]


def test_apply_changes_skips_unconfirmed_anomaly(tmp_path: Path):
    old_audio = tmp_path / "bad.mp3"
    old_audio.write_bytes(b"audio")

    workflow = MusicArchWorkflow()
    called = {"value": False}

    def _fake_embed(_path):
        called["value"] = True
        return True

    workflow.engine.embed_lrc_for_audio = _fake_embed

    records = [
        {
            "audio_path": str(old_audio),
            "relative_path": "Artist/Album/bad.mp3",
            "old_file_name": "bad.mp3",
            "new_file_name": "bad.mp3",
            "rename_needed": False,
            "status": "anomaly",
            "manual_confirmed": False,
            "skip_apply": True,
        }
    ]

    out = workflow.apply_changes(records)
    assert out[0]["status"] == "anomaly"
    assert called["value"] is False


def test_apply_changes_allows_confirmed_anomaly(tmp_path: Path):
    old_audio = tmp_path / "fixme.mp3"
    old_audio.write_bytes(b"audio")

    workflow = MusicArchWorkflow()
    workflow.engine.embed_lrc_for_audio = lambda _path: True

    records = [
        {
            "audio_path": str(old_audio),
            "relative_path": "Artist/Album/fixme.mp3",
            "old_file_name": "fixme.mp3",
            "new_file_name": "fixed.mp3",
            "rename_needed": True,
            "has_lrc": False,
            "status": "pending",
            "manual_confirmed": True,
            "skip_apply": False,
        }
    ]

    out = workflow.apply_changes(records)
    assert out[0]["status"] == "success"
    assert (tmp_path / "fixed.mp3").exists()
