"""MusicArch core package."""

from .api_matcher import (
	CloudTrackCandidate,
	LocalTrackInfo,
	MatchDecision,
	MetadataMatcher,
)
from .core_engine import MusicArchEngine

__all__ = [
	"MusicArchEngine",
	"LocalTrackInfo",
	"CloudTrackCandidate",
	"MatchDecision",
	"MetadataMatcher",
]
