from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from mutagen import File as MutagenFile

from .core_engine import MusicArchEngine


@dataclass(slots=True)
class TrackScanRecord:
    audio_path: str
    relative_path: str
    format: str
    size_bytes: int
    old_file_name: str
    new_file_name: str
    rename_needed: bool
    has_lrc: bool
    lrc_path: str | None
    lrc_new_file_name: str | None
    status: str
    cloud_match_result: str
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    duration_seconds: float | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MusicLibraryScanner:
    """Phase 3 scanner for large music folders."""

    def __init__(
        self,
        engine: MusicArchEngine | None = None,
        max_workers: int = 8,
        filename_max_length: int = 120,
    ):
        self.engine = engine or MusicArchEngine()
        self.max_workers = max_workers
        self.filename_max_length = filename_max_length

    def scan(
        self,
        root_dir: Path,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> list[TrackScanRecord]:
        root = root_dir.expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise ValueError(f"Invalid scan directory: {root_dir}")

        audio_files = list(self._iter_audio_files(root))
        if not audio_files:
            return []

        records: list[TrackScanRecord] = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = [pool.submit(self._build_record, root, path) for path in audio_files]
            total = len(futures)
            done = 0
            for future in as_completed(futures):
                records.append(future.result())
                done += 1
                if progress_callback:
                    progress_callback(done, total, "Scanning files")

        records.sort(key=lambda item: item.relative_path.lower())
        return records

    def scan_as_dicts(
        self,
        root_dir: Path,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self.scan(root_dir, progress_callback=progress_callback)]

    def _iter_audio_files(self, root: Path):
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() in self.engine.AUDIO_SUFFIXES:
                yield path

    def _build_record(self, root: Path, audio_path: Path) -> TrackScanRecord:
        old_file_name = audio_path.name
        new_stem = self.engine.build_new_stem(audio_path.stem, max_length=self.filename_max_length)
        new_file_name = f"{new_stem}{audio_path.suffix}"
        rename_needed = new_file_name != old_file_name

        lrc_path = audio_path.with_suffix(".lrc")
        has_lrc = lrc_path.exists()

        metadata: dict[str, Any] = {}
        status = "pending"
        error: str | None = None

        try:
            metadata = self._read_basic_metadata(audio_path)
        except Exception as exc:
            status = "anomaly"
            error = str(exc)

        return TrackScanRecord(
            audio_path=str(audio_path),
            relative_path=str(audio_path.relative_to(root)),
            format=audio_path.suffix.lower().lstrip("."),
            size_bytes=audio_path.stat().st_size,
            old_file_name=old_file_name,
            new_file_name=new_file_name,
            rename_needed=rename_needed,
            has_lrc=has_lrc,
            lrc_path=str(lrc_path) if has_lrc else None,
            lrc_new_file_name=f"{new_stem}.lrc" if has_lrc else None,
            status=status,
            cloud_match_result="待匹配",
            title=metadata.get("title"),
            artist=metadata.get("artist"),
            album=metadata.get("album"),
            duration_seconds=metadata.get("duration_seconds"),
            error=error,
        )

    def _read_basic_metadata(self, audio_path: Path) -> dict[str, Any]:
        audio = MutagenFile(audio_path)
        if audio is None:
            return {}

        duration_seconds = None
        if hasattr(audio, "info") and getattr(audio.info, "length", None) is not None:
            duration_seconds = float(audio.info.length)

        tags = getattr(audio, "tags", None)
        title = self._extract_tag(tags, "title", "TIT2", "\xa9nam")
        artist = self._extract_tag(tags, "artist", "TPE1", "\xa9ART")
        album = self._extract_tag(tags, "album", "TALB", "\xa9alb")

        return {
            "duration_seconds": duration_seconds,
            "title": title,
            "artist": artist,
            "album": album,
        }

    def _extract_tag(self, tags: Any, *keys: str) -> str | None:
        if tags is None:
            return None

        for key in keys:
            value = None
            try:
                if hasattr(tags, "get"):
                    value = tags.get(key)
            except Exception:
                value = None

            if value is None:
                continue

            if isinstance(value, list) and value:
                return str(value[0]).strip() or None

            text_attr = getattr(value, "text", None)
            if isinstance(text_attr, list) and text_attr:
                return str(text_attr[0]).strip() or None

            raw = str(value).strip()
            if raw:
                return raw

        return None
