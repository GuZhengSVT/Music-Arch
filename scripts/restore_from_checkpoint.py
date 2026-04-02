from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_rows(checkpoint_path: Path) -> list[dict]:
    rows: list[dict] = []
    with checkpoint_path.open("r", encoding="utf-8") as fp:
        for idx, line in enumerate(fp):
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if idx == 0 and "_meta" in obj:
                continue
            rows.append(obj)
    return rows


def build_candidates(rows: list[dict], only_digit_prefix: bool) -> list[tuple[Path, Path, Path, Path]]:
    candidates: list[tuple[Path, Path, Path, Path]] = []
    for row in rows:
        old_name = str(row.get("old_file_name") or "").strip()
        new_name = str(row.get("new_file_name") or "").strip()
        if not old_name or not new_name:
            continue
        if old_name == new_name:
            continue
        if not row.get("rename_needed"):
            continue
        if only_digit_prefix and not old_name[:1].isdigit():
            continue

        audio_path = Path(str(row.get("audio_path") or "")).expanduser()
        if not audio_path.name:
            continue

        old_audio = audio_path.with_name(old_name)
        new_audio = audio_path.with_name(new_name)
        old_lrc = old_audio.with_suffix(".lrc")
        new_lrc = new_audio.with_suffix(".lrc")
        candidates.append((old_audio, new_audio, old_lrc, new_lrc))

    return candidates


def restore(candidates: list[tuple[Path, Path, Path, Path]], apply: bool) -> tuple[int, int]:
    total = 0
    restored = 0

    for old_audio, new_audio, old_lrc, new_lrc in candidates:
        # Only restore records that were actually renamed: new exists and old is missing.
        if old_audio.exists() or not new_audio.exists():
            continue

        total += 1
        print(f"RESTORE AUDIO: {new_audio} -> {old_audio}")
        if apply:
            old_audio.parent.mkdir(parents=True, exist_ok=True)
            new_audio.rename(old_audio)

        if new_lrc.exists() and not old_lrc.exists():
            print(f"RESTORE LRC:   {new_lrc} -> {old_lrc}")
            if apply:
                old_lrc.parent.mkdir(parents=True, exist_ok=True)
                new_lrc.rename(old_lrc)

        restored += 1

    return total, restored


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore filenames using MusicArch checkpoint JSONL.")
    parser.add_argument("checkpoint", type=Path, help="Path to .musicarch_checkpoint.jsonl")
    parser.add_argument("--apply", action="store_true", help="Apply changes. Default is dry-run.")
    parser.add_argument(
        "--all-renames",
        action="store_true",
        help="Restore all rename_needed entries. Default only restores entries whose old filename starts with a digit.",
    )
    args = parser.parse_args()

    if not args.checkpoint.exists():
        raise SystemExit(f"Checkpoint not found: {args.checkpoint}")

    rows = load_rows(args.checkpoint)
    candidates = build_candidates(rows, only_digit_prefix=not args.all_renames)
    total, restored = restore(candidates, apply=args.apply)

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"MODE={mode} | candidate_rows={len(candidates)} | restore_needed={total} | restored={restored}")
    if not args.apply:
        print("Tip: add --apply to perform the rename rollback.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
