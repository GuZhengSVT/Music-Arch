from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class CheckpointStore:
    """Persist and restore scan/apply state using JSONL."""

    META_KEY = "_meta"

    def save(
        self,
        path: Path,
        records: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        meta = metadata or {}
        temp_path = path.with_suffix(path.suffix + ".tmp")

        with temp_path.open("w", encoding="utf-8") as fp:
            fp.write(json.dumps({self.META_KEY: meta}, ensure_ascii=False) + "\n")
            for record in records:
                fp.write(json.dumps(record, ensure_ascii=False) + "\n")

        temp_path.replace(path)

    def load(self, path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        if not path.exists():
            raise FileNotFoundError(f"Checkpoint not found: {path}")

        records: list[dict[str, Any]] = []
        metadata: dict[str, Any] = {}

        with path.open("r", encoding="utf-8") as fp:
            for line_no, raw_line in enumerate(fp, start=1):
                line = raw_line.strip()
                if not line:
                    continue

                obj = json.loads(line)
                if line_no == 1 and isinstance(obj, dict) and self.META_KEY in obj:
                    raw_meta = obj.get(self.META_KEY)
                    metadata = raw_meta if isinstance(raw_meta, dict) else {}
                    continue

                if not isinstance(obj, dict):
                    continue
                records.append(obj)

        return metadata, records
