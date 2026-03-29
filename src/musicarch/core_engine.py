from __future__ import annotations

import re
from pathlib import Path

from mutagen.flac import FLAC
from mutagen.id3 import ID3, ID3NoHeaderError, USLT
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4


class MusicArchEngine:
    """Phase 1 core processing engine (non-GUI)."""

    AUDIO_SUFFIXES = {".mp3", ".flac", ".m4a"}

    # Prefix examples:
    # 01 Song, 01. Song, 01 - Song, Track 01 Song, track_01 Song
    TRACK_PREFIX_PATTERN = re.compile(
        r"^\s*(?:(?:track|trk)\s*[_\-.]?)?\s*\d{1,3}\s*(?:[\-.]|\)|:)?\s*",
        re.IGNORECASE,
    )

    INVALID_FILENAME_CHARS_PATTERN = re.compile(r"[\\/:*?\"<>|]+")
    CONTROL_CHARS_PATTERN = re.compile(r"[\x00-\x1f\x7f]")
    MULTI_SPACE_PATTERN = re.compile(r"\s+")

    def normalize_title(self, original_stem: str) -> str:
        """Remove leading track numbers and normalize spaces."""
        cleaned = self.TRACK_PREFIX_PATTERN.sub("", original_stem).strip()
        if not cleaned:
            cleaned = original_stem.strip()
        return self.MULTI_SPACE_PATTERN.sub(" ", cleaned)

    def sanitize_filename(self, name: str, max_length: int = 120, replacement: str = "-") -> str:
        """Replace invalid filename chars and trim to a safe max length."""
        sanitized = self.INVALID_FILENAME_CHARS_PATTERN.sub(replacement, name)
        sanitized = self.CONTROL_CHARS_PATTERN.sub("", sanitized)
        sanitized = sanitized.replace("\t", " ").replace("\n", " ").strip()
        sanitized = self.MULTI_SPACE_PATTERN.sub(" ", sanitized)

        # Avoid trailing dots/spaces which are problematic on Windows.
        sanitized = sanitized.rstrip(". ")
        if not sanitized:
            sanitized = "untitled"

        if len(sanitized) <= max_length:
            return sanitized

        head = sanitized[:max_length]
        split_idx = head.rfind(" ")
        if split_idx >= max(8, int(max_length * 0.5)):
            head = head[:split_idx]

        head = head.rstrip(". -_")
        return head or sanitized[:max_length]

    def build_new_stem(self, original_stem: str, max_length: int = 120) -> str:
        normalized = self.normalize_title(original_stem)
        return self.sanitize_filename(normalized, max_length=max_length)

    def read_lrc_text(self, lrc_path: Path) -> str:
        """Read LRC text with common encodings fallback."""
        encodings = ["utf-8", "utf-8-sig", "gb18030", "cp932", "latin-1"]
        last_error: Exception | None = None
        for enc in encodings:
            try:
                return lrc_path.read_text(encoding=enc)
            except UnicodeDecodeError as exc:
                last_error = exc
                continue
        if last_error:
            raise last_error
        return lrc_path.read_text()

    def embed_lyrics(self, audio_path: Path, lyrics_text: str) -> None:
        """Embed lyrics into mp3/flac/m4a based on container format."""
        suffix = audio_path.suffix.lower()
        if suffix == ".mp3":
            self._embed_mp3_lyrics(audio_path, lyrics_text)
            return
        if suffix == ".flac":
            self._embed_flac_lyrics(audio_path, lyrics_text)
            return
        if suffix == ".m4a":
            self._embed_m4a_lyrics(audio_path, lyrics_text)
            return
        raise ValueError(f"Unsupported audio format: {audio_path.suffix}")

    def embed_lrc_for_audio(self, audio_path: Path) -> bool:
        """Read sidecar LRC and embed into audio if present.

        Returns True when an LRC exists and is embedded, otherwise False.
        """
        lrc_path = audio_path.with_suffix(".lrc")
        if not lrc_path.exists():
            return False

        lyrics = self.read_lrc_text(lrc_path)
        self.embed_lyrics(audio_path, lyrics)
        return True

    def _embed_mp3_lyrics(self, audio_path: Path, lyrics_text: str) -> None:
        audio = MP3(audio_path)

        try:
            tags = ID3(audio_path)
        except ID3NoHeaderError:
            tags = ID3()

        tags.delall("USLT")
        tags.add(
            USLT(
                encoding=3,
                lang="eng",
                desc="Lyrics",
                text=lyrics_text,
            )
        )

        tags.save(audio_path)
        audio.load(audio_path)

    def _embed_flac_lyrics(self, audio_path: Path, lyrics_text: str) -> None:
        audio = FLAC(audio_path)
        audio["LYRICS"] = lyrics_text
        audio.save()

    def _embed_m4a_lyrics(self, audio_path: Path, lyrics_text: str) -> None:
        audio = MP4(audio_path)
        if audio.tags is None:
            audio.add_tags()
        audio.tags["\xa9lyr"] = [lyrics_text]
        audio.save()
