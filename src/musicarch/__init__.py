"""MusicArch core package."""

from .api_matcher import (
	CloudTrackCandidate,
	LocalTrackInfo,
	MatchDecision,
	MetadataMatcher,
)
from .checkpoint_store import CheckpointStore
from .core_engine import MusicArchEngine
from .library_scanner import MusicLibraryScanner, TrackScanRecord
from .view_state import PageResult, RecordViewState
from .workflow import MusicArchWorkflow

__all__ = [
	"MusicArchEngine",
	"CheckpointStore",
	"MusicLibraryScanner",
	"TrackScanRecord",
	"RecordViewState",
	"PageResult",
	"MusicArchWorkflow",
	"LocalTrackInfo",
	"CloudTrackCandidate",
	"MatchDecision",
	"MetadataMatcher",
]
