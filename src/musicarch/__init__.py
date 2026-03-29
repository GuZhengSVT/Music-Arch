"""MusicArch core package."""

from .api_matcher import (
	CloudTrackCandidate,
	LocalTrackInfo,
	MatchDecision,
	MetadataMatcher,
)
from .core_engine import MusicArchEngine
from .library_scanner import MusicLibraryScanner, TrackScanRecord
from .workflow import MusicArchWorkflow

__all__ = [
	"MusicArchEngine",
	"MusicLibraryScanner",
	"TrackScanRecord",
	"MusicArchWorkflow",
	"LocalTrackInfo",
	"CloudTrackCandidate",
	"MatchDecision",
	"MetadataMatcher",
]
