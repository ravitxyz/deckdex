"""Tests for playlist models."""

import pytest
from datetime import datetime
from uuid import uuid4

from deckdex.playlist.models import (
    Playlist, 
    PlaylistItem, 
    PlaylistSource, 
    SyncStatus, 
    PlaylistSyncStatus, 
    SyncHistoryEntry
)


def test_playlist_creation():
    """Test creating a playlist."""
    # Create basic playlist
    playlist = Playlist(
        name="Test Playlist",
        source=PlaylistSource.PLEX
    )
    
    # Check basic properties
    assert playlist.name == "Test Playlist"
    assert playlist.source == PlaylistSource.PLEX
    assert playlist.is_active is True
    assert playlist.version == 1
    
    # ID should be auto-generated
    assert playlist.id is not None
    assert isinstance(playlist.id, str)
    
    # Items should start empty
    assert len(playlist.items) == 0


def test_playlist_with_items():
    """Test creating a playlist with items."""
    # Create playlist
    playlist = Playlist(
        id="test-id",
        name="Test Playlist",
        source=PlaylistSource.PLEX
    )
    
    # Add items
    items = [
        PlaylistItem(
            playlist_id=playlist.id,
            track_id=f"track-{i}",
            position=i
        )
        for i in range(3)
    ]
    playlist.items = items
    
    # Check items
    assert len(playlist.items) == 3
    assert playlist.items[0].track_id == "track-0"
    assert playlist.items[1].track_id == "track-1"
    assert playlist.items[2].track_id == "track-2"
    
    # Check positions
    assert playlist.items[0].position == 0
    assert playlist.items[1].position == 1
    assert playlist.items[2].position == 2


def test_playlist_item():
    """Test playlist item properties."""
    # Create a playlist item
    item = PlaylistItem(
        playlist_id="test-playlist",
        track_id="test-track",
        position=1,
        external_id="ext-123",
        added_at=datetime(2023, 1, 1, 12, 0, 0)
    )
    
    # Check properties
    assert item.playlist_id == "test-playlist"
    assert item.track_id == "test-track"
    assert item.position == 1
    assert item.external_id == "ext-123"
    assert item.added_at == datetime(2023, 1, 1, 12, 0, 0)


def test_playlist_sources():
    """Test playlist source enumeration."""
    # Check enum values
    assert PlaylistSource.PLEX.value == "plex"
    assert PlaylistSource.REKORDBOX.value == "rekordbox"
    
    # Create playlists with different sources
    plex_playlist = Playlist(
        name="Plex Playlist",
        source=PlaylistSource.PLEX
    )
    rb_playlist = Playlist(
        name="Rekordbox Playlist",
        source=PlaylistSource.REKORDBOX
    )
    
    # Check sources
    assert plex_playlist.source == PlaylistSource.PLEX
    assert rb_playlist.source == PlaylistSource.REKORDBOX
    assert plex_playlist.source != rb_playlist.source


def test_sync_status():
    """Test sync status enumeration."""
    # Check enum values
    assert SyncStatus.PENDING.value == "pending"
    assert SyncStatus.SYNCED.value == "synced"
    assert SyncStatus.CONFLICT.value == "conflict"


def test_playlist_sync_status():
    """Test playlist sync status model."""
    # Create sync status
    sync_status = PlaylistSyncStatus(
        playlist_id="test-playlist",
        last_plex_sync=datetime(2023, 1, 1, 12, 0, 0),
        last_rekordbox_sync=datetime(2023, 1, 2, 12, 0, 0),
        plex_version=2,
        rekordbox_version=1,
        sync_status=SyncStatus.SYNCED
    )
    
    # Check properties
    assert sync_status.playlist_id == "test-playlist"
    assert sync_status.last_plex_sync == datetime(2023, 1, 1, 12, 0, 0)
    assert sync_status.last_rekordbox_sync == datetime(2023, 1, 2, 12, 0, 0)
    assert sync_status.plex_version == 2
    assert sync_status.rekordbox_version == 1
    assert sync_status.sync_status == SyncStatus.SYNCED


def test_sync_history_entry():
    """Test sync history entry model."""
    # Create history entry
    entry = SyncHistoryEntry(
        playlist_id="test-playlist",
        sync_time=datetime(2023, 1, 1, 12, 0, 0),
        source=PlaylistSource.PLEX,
        action="create",
        status="success",
        details="Created playlist",
        id=1
    )
    
    # Check properties
    assert entry.playlist_id == "test-playlist"
    assert entry.sync_time == datetime(2023, 1, 1, 12, 0, 0)
    assert entry.source == PlaylistSource.PLEX
    assert entry.action == "create"
    assert entry.status == "success"
    assert entry.details == "Created playlist"
    assert entry.id == 1


def test_sample_playlist_fixture(sample_playlist):
    """Test the sample playlist fixture."""
    # Check basic properties
    assert sample_playlist.name == "Test Playlist"
    assert sample_playlist.source == PlaylistSource.PLEX
    
    # Check items
    assert len(sample_playlist.items) == 3
    for i, item in enumerate(sample_playlist.items):
        assert item.track_id == f"track-{i}"
        assert item.position == i