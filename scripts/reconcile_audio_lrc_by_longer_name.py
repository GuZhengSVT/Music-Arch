from __future__ import annotations

import argparse
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
import re

AUDIO_SUFFIXES = {".mp3", ".m4a", ".flac", ".wav", ".aac", ".ogg"}
NORMALIZE_RE = re.compile(r"[^a-z0-9\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7a3]+", re.IGNORECASE)


@dataclass
class PairCandidate:
    audio: Path
    lrc: Path
    score: float


def normalize_stem(stem: str) -> str:
    compact = NORMALIZE_RE.sub("", stem.lower())
    return compact


def pair_score(audio_stem: str, lrc_stem: str) -> float:
    a = normalize_stem(audio_stem)
    b = normalize_stem(lrc_stem)
    if not a or not b:
        return 0.0

    ratio = SequenceMatcher(a=a, b=b).ratio()
    if a in b or b in a:
        ratio = max(ratio, 0.9)
    return ratio


def choose_pairs(audios: list[Path], lrcs: list[Path]) -> list[PairCandidate]:
    unmatched_audio = audios[:]
    unmatched_lrc = lrcs[:]
    pairs: list[PairCandidate] = []

    # First pair exact stems.
    audio_by_stem = {p.stem: p for p in unmatched_audio}
    exact = []
    for lrc in unmatched_lrc:
        audio = audio_by_stem.get(lrc.stem)
        if audio is not None:
            exact.append((audio, lrc))

    for audio, lrc in exact:
        if audio in unmatched_audio:
            unmatched_audio.remove(audio)
        if lrc in unmatched_lrc:
            unmatched_lrc.remove(lrc)
        pairs.append(PairCandidate(audio=audio, lrc=lrc, score=1.0))

    # Greedy best-match pairing for remaining files.
    candidates: list[PairCandidate] = []
    for audio in unmatched_audio:
        for lrc in unmatched_lrc:
            score = pair_score(audio.stem, lrc.stem)
            if score >= 0.55:
                candidates.append(PairCandidate(audio=audio, lrc=lrc, score=score))

    used_audio: set[Path] = set()
    used_lrc: set[Path] = set()
    for item in sorted(candidates, key=lambda x: x.score, reverse=True):
        if item.audio in used_audio or item.lrc in used_lrc:
            continue
        used_audio.add(item.audio)
        used_lrc.add(item.lrc)
        pairs.append(item)

    return pairs


def safer_target(path: Path, target_name: str) -> Path:
    target = path.with_name(target_name)
    if not target.exists() or target.resolve() == path.resolve():
        return target

    stem = target.stem
    suffix = target.suffix
    parent = target.parent
    index = 1
    while True:
        candidate = parent / f"{stem} ({index}){suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def reconcile(root: Path, apply: bool, report_path: Path) -> tuple[int, int, int]:
    planned = 0
    renamed = 0
    skipped = 0
    lines: list[str] = []

    for directory in sorted({p.parent for p in root.rglob('*') if p.is_file()}):
        files = [p for p in directory.iterdir() if p.is_file()]
        audios = [p for p in files if p.suffix.lower() in AUDIO_SUFFIXES]
        lrcs = [p for p in files if p.suffix.lower() == ".lrc"]
        if not audios or not lrcs:
            continue

        pairs = choose_pairs(audios, lrcs)
        for pair in pairs:
            audio = pair.audio
            lrc = pair.lrc
            if audio.stem == lrc.stem:
                continue

            target_stem = audio.stem if len(audio.stem) >= len(lrc.stem) else lrc.stem
            target_audio = safer_target(audio, f"{target_stem}{audio.suffix}")
            target_lrc = safer_target(lrc, f"{target_stem}.lrc")

            audio_rename_needed = audio.name != target_audio.name
            lrc_rename_needed = lrc.name != target_lrc.name
            if not audio_rename_needed and not lrc_rename_needed:
                continue

            planned += int(audio_rename_needed) + int(lrc_rename_needed)
            lines.append(
                f"PAIR\t{directory}\tscore={pair.score:.3f}\taudio={audio.name}\tlrc={lrc.name}\ttarget_stem={target_stem}"
            )

            if apply:
                try:
                    if audio_rename_needed:
                        audio.rename(target_audio)
                        renamed += 1
                        lines.append(f"RENAMED\t{audio}\t->\t{target_audio}")
                        audio = target_audio
                    if lrc_rename_needed:
                        lrc.rename(target_lrc)
                        renamed += 1
                        lines.append(f"RENAMED\t{lrc}\t->\t{target_lrc}")
                except Exception as exc:
                    skipped += 1
                    lines.append(f"SKIPPED\t{directory}\t{exc}")
            else:
                if audio_rename_needed:
                    lines.append(f"PLAN\t{audio}\t->\t{target_audio}")
                if lrc_rename_needed:
                    lines.append(f"PLAN\t{lrc}\t->\t{target_lrc}")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    mode = "APPLY" if apply else "DRY_RUN"
    with report_path.open("w", encoding="utf-8") as fp:
        fp.write(f"mode={mode}\n")
        fp.write(f"root={root}\n")
        fp.write(f"planned={planned}\n")
        fp.write(f"renamed={renamed}\n")
        fp.write(f"skipped={skipped}\n")
        for line in lines:
            fp.write(line + "\n")

    return planned, renamed, skipped


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile audio/lrc names in the same folder by keeping the longer stem."
    )
    parser.add_argument("root", type=Path, help="Music root folder")
    parser.add_argument("--apply", action="store_true", help="Apply rename changes")
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("reports/reconcile_audio_lrc_report.txt"),
        help="Report output path",
    )
    args = parser.parse_args()

    if not args.root.exists() or not args.root.is_dir():
        raise SystemExit(f"Invalid root folder: {args.root}")

    planned, renamed, skipped = reconcile(args.root, apply=args.apply, report_path=args.report)
    print(f"MODE={'APPLY' if args.apply else 'DRY_RUN'}")
    print(f"PLANNED={planned}")
    print(f"RENAMED={renamed}")
    print(f"SKIPPED={skipped}")
    print(f"REPORT={args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
