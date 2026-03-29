from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import json
import re
from typing import Iterable

import httpx


def _normalize_text(text: str) -> str:
    """Normalize text for fuzzy comparisons."""
    compact = re.sub(r"\s+", " ", text).strip().lower()
    return re.sub(r"[^\w\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7a3 ]+", "", compact)


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(a=_normalize_text(a), b=_normalize_text(b)).ratio()


@dataclass(slots=True)
class LocalTrackInfo:
    title: str
    artist: str
    duration_seconds: float | None = None
    album: str | None = None


@dataclass(slots=True)
class CloudTrackCandidate:
    source: str
    track_id: str
    title: str
    artists: list[str]
    duration_seconds: float | None
    album: str | None = None
    url: str | None = None
    raw: dict | None = None


@dataclass(slots=True)
class MatchDecision:
    status: str  # matched | anomaly | not_found
    confidence: float
    reason: str
    best_candidate: CloudTrackCandidate | None
    title_similarity: float | None = None
    artist_similarity: float | None = None
    duration_diff_seconds: float | None = None


class BaseMusicSearchClient:
    source_name = "base"

    def search_tracks(self, query: str, limit: int = 5) -> list[CloudTrackCandidate]:
        raise NotImplementedError


class NetEaseSearchClient(BaseMusicSearchClient):
    source_name = "netease"

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    def search_tracks(self, query: str, limit: int = 5) -> list[CloudTrackCandidate]:
        url = "https://music.163.com/api/cloudsearch/pc"
        payload = {"s": query, "type": 1, "offset": 0, "limit": limit}
        headers = {"Referer": "https://music.163.com", "User-Agent": "MusicArch/0.1"}

        resp = httpx.post(url, data=payload, headers=headers, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()

        songs = ((data.get("result") or {}).get("songs") or [])
        out: list[CloudTrackCandidate] = []
        for song in songs:
            artists = [a.get("name", "") for a in song.get("ar", []) if a.get("name")]
            duration_ms = song.get("dt")
            out.append(
                CloudTrackCandidate(
                    source=self.source_name,
                    track_id=str(song.get("id", "")),
                    title=song.get("name", ""),
                    artists=artists,
                    duration_seconds=(duration_ms / 1000.0) if isinstance(duration_ms, (int, float)) else None,
                    album=(song.get("al") or {}).get("name"),
                    url=f"https://music.163.com/#/song?id={song.get('id')}" if song.get("id") else None,
                    raw=song,
                )
            )
        return out


class QQMusicSearchClient(BaseMusicSearchClient):
    source_name = "qqmusic"

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    def search_tracks(self, query: str, limit: int = 5) -> list[CloudTrackCandidate]:
        url = "https://c.y.qq.com/soso/fcgi-bin/client_search_cp"
        params = {
            "ct": 24,
            "qqmusic_ver": 1298,
            "new_json": 1,
            "remoteplace": "txt.yqq.song",
            "searchid": 46804736771125334,
            "t": 0,
            "aggr": 1,
            "cr": 1,
            "catZhida": 1,
            "lossless": 0,
            "flag_qc": 0,
            "p": 1,
            "n": limit,
            "w": query,
            "g_tk": 5381,
            "loginUin": 0,
            "hostUin": 0,
            "format": "json",
            "inCharset": "utf8",
            "outCharset": "utf-8",
            "notice": 0,
            "platform": "yqq.json",
            "needNewCode": 0,
        }
        headers = {
            "Referer": "https://y.qq.com/",
            "User-Agent": "MusicArch/0.1",
        }

        resp = httpx.get(url, params=params, headers=headers, timeout=self.timeout)
        resp.raise_for_status()

        text = resp.text.strip()
        if text.startswith("callback(") and text.endswith(")"):
            text = text[len("callback(") : -1]
        data = json.loads(text)

        songs = (((data.get("data") or {}).get("song") or {}).get("list") or [])
        out: list[CloudTrackCandidate] = []
        for song in songs:
            artists = [a.get("name", "") for a in song.get("singer", []) if a.get("name")]
            interval = song.get("interval")
            mid = song.get("mid")
            out.append(
                CloudTrackCandidate(
                    source=self.source_name,
                    track_id=str(song.get("id", "")),
                    title=song.get("name", ""),
                    artists=artists,
                    duration_seconds=float(interval) if isinstance(interval, (int, float)) else None,
                    album=song.get("album", {}).get("name") if isinstance(song.get("album"), dict) else None,
                    url=f"https://y.qq.com/n/ryqq/songDetail/{mid}" if mid else None,
                    raw=song,
                )
            )
        return out


class SpotifySearchClient(BaseMusicSearchClient):
    source_name = "spotify"

    def __init__(self, access_token: str, timeout: float = 10.0):
        self.access_token = access_token
        self.timeout = timeout

    def search_tracks(self, query: str, limit: int = 5) -> list[CloudTrackCandidate]:
        url = "https://api.spotify.com/v1/search"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        params = {"q": query, "type": "track", "limit": limit}

        resp = httpx.get(url, headers=headers, params=params, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()

        items = (((data.get("tracks") or {}).get("items")) or [])
        out: list[CloudTrackCandidate] = []
        for item in items:
            artists = [a.get("name", "") for a in item.get("artists", []) if a.get("name")]
            duration_ms = item.get("duration_ms")
            out.append(
                CloudTrackCandidate(
                    source=self.source_name,
                    track_id=str(item.get("id", "")),
                    title=item.get("name", ""),
                    artists=artists,
                    duration_seconds=(duration_ms / 1000.0) if isinstance(duration_ms, (int, float)) else None,
                    album=(item.get("album") or {}).get("name"),
                    url=item.get("external_urls", {}).get("spotify") if isinstance(item.get("external_urls"), dict) else None,
                    raw=item,
                )
            )
        return out


class MetadataMatcher:
    """Search cloud tracks and decide whether local metadata can be trusted."""

    def __init__(
        self,
        clients: Iterable[BaseMusicSearchClient],
        duration_tolerance_seconds: float = 5.0,
        min_confidence: float = 0.60,
    ):
        self.clients = list(clients)
        self.duration_tolerance_seconds = duration_tolerance_seconds
        self.min_confidence = min_confidence

    def search_candidates(self, local: LocalTrackInfo, limit_per_source: int = 5) -> list[CloudTrackCandidate]:
        query = f"{local.artist} {local.title}".strip()
        candidates: list[CloudTrackCandidate] = []
        for client in self.clients:
            try:
                candidates.extend(client.search_tracks(query=query, limit=limit_per_source))
            except Exception:
                continue
        return candidates

    def match(self, local: LocalTrackInfo, limit_per_source: int = 5) -> MatchDecision:
        candidates = self.search_candidates(local, limit_per_source=limit_per_source)
        if not candidates:
            return MatchDecision(
                status="not_found",
                confidence=0.0,
                reason="No cloud candidate found",
                best_candidate=None,
            )

        scored: list[tuple[float, float, float, float | None, CloudTrackCandidate]] = []
        for candidate in candidates:
            title_sim = _similarity(local.title, candidate.title)
            artist_text = " / ".join(candidate.artists)
            artist_sim = _similarity(local.artist, artist_text)
            duration_diff = None
            duration_score = 0.5
            if local.duration_seconds is not None and candidate.duration_seconds is not None:
                duration_diff = abs(local.duration_seconds - candidate.duration_seconds)
                duration_score = max(0.0, 1.0 - (duration_diff / 30.0))

            confidence = (0.5 * title_sim) + (0.3 * artist_sim) + (0.2 * duration_score)
            scored.append((confidence, title_sim, artist_sim, duration_diff, candidate))

        scored.sort(key=lambda item: item[0], reverse=True)
        confidence, title_sim, artist_sim, duration_diff, best = scored[0]

        if confidence < self.min_confidence:
            return MatchDecision(
                status="anomaly",
                confidence=confidence,
                reason="Low confidence match",
                best_candidate=best,
                title_similarity=title_sim,
                artist_similarity=artist_sim,
                duration_diff_seconds=duration_diff,
            )

        if duration_diff is not None and duration_diff > self.duration_tolerance_seconds:
            return MatchDecision(
                status="anomaly",
                confidence=confidence,
                reason=f"Duration mismatch > {self.duration_tolerance_seconds:.0f}s",
                best_candidate=best,
                title_similarity=title_sim,
                artist_similarity=artist_sim,
                duration_diff_seconds=duration_diff,
            )

        return MatchDecision(
            status="matched",
            confidence=confidence,
            reason="High confidence match",
            best_candidate=best,
            title_similarity=title_sim,
            artist_similarity=artist_sim,
            duration_diff_seconds=duration_diff,
        )


def format_match_result(decision: MatchDecision) -> str:
    if decision.status == "not_found":
        return "未找到云端结果"
    if not decision.best_candidate:
        return "匹配异常"

    candidate = decision.best_candidate
    artist = "/".join(candidate.artists)
    confidence = f"{decision.confidence:.0%}"
    if decision.status == "anomaly":
        return f"异常: {candidate.source} {artist} - {candidate.title} (置信度{confidence}, {decision.reason})"
    return f"匹配: {candidate.source} {artist} - {candidate.title} (置信度{confidence})"
