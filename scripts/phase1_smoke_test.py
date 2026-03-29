from pathlib import Path

from musicarch.core_engine import MusicArchEngine


def run() -> None:
    engine = MusicArchEngine()

    samples = [
        "01 - Hello/World?",
        "Track 07   Song Name",
        "003.  超长标题测试 with symbols : * ? \" < > |",
    ]

    print("== Filename Clean Demo ==")
    for item in samples:
        new_name = engine.build_new_stem(item, max_length=40)
        print(f"{item!r} -> {new_name!r}")

    print("\n== Lyrics Embed Demo ==")
    print("This script does not create fake audio files.")
    print("Provide real file paths below to run embedding:")

    # Replace with your real local files when ready.
    candidate_audio = Path("/tmp/example.mp3")
    candidate_lrc = candidate_audio.with_suffix(".lrc")
    if candidate_audio.exists() and candidate_lrc.exists():
        engine.embed_lrc_for_audio(candidate_audio)
        print(f"Embedded lyrics for: {candidate_audio}")
    else:
        print("Skip embedding demo: /tmp/example.mp3 and /tmp/example.lrc not found")


if __name__ == "__main__":
    run()
