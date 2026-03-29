import httpx

from musicarch.api_matcher import (
    BaseMusicSearchClient,
    CloudTrackCandidate,
    LocalTrackInfo,
    MetadataMatcher,
    format_match_result,
)


class FakeClient(BaseMusicSearchClient):
    source_name = "fake"

    def __init__(self, payload: list[CloudTrackCandidate]):
        self.payload = payload

    def search_tracks(self, query: str, limit: int = 5) -> list[CloudTrackCandidate]:
        return self.payload[:limit]


class FailingClient(BaseMusicSearchClient):
    source_name = "failing"

    def search_tracks(self, query: str, limit: int = 5) -> list[CloudTrackCandidate]:
        raise httpx.TimeoutException("request timeout")


def test_match_success_high_confidence():
    local = LocalTrackInfo(title="Yellow", artist="Coldplay", duration_seconds=266)
    cand = CloudTrackCandidate(
        source="fake",
        track_id="1",
        title="Yellow",
        artists=["Coldplay"],
        duration_seconds=267,
        album="Parachutes",
    )
    matcher = MetadataMatcher([FakeClient([cand])])
    decision = matcher.match(local)

    assert decision.status == "matched"
    assert decision.confidence >= 0.6
    assert "匹配" in format_match_result(decision)


def test_match_anomaly_when_duration_gap_too_large():
    local = LocalTrackInfo(title="Fix You", artist="Coldplay", duration_seconds=295)
    cand = CloudTrackCandidate(
        source="fake",
        track_id="2",
        title="Fix You",
        artists=["Coldplay"],
        duration_seconds=310,
    )
    matcher = MetadataMatcher([FakeClient([cand])], duration_tolerance_seconds=5)
    decision = matcher.match(local)

    assert decision.status == "anomaly"
    assert decision.duration_diff_seconds is not None
    assert decision.duration_diff_seconds > 5


def test_match_not_found_when_no_candidates():
    local = LocalTrackInfo(title="Unknown Song", artist="Unknown Artist", duration_seconds=200)
    matcher = MetadataMatcher([FakeClient([])])
    decision = matcher.match(local)

    assert decision.status == "not_found"
    assert decision.best_candidate is None


def test_match_anomaly_when_confidence_too_low():
    local = LocalTrackInfo(title="Numb", artist="Linkin Park", duration_seconds=185)
    cand = CloudTrackCandidate(
        source="fake",
        track_id="3",
        title="Random Name",
        artists=["Another Artist"],
        duration_seconds=185,
    )
    matcher = MetadataMatcher([FakeClient([cand])], min_confidence=0.7)
    decision = matcher.match(local)

    assert decision.status == "anomaly"
    assert decision.reason == "Low confidence match"


def test_match_not_found_contains_error_metadata_when_client_fails():
    local = LocalTrackInfo(title="A", artist="B")
    matcher = MetadataMatcher([FailingClient()])
    decision = matcher.match(local)

    assert decision.status == "not_found"
    assert decision.error_code == "timeout"
    assert decision.error_message is not None
    assert "timeout" in format_match_result(decision)
