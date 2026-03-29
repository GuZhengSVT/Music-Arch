from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Callable

from .api_matcher import LocalTrackInfo, MetadataMatcher, format_match_result
from .core_engine import MusicArchEngine


class MusicArchWorkflow:
    """Coordinate cloud matching and apply changes for GUI workers."""

    def __init__(
        self,
        engine: MusicArchEngine | None = None,
        matcher: MetadataMatcher | None = None,
    ):
        self.engine = engine or MusicArchEngine()
        self.matcher = matcher

    def match_records(
        self,
        records: list[dict],
        progress_callback: Callable[[int, int, str], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> list[dict]:
        if not self.matcher:
            raise ValueError("MetadataMatcher is not configured")

        updated = deepcopy(records)
        total = len(updated)
        for idx, record in enumerate(updated, start=1):
            if should_stop and should_stop():
                break

            local = self._build_local_track(record)
            decision = self.matcher.match(local)
            record["cloud_match_result"] = format_match_result(decision)

            if decision.status in {"anomaly", "not_found"}:
                record["status"] = "anomaly"

            if progress_callback:
                progress_callback(idx, total, f"Matching: {record.get('old_file_name', '')}")

        return updated

    def apply_changes(
        self,
        records: list[dict],
        progress_callback: Callable[[int, int, str], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> list[dict]:
        updated = deepcopy(records)
        total = len(updated)

        for idx, record in enumerate(updated, start=1):
            if should_stop and should_stop():
                break

            if record.get("skip_apply"):
                if progress_callback:
                    progress_callback(idx, total, f"Skipped: {record.get('old_file_name', '')}")
                continue

            try:
                updated_record = self._apply_one(record)
                record.update(updated_record)
                if record.get("status") != "anomaly":
                    record["status"] = "success"
            except Exception as exc:
                record["status"] = "anomaly"
                record["error"] = str(exc)

            if progress_callback:
                progress_callback(idx, total, f"Applying: {record.get('old_file_name', '')}")

        return updated

    def _build_local_track(self, record: dict) -> LocalTrackInfo:
        title = str(record.get("title") or Path(str(record.get("new_file_name", ""))).stem).strip()
        artist = str(record.get("artist") or self._infer_artist(record)).strip()

        duration = record.get("duration_seconds")
        duration_value = float(duration) if isinstance(duration, (int, float)) else None

        album = record.get("album")
        album_value = str(album).strip() if album else None

        return LocalTrackInfo(
            title=title,
            artist=artist,
            duration_seconds=duration_value,
            album=album_value,
        )

    def _infer_artist(self, record: dict) -> str:
        relative_path = str(record.get("relative_path", ""))
        if relative_path:
            parts = Path(relative_path).parts
            if len(parts) >= 2:
                return parts[0]
        return "Unknown Artist"

    def _apply_one(self, record: dict) -> dict:
        audio_path = Path(str(record["audio_path"]))
        current_audio_path = audio_path

        if record.get("rename_needed"):
            target_audio_path = audio_path.with_name(str(record["new_file_name"]))
            if target_audio_path != audio_path:
                self._safe_rename(audio_path, target_audio_path)
                current_audio_path = target_audio_path

                if record.get("has_lrc") and record.get("lrc_path") and record.get("lrc_new_file_name"):
                    current_lrc_path = Path(str(record["lrc_path"]))
                    if current_lrc_path.exists():
                        target_lrc_path = current_lrc_path.with_name(str(record["lrc_new_file_name"]))
                        self._safe_rename(current_lrc_path, target_lrc_path)
                        record["lrc_path"] = str(target_lrc_path)

        embedded = self.engine.embed_lrc_for_audio(current_audio_path)

        return {
            "audio_path": str(current_audio_path),
            "new_file_name": current_audio_path.name,
            "rename_needed": False,
            "embedded_lyrics": embedded,
        }

    def _safe_rename(self, src: Path, dst: Path) -> None:
        if dst.exists() and dst.resolve() != src.resolve():
            raise FileExistsError(f"Target already exists: {dst}")
        src.rename(dst)
