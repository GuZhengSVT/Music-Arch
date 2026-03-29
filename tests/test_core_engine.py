from pathlib import Path
from unittest.mock import patch

from musicarch.core_engine import MusicArchEngine


def test_normalize_title_removes_track_prefix():
    engine = MusicArchEngine()
    assert engine.normalize_title("01 - Hello World") == "Hello World"
    assert engine.normalize_title("Track 07   Song Name") == "Song Name"


def test_sanitize_filename_replaces_invalid_chars():
    engine = MusicArchEngine()
    sanitized = engine.sanitize_filename('A/B:C*D?E"F<G>H|I')
    assert "/" not in sanitized
    assert ":" not in sanitized
    assert "*" not in sanitized


def test_sanitize_filename_truncates_on_word_boundary():
    engine = MusicArchEngine()
    text = "this is a very long title for a song that should be truncated safely"
    out = engine.sanitize_filename(text, max_length=30)
    assert len(out) <= 30
    assert not out.endswith(" ")


def test_embed_lyrics_dispatch_mp3():
    engine = MusicArchEngine()
    with patch.object(engine, "_embed_mp3_lyrics") as mp3_mock:
        engine.embed_lyrics(Path("song.mp3"), "abc")
        mp3_mock.assert_called_once()


def test_embed_lyrics_dispatch_flac():
    engine = MusicArchEngine()
    with patch.object(engine, "_embed_flac_lyrics") as flac_mock:
        engine.embed_lyrics(Path("song.flac"), "abc")
        flac_mock.assert_called_once()


def test_embed_lyrics_dispatch_m4a():
    engine = MusicArchEngine()
    with patch.object(engine, "_embed_m4a_lyrics") as m4a_mock:
        engine.embed_lyrics(Path("song.m4a"), "abc")
        m4a_mock.assert_called_once()


def test_embed_lyrics_rejects_unsupported_format():
    engine = MusicArchEngine()
    try:
        engine.embed_lyrics(Path("song.wav"), "abc")
    except ValueError as exc:
        assert "Unsupported audio format" in str(exc)
    else:
        raise AssertionError("Expected ValueError for unsupported format")
