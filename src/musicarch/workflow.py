from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Callable

from .api_matcher import LocalTrackInfo, MetadataMatcher, format_match_result, is_instrumental_lyrics, join_artists
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
        self.artist_separator = " / "

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
                self._mark_cancelled(updated, start_index=idx - 1)
                break

            local = self._build_local_track(record)
            decision = self.matcher.match(local)
            record["cloud_match_result"] = format_match_result(decision)
            record["match_status"] = decision.status
            record["match_confidence"] = round(float(decision.confidence), 4)
            record["match_reason"] = decision.reason

            if decision.status in {"anomaly", "not_found"}:
                record["status"] = "anomaly"
            elif decision.status == "matched":
                self._apply_matched_candidate(record, decision)

            if progress_callback:
                progress_callback(idx, total, f"Matching: {record.get('old_file_name', '')}")

        return updated

    def apply_metadata(
        self,
        records: list[dict],
        progress_callback: Callable[[int, int, str], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> list[dict]:
        return self._process_records(
            records,
            step_name="Writing metadata",
            action=self._apply_metadata_one,
            progress_callback=progress_callback,
            should_stop=should_stop,
        )

    def apply_rename(
        self,
        records: list[dict],
        progress_callback: Callable[[int, int, str], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> list[dict]:
        return self._process_records(
            records,
            step_name="Renaming",
            action=self._apply_rename_one,
            progress_callback=progress_callback,
            should_stop=should_stop,
        )

    def apply_lyrics(
        self,
        records: list[dict],
        progress_callback: Callable[[int, int, str], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> list[dict]:
        return self._process_records(
            records,
            step_name="Embedding lyrics",
            action=self._apply_lyrics_one,
            progress_callback=progress_callback,
            should_stop=should_stop,
        )

    def apply_changes(
        self,
        records: list[dict],
        progress_callback: Callable[[int, int, str], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> list[dict]:
        """Backward-compatible entrypoint: rename -> lyrics."""
        rename_done = self.apply_rename(records, progress_callback=progress_callback, should_stop=should_stop)
        return self.apply_lyrics(rename_done, progress_callback=progress_callback, should_stop=should_stop)

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

    def _apply_matched_candidate(self, record: dict, decision) -> None:
        candidate = decision.best_candidate
        if candidate is None:
            return

        matched_artists = [str(item).strip() for item in candidate.artists if str(item).strip()]
        matched_artist_text = join_artists(matched_artists, separator=self.artist_separator)

        record["matched_title"] = candidate.title
        record["matched_artists"] = matched_artists
        record["matched_artist"] = matched_artist_text
        record["matched_album"] = candidate.album
        record["matched_source"] = candidate.source
        record["matched_track_id"] = candidate.track_id

        if candidate.title:
            record["title"] = candidate.title
        if matched_artist_text:
            record["artist"] = matched_artist_text
        if candidate.album:
            record["album"] = candidate.album

        file_suffix = Path(str(record.get("audio_path", ""))).suffix
        new_stem = self.engine.build_metadata_filename_stem(
            title=str(record.get("title") or candidate.title or ""),
            artists=matched_artists,
            artist_separator=self.artist_separator,
        )
        if new_stem and file_suffix:
            target_audio_name = f"{new_stem}{file_suffix}"
            record["new_file_name"] = target_audio_name
            record["rename_needed"] = target_audio_name != str(record.get("old_file_name", ""))
            if record.get("has_lrc"):
                record["lrc_new_file_name"] = f"{new_stem}.lrc"

        record["status"] = "pending"

    def _process_records(
        self,
        records: list[dict],
        *,
        step_name: str,
        action: Callable[[dict], dict],
        progress_callback: Callable[[int, int, str], None] | None,
        should_stop: Callable[[], bool] | None,
    ) -> list[dict]:
        updated = deepcopy(records)
        total = len(updated)

        for idx, record in enumerate(updated, start=1):
            if should_stop and should_stop():
                self._mark_cancelled(updated, start_index=idx - 1)
                break

            if record.get("skip_apply"):
                if progress_callback:
                    progress_callback(idx, total, f"Skipped: {record.get('old_file_name', '')}")
                continue

            preflight = self._preflight_record(record)
            if preflight is not None:
                record["status"] = "anomaly"
                record["error_code"] = preflight[0]
                record["error"] = preflight[1]
                if progress_callback:
                    progress_callback(idx, total, f"Preflight failed: {record.get('old_file_name', '')}")
                continue

            try:
                updated_record = action(record)
                record.update(updated_record)
                if record.get("status") != "anomaly":
                    record["status"] = "success"
                record.pop("error_code", None)
                record.pop("error", None)
                record["retryable"] = False
            except Exception as exc:
                record["status"] = "anomaly"
                record["error_code"] = self._classify_apply_error(exc)
                record["error"] = str(exc)
                record["retryable"] = record["error_code"] in {
                    "missing_file",
                    "permission_denied",
                    "io_error",
                    "tag_write_error",
                    "network",
                    "timeout",
                    "http_status",
                }

            if progress_callback:
                progress_callback(idx, total, f"{step_name}: {record.get('old_file_name', '')}")

        return updated

    def _apply_metadata_one(self, record: dict) -> dict:
        audio_path = Path(str(record["audio_path"]))
        title = str(record.get("title") or "").strip() or None

        artists_raw = record.get("matched_artists")
        if not isinstance(artists_raw, list):
            artist_text = str(record.get("artist") or "").strip()
            artists_raw = [part.strip() for part in artist_text.split("/") if part.strip()] if artist_text else []

        album = str(record.get("album") or "").strip() or None
        self.engine.write_metadata(audio_path, title=title, artists=artists_raw, album=album)
        return {
            "metadata_written": True,
        }

    def _apply_rename_one(self, record: dict) -> dict:
        audio_path = Path(str(record["audio_path"]))
        current_audio_path = audio_path

        if record.get("rename_needed"):
            target_audio_path = audio_path.with_name(str(record["new_file_name"]))
            if target_audio_path != audio_path:
                target_audio_path = self._resolve_non_conflicting_path(target_audio_path)
                self._safe_rename(audio_path, target_audio_path)
                current_audio_path = target_audio_path

                if record.get("has_lrc") and record.get("lrc_path") and record.get("lrc_new_file_name"):
                    current_lrc_path = Path(str(record["lrc_path"]))
                    if current_lrc_path.exists():
                        target_lrc_path = current_lrc_path.with_name(str(record["lrc_new_file_name"]))
                        target_lrc_path = self._resolve_non_conflicting_path(target_lrc_path)
                        self._safe_rename(current_lrc_path, target_lrc_path)
                        record["lrc_path"] = str(target_lrc_path)

        return {
            "audio_path": str(current_audio_path),
            "new_file_name": current_audio_path.name,
            "rename_needed": False,
            "rename_applied": True,
        }

    def _apply_lyrics_one(self, record: dict) -> dict:
        audio_path = Path(str(record["audio_path"]))
        lrc_path = audio_path.with_suffix(".lrc")

        if lrc_path.exists():
            try:
                self.engine.embed_lrc_for_audio(audio_path)
            except Exception as exc:
                raise RuntimeError(f"Failed to embed local lyrics: {exc}") from exc
            return {
                "embedded_lyrics": True,
                "lyrics_source": "local_lrc",
                "lrc_path": str(lrc_path),
                "has_lrc": True,
            }

        if not self.matcher:
            return {
                "embedded_lyrics": False,
                "lyrics_source": "none",
            }

        local = self._build_local_track(record)
        decision = self.matcher.match(local)
        lyrics_text = self.matcher.fetch_lyrics_for_match(decision, local)
        if not lyrics_text:
            return {
                "embedded_lyrics": False,
                "lyrics_source": "not_found",
            }

        if is_instrumental_lyrics(lyrics_text):
            return {
                "embedded_lyrics": False,
                "lyrics_source": "instrumental",
            }

        try:
            self.engine.embed_lyrics(audio_path, lyrics_text)
        except Exception as exc:
            raise RuntimeError(f"Failed to embed online lyrics: {exc}") from exc

        return {
            "embedded_lyrics": True,
            "lyrics_source": "online",
            "cloud_lyrics_pulled": True,
        }

    def _safe_rename(self, src: Path, dst: Path) -> None:
        if dst.exists() and dst.resolve() != src.resolve():
            raise FileExistsError(f"Target already exists: {dst}")
        src.rename(dst)

    def _resolve_non_conflicting_path(self, target: Path) -> Path:
        if not target.exists():
            return target

        stem = target.stem
        suffix = target.suffix
        parent = target.parent
        counter = 1
        while True:
            candidate = parent / f"{stem} ({counter}){suffix}"
            if not candidate.exists():
                return candidate
            counter += 1

    def _preflight_record(self, record: dict) -> tuple[str, str] | None:
        audio_path = Path(str(record.get("audio_path", "")))
        if not audio_path.exists():
            return ("missing_file", f"Audio file not found: {audio_path}")
        if not audio_path.is_file():
            return ("invalid_path", f"Not a file: {audio_path}")
        if not audio_path.parent.exists():
            return ("invalid_parent", f"Parent folder missing: {audio_path.parent}")
        return None

    def _classify_apply_error(self, exc: Exception) -> str:
        if isinstance(exc, FileNotFoundError):
            return "missing_file"
        if isinstance(exc, PermissionError):
            return "permission_denied"
        if isinstance(exc, RuntimeError):
            return "tag_write_error"
        message = str(exc).lower()
        if "timeout" in message:
            return "timeout"
        if "http" in message:
            return "http_status"
        if "network" in message:
            return "network"
        if isinstance(exc, OSError):
            return "io_error"
        return "unknown"

    def _mark_cancelled(self, records: list[dict], start_index: int) -> None:
        for i in range(start_index, len(records)):
            status = str(records[i].get("status", ""))
            if status in {"success", "anomaly"}:
                continue
            records[i]["status"] = "cancelled"
