from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Dict,Optional
from dataclasses import dataclass, field
from uuid import uuid4
from enum import Enum

@dataclass
class TrackLocation:
    """Track file location history"""
    track_id: str
    file_path: Path
    timestamp: datetime = field(default_factory=datetime.now)
    active: bool = True  # Whether this is the current location

    def deactivate(self):
        """Mark location as no longer current"""
        self.active = False

@dataclass
class LocationStatus(Enum):
    ACTIVE = "active"
    MOVED = "moved"
    DELETED = "deleted"

class IdentificationMethod(Enum):
    """Methods used to identify tracks"""
    HASH = "hash"
    FINGERPRINT = "fingerprint"
    PATH = "path"
    UUID = "uuid"

class ConfidenceLevel(Enum):
    """Confidence levels for track identifications"""
    HIGH = "high" # Multiple methods match
    MEDIUM = "medium" # Single strong method match (e.g., fingerprint)
    LOW = "low" # Only path/hash match
    UNCERTAIN = "uncertain"


@dataclass
class AudioFingerprint:
    """Chromaprint audio fingerprint data"""
    fingerprint: str
    duration: float
    sample_rate: int
    created_at: datetime = field(default_factory=datetime.now)
    algorithm_version: str = "chromaprint_1"

def similarity_score(self, other: 'AudioFingerprint') -> float:
    """
    Calculate similarity score between two Chromaprint fingerprints
    Returns a score between 0.0 (completely different) and 1.0 (identical)
    """
    if not isinstance(other, AudioFingerprint):
        raise TypeError("Can only compare with another AudioFingerprint")
        
    if self.algorithm_version != other.algorithm_version:
        raise ValueError("Cannot compare fingerprints from different algorithm versions")

    # Convert fingerprint strings to lists of integers
    fp1 = [int(x) for x in self.fingerprint.split(',')]
    fp2 = [int(x) for x in other.fingerprint.split(',')]
    
    # Make sure fingerprints are same length by padding shorter one
    max_len = max(len(fp1), len(fp2))
    fp1.extend([0] * (max_len - len(fp1)))
    fp2.extend([0] * (max_len - len(fp2)))
    
    # Calculate Hamming distance between fingerprints
    differences = sum(1 for x, y in zip(fp1, fp2) if x != y)
    
    # Convert to similarity score (1.0 - normalized hamming distance)
    return 1.0 - (differences / max_len)
@dataclass
class TrackIdentifier:
    """Main track identification class"""
    file_hash: str
    track_id: str = field(default_factory=lambda: str(uuid4()))
    audio_fingerprint: Optional[AudioFingerprint] = None
    created_at: datetime = field(default_factory=datetime.now)
    last_seen: datetime = field(default_factory=datetime.now)
    metadata: Dict = field(default_factory=dict)
    confidence_level: ConfidenceLevel = ConfidenceLevel.UNCERTAIN
    locations: List[TrackLocation] = field(default_factory=list)

    def add_location(self, file_path: Path) -> TrackLocation:
        """Add a new location for the track"""
        # Deactivate previous locations
        for location in self.locations:
            if location.active:
                location.deactivate()
        
        # Create and add new location
        new_location = TrackLocation(
            track_id=self.track_id,
            file_path=file_path
        )
        self.locations.append(new_location)
        return new_location

    def current_location(self) -> Optional[TrackLocation]:
        """Get the current active location of the track"""
        for location in reversed(self.locations):
            if location.active:
                return location
        return None

    def update_fingerprint(self, fingerprint: AudioFingerprint):
        """Update the track's audio fingerprint"""
        self.audio_fingerprint = fingerprint
        self.last_seen = datetime.now()
        self._update_confidence_level()

    def update_hash(self, new_hash: str):
        """Update the track's file hash"""
        self.file_hash = new_hash
        self.last_seen = datetime.now()
        self._update_confidence_level()

    def _update_confidence_level(self):
        """Update confidence level based on available identification methods"""
        methods_available = []
        
        if self.file_hash:
            methods_available.append(IdentificationMethod.HASH)
        if self.audio_fingerprint:
            methods_available.append(IdentificationMethod.FINGERPRINT)
        if self.locations:
            methods_available.append(IdentificationMethod.PATH)
        
        # Set confidence level based on available methods
        if len(methods_available) >= 2 and IdentificationMethod.FINGERPRINT in methods_available:
            self.confidence_level = ConfidenceLevel.HIGH
        elif IdentificationMethod.FINGERPRINT in methods_available:
            self.confidence_level = ConfidenceLevel.MEDIUM
        elif methods_available:
            self.confidence_level = ConfidenceLevel.LOW
        else:
            self.confidence_level = ConfidenceLevel.UNCERTAIN

@dataclass
class TrackIdentificationResult:
    """Result of a track identification operation"""
    identifier: TrackIdentifier
    matched_methods: List[IdentificationMethod]
    is_new: bool
    confidence_level: ConfidenceLevel
    similarity_scores: Dict[IdentificationMethod, float] = field(default_factory=dict)
    
    @property
    def is_confident(self) -> bool:
        """Whether the identification is confident enough to use"""
        return self.confidence_level in (ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM)