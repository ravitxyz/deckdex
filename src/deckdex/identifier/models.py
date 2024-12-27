from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, field
import uuid

@dataclass
class TrackIdentifier:
    track_id: str
    file_hash: str
    audio_fingerprint: Optional[str] = None
    confidence_score: float = 1.0
    metadata_version: int = 1
    created_at: datetime = field(default_factory=datetime.now)
    last_seen: datetime = field(default_factory=datetime.now)
    is_active: bool = True

@dataclass
class TrackFingerprint:
    track_id: str
    fingerprint: str
    algorithm: str
    confidence: float
    created_at: datetime = field(default_factory=datetime.now)

@dataclass
class TrackLocation:
    track_id: str
    file_path: Path
    timestamp: datetime = datetime.now()