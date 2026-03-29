"""MusicArch core package."""

from .api_matcher import (
	CloudTrackCandidate,
	LocalTrackInfo,
	MatchDecision,
	MetadataMatcher,
)
from .core_engine import MusicArchEngine
from .library_scanner import MusicLibraryScanner, TrackScanRecord

__all__ = [
	"MusicArchEngine",
	"MusicLibraryScanner",
	"TrackScanRecord",
	"LocalTrackInfo",
	"CloudTrackCandidate",
	"MatchDecision",
	"MetadataMatcher",
]
