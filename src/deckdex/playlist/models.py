"""Data models for playlist functionality."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import uuid4


class SyncStatus(Enum):
    """Playlist synchronization status."""
    PENDING = "pending"
    SYNCED = "synced"
    CONFLICT = "conflict"


class PlaylistSource(Enum):
    """Source of the playlist."""
    PLEX = "plex"
    REKORDBOX = "rekordbox"


@dataclass
class PlaylistItem:
    """An item in a playlist representing a track."""
    playlist_id: str
    track_id: str         # Internal track identifier
    position: int
    added_at: datetime = field(default_factory=datetime.now)
    external_id: Optional[str] = None  # ID in source system


@dataclass
class Playlist:
    """A playlist containing ordered tracks."""
    name: str
    source: PlaylistSource
    id: str = field(default_factory=lambda: str(uuid4()))
    description: Optional[str] = None
    external_id: Optional[str] = None  # ID in source system
    items: List[PlaylistItem] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    modified_at: datetime = field(default_factory=datetime.now)
    version: int = 1
    is_active: bool = True


@dataclass
class PlaylistSyncStatus:
    """Tracking status for playlist synchronization."""
    playlist_id: str
    last_plex_sync: Optional[datetime] = None
    last_rekordbox_sync: Optional[datetime] = None
    plex_version: int = 0
    rekordbox_version: int = 0
    sync_status: SyncStatus = SyncStatus.PENDING


@dataclass
class SyncHistoryEntry:
    """Record of a synchronization event."""
    playlist_id: str
    source: PlaylistSource
    action: str  # 'create', 'update', 'delete'
    status: str  # 'success', 'failure'
    sync_time: datetime = field(default_factory=datetime.now)
    details: Optional[str] = None
    id: Optional[int] = None  # Database-assigned ID