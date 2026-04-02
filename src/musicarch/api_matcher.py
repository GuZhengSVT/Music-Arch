from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import json
import re
import time
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
    error_code: str | None = None
    error_message: str | None = None


def join_artists(artists: list[str], separator: str = " / ") -> str:
    normalized = [str(item).strip() for item in artists if str(item).strip()]
    return separator.join(normalized)


def is_instrumental_lyrics(lyrics_text: str) -> bool:
    text = str(lyrics_text or "").strip().lower()
    if not text:
        return False
    markers = [
        "纯音乐",
        "instrumental",
        "inst.",
        "请欣赏",
        "没有填词",
        "暂无歌词",
    ]
    return any(marker in text for marker in markers)


class BaseMusicSearchClient:
    source_name = "base"

    def __init__(self, timeout: float = 10.0, retries: int = 2, backoff_seconds: float = 0.4):
        self.timeout = timeout
        self.retries = max(0, retries)
        self.backoff_seconds = max(0.0, backoff_seconds)

    def search_tracks(self, query: str, limit: int = 5) -> list[CloudTrackCandidate]:
        raise NotImplementedError

    def _call_with_retry(self, request_func):
        attempt = 0
        while True:
            try:
                return request_func()
            except httpx.TimeoutException:
                if attempt >= self.retries:
                    raise
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status not in {429, 500, 502, 503, 504} or attempt >= self.retries:
                    raise
            except httpx.HTTPError:
                if attempt >= self.retries:
                    raise

            attempt += 1
            sleep_for = self.backoff_seconds * (2 ** (attempt - 1))
            if sleep_for > 0:
                time.sleep(sleep_for)


class NetEaseSearchClient(BaseMusicSearchClient):
    source_name = "netease"

    def __init__(self, timeout: float = 10.0, retries: int = 2, backoff_seconds: float = 0.4):
        super().__init__(timeout=timeout, retries=retries, backoff_seconds=backoff_seconds)

    def search_tracks(self, query: str, limit: int = 5) -> list[CloudTrackCandidate]:
        url = "https://music.163.com/api/cloudsearch/pc"
        payload = {"s": query, "type": 1, "offset": 0, "limit": limit}
        headers = {"Referer": "https://music.163.com", "User-Agent": "MusicArch/0.1"}

        resp = self._call_with_retry(
            lambda: httpx.post(url, data=payload, headers=headers, timeout=self.timeout)
        )
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


class NetEaseLyricClient(BaseMusicSearchClient):
    source_name = "netease-lyric"

    def __init__(self, timeout: float = 10.0, retries: int = 2, backoff_seconds: float = 0.4):
        super().__init__(timeout=timeout, retries=retries, backoff_seconds=backoff_seconds)

    def search_tracks(self, query: str, limit: int = 5) -> list[CloudTrackCandidate]:
        # Keep BaseMusicSearchClient contract; not used for lyric fetch.
        return []

    def fetch_lyric_text(self, track_id: str) -> str | None:
        if not str(track_id).strip():
            return None

        url = "https://music.163.com/api/song/lyric"
        headers = {"Referer": "https://music.163.com", "User-Agent": "MusicArch/0.1"}
        params = {"id": str(track_id), "lv": 1, "kv": 1, "tv": -1}

        resp = self._call_with_retry(
            lambda: httpx.get(url, params=params, headers=headers, timeout=self.timeout)
        )
        resp.raise_for_status()
        data = resp.json()

        lrc_data = data.get("lrc") if isinstance(data, dict) else None
        if not isinstance(lrc_data, dict):
            return None
        lyric_text = lrc_data.get("lyric")
        if isinstance(lyric_text, str) and lyric_text.strip():
            return lyric_text
        return None


class QQMusicSearchClient(BaseMusicSearchClient):
    source_name = "qqmusic"

    def __init__(self, timeout: float = 10.0, retries: int = 2, backoff_seconds: float = 0.4):
        super().__init__(timeout=timeout, retries=retries, backoff_seconds=backoff_seconds)

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

        resp = self._call_with_retry(
            lambda: httpx.get(url, params=params, headers=headers, timeout=self.timeout)
        )
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

    def __init__(
        self,
        access_token: str,
        timeout: float = 10.0,
        retries: int = 2,
        backoff_seconds: float = 0.4,
    ):
        super().__init__(timeout=timeout, retries=retries, backoff_seconds=backoff_seconds)
        self.access_token = access_token

    def search_tracks(self, query: str, limit: int = 5) -> list[CloudTrackCandidate]:
        url = "https://api.spotify.com/v1/search"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        params = {"q": query, "type": "track", "limit": limit}

        resp = self._call_with_retry(
            lambda: httpx.get(url, headers=headers, params=params, timeout=self.timeout)
        )
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
        lyric_client: NetEaseLyricClient | None = None,
    ):
        self.clients = list(clients)
        self.duration_tolerance_seconds = duration_tolerance_seconds
        self.min_confidence = min_confidence
        self.lyric_client = lyric_client or NetEaseLyricClient()

    def _classify_error(self, exc: Exception) -> tuple[str, str]:
        if isinstance(exc, httpx.TimeoutException):
            return "timeout", str(exc)
        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code if exc.response is not None else "unknown"
            return "http_status", f"HTTP {status}"
        if isinstance(exc, httpx.HTTPError):
            return "network", str(exc)
        if isinstance(exc, (json.JSONDecodeError, ValueError)):
            return "parse_error", str(exc)
        return "unknown", str(exc)

    def search_candidates(
        self,
        local: LocalTrackInfo,
        limit_per_source: int = 5,
    ) -> tuple[list[CloudTrackCandidate], list[tuple[str, str, str]]]:
        query = f"{local.artist} {local.title}".strip()
        candidates: list[CloudTrackCandidate] = []
        errors: list[tuple[str, str, str]] = []
        for client in self.clients:
            try:
                candidates.extend(client.search_tracks(query=query, limit=limit_per_source))
            except Exception as exc:
                code, message = self._classify_error(exc)
                errors.append((client.source_name, code, message))
                continue
        return candidates, errors

    def match(self, local: LocalTrackInfo, limit_per_source: int = 5) -> MatchDecision:
        candidates, errors = self.search_candidates(local, limit_per_source=limit_per_source)
        if not candidates:
            error_code = None
            error_message = None
            if errors:
                source, code, message = errors[0]
                error_code = code
                error_message = f"{source}: {message}"
            return MatchDecision(
                status="not_found",
                confidence=0.0,
                reason="No cloud candidate found",
                best_candidate=None,
                error_code=error_code,
                error_message=error_message,
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

    def fetch_lyrics_for_match(self, decision: MatchDecision, local: LocalTrackInfo) -> str | None:
        if not self.lyric_client:
            return None

        candidate = decision.best_candidate
        # Prefer the matched NetEase song id when available.
        if candidate and candidate.source == "netease" and candidate.track_id:
            lyric = self.lyric_client.fetch_lyric_text(candidate.track_id)
            if lyric:
                return lyric

        # Fallback: search NetEase by local metadata and request lyric from top candidate.
        fallback_client = NetEaseSearchClient(
            timeout=self.lyric_client.timeout,
            retries=self.lyric_client.retries,
            backoff_seconds=self.lyric_client.backoff_seconds,
        )
        query = f"{local.artist} {local.title}".strip()
        if not query:
            return None

        try:
            candidates = fallback_client.search_tracks(query=query, limit=3)
        except Exception:
            return None

        for item in candidates:
            if not item.track_id:
                continue
            try:
                lyric = self.lyric_client.fetch_lyric_text(item.track_id)
            except Exception:
                continue
            if lyric:
                return lyric

        return None


def format_match_result(decision: MatchDecision) -> str:
    if decision.status == "not_found":
        if decision.error_code and decision.error_message:
            return f"未找到云端结果({decision.error_code}: {decision.error_message})"
        return "未找到云端结果"
    if not decision.best_candidate:
        return "匹配异常"

    candidate = decision.best_candidate
    artist = "/".join(candidate.artists)
    confidence = f"{decision.confidence:.0%}"
    if decision.status == "anomaly":
        return f"异常: {candidate.source} {artist} - {candidate.title} (置信度{confidence}, {decision.reason})"
    return f"匹配: {candidate.source} {artist} - {candidate.title} (置信度{confidence})"
