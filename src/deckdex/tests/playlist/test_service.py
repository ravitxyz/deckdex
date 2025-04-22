"""Tests for playlist service."""

import os
import pytest
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import aiosqlite

from deckdex.playlist.models import (
    Playlist, 
    PlaylistItem, 
    PlaylistSource, 
    SyncStatus, 
    PlaylistSyncStatus
)
from deckdex.playlist.service import PlaylistService


@pytest.fixture
async def temp_db_path():
    """Create a temporary database file."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield Path(path)
    # Clean up
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
async def playlist_service(temp_db_path):
    """Create a playlist service with a temp database."""
    service = PlaylistService(db_path=temp_db_path)
    await service.initialize()
    return service


@pytest.mark.asyncio
async def test_playlist_service_initialize(temp_db_path):
    """Test initializing the playlist service."""
    # Create service and initialize
    service = PlaylistService(db_path=temp_db_path)
    await service.initialize()
    
    # Verify database tables were created
    async with aiosqlite.connect(temp_db_path) as db:
        # Check playlists table
        cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='playlists'")
        result = await cursor.fetchone()
        assert result is not None
        
        # Check playlist_items table
        cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='playlist_items'")
        result = await cursor.fetchone()
        assert result is not None
        
        # Check playlist_sync table
        cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='playlist_sync'")
        result = await cursor.fetchone()
        assert result is not None
        
        # Check playlist_sync_history table
        cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='playlist_sync_history'")
        result = await cursor.fetchone()
        assert result is not None


@pytest.mark.asyncio
async def test_create_playlist(playlist_service, sample_playlist):
    """Test creating a playlist."""
    # Create a new playlist
    playlist_id = await playlist_service.create_playlist(sample_playlist)
    
    # Verify ID was returned
    assert playlist_id is not None
    assert playlist_id == sample_playlist.id
    
    # Retrieve the playlist and verify it was stored correctly
    retrieved = await playlist_service.get_playlist(playlist_id)
    assert retrieved is not None
    assert retrieved.name == sample_playlist.name
    assert retrieved.source == sample_playlist.source
    assert len(retrieved.items) == len(sample_playlist.items)


@pytest.mark.asyncio
async def test_update_playlist(playlist_service, sample_playlist):
    """Test updating a playlist."""
    # First create a playlist
    playlist_id = await playlist_service.create_playlist(sample_playlist)
    
    # Modify the playlist
    sample_playlist.name = "Updated Playlist"
    sample_playlist.description = "Updated description"
    
    # Add a new item
    new_item = PlaylistItem(
        playlist_id=playlist_id,
        track_id="track-new",
        position=len(sample_playlist.items),
        external_id="plex-track-new"
    )
    sample_playlist.items.append(new_item)
    
    # Update the playlist
    success = await playlist_service.update_playlist(sample_playlist)
    assert success is True
    
    # Retrieve the updated playlist
    retrieved = await playlist_service.get_playlist(playlist_id)
    assert retrieved is not None
    assert retrieved.name == "Updated Playlist"
    assert retrieved.description == "Updated description"
    assert len(retrieved.items) == len(sample_playlist.items)
    assert retrieved.items[-1].track_id == "track-new"


@pytest.mark.asyncio
async def test_delete_playlist(playlist_service, sample_playlist):
    """Test deleting a playlist."""
    # First create a playlist
    playlist_id = await playlist_service.create_playlist(sample_playlist)
    
    # Delete the playlist
    success = await playlist_service.delete_playlist(playlist_id)
    assert success is True
    
    # Try to retrieve the deleted playlist
    retrieved = await playlist_service.get_playlist(playlist_id)
    assert retrieved is None
    
    # But it should be soft deleted, so still in database
    async with aiosqlite.connect(playlist_service.db_path) as db:
        cursor = await db.execute(
            "SELECT is_active FROM playlists WHERE id = ?",
            (playlist_id,)
        )
        result = await cursor.fetchone()
        assert result is not None
        assert result[0] == 0  # is_active should be 0 (False)


@pytest.mark.asyncio
async def test_get_playlists_by_source(playlist_service, sample_playlists):
    """Test retrieving playlists by source."""
    # Create playlists
    for playlist in sample_playlists:
        await playlist_service.create_playlist(playlist)
    
    # Get playlists by source
    plex_playlists = await playlist_service.get_playlists_by_source(PlaylistSource.PLEX)
    rb_playlists = await playlist_service.get_playlists_by_source(PlaylistSource.REKORDBOX)
    
    # Check results
    assert len(plex_playlists) == 1
    assert len(rb_playlists) == 1
    assert plex_playlists[0].name == "Plex Playlist"
    assert rb_playlists[0].name == "Rekordbox Playlist"


@pytest.mark.asyncio
async def test_get_playlist_by_external_id(playlist_service, sample_playlists):
    """Test retrieving a playlist by external ID."""
    # Create playlists
    for playlist in sample_playlists:
        await playlist_service.create_playlist(playlist)
    
    # Get playlist by external ID
    playlist = await playlist_service.get_playlist_by_external_id(
        PlaylistSource.PLEX, "plex-123"
    )
    
    # Check result
    assert playlist is not None
    assert playlist.name == "Plex Playlist"
    assert playlist.external_id == "plex-123"
    
    # Try with non-existent ID
    playlist = await playlist_service.get_playlist_by_external_id(
        PlaylistSource.PLEX, "non-existent"
    )
    assert playlist is None


@pytest.mark.asyncio
async def test_update_sync_status(playlist_service, sample_playlist):
    """Test updating the sync status for a playlist."""
    # First create a playlist
    playlist_id = await playlist_service.create_playlist(sample_playlist)
    
    # Update sync status
    success = await playlist_service.update_sync_status(
        playlist_id,
        PlaylistSource.PLEX,
        SyncStatus.SYNCED,
        version=2
    )
    assert success is True
    
    # Retrieve sync status
    sync_status = await playlist_service.get_sync_status(playlist_id)
    assert sync_status is not None
    assert sync_status.playlist_id == playlist_id
    assert sync_status.sync_status == SyncStatus.SYNCED
    assert sync_status.plex_version == 2
    
    # Update Rekordbox sync status
    success = await playlist_service.update_sync_status(
        playlist_id,
        PlaylistSource.REKORDBOX,
        SyncStatus.SYNCED,
        version=1
    )
    assert success is True
    
    # Retrieve updated sync status
    sync_status = await playlist_service.get_sync_status(playlist_id)
    assert sync_status.plex_version == 2
    assert sync_status.rekordbox_version == 1
    assert sync_status.last_plex_sync is not None
    assert sync_status.last_rekordbox_sync is not None


@pytest.mark.asyncio
async def test_get_playlists_needing_sync(playlist_service, sample_playlists):
    """Test retrieving playlists that need synchronization."""
    # Create playlists
    for playlist in sample_playlists:
        await playlist_service.create_playlist(playlist)
    
    # Initially, all playlists should need sync
    pending_syncs = await playlist_service.get_playlists_needing_sync()
    assert len(pending_syncs) == 2
    
    # Update sync status for one playlist
    await playlist_service.update_sync_status(
        sample_playlists[0].id,
        PlaylistSource.PLEX,
        SyncStatus.SYNCED
    )
    
    # Check specific source sync needs
    plex_pending = await playlist_service.get_playlists_needing_sync(PlaylistSource.PLEX)
    rb_pending = await playlist_service.get_playlists_needing_sync(PlaylistSource.REKORDBOX)
    
    # Both should still need Rekordbox sync
    assert len(rb_pending) == 2
    # Only one should need Plex sync (the Rekordbox one)
    assert len(plex_pending) == 1
    assert plex_pending[0][0] == sample_playlists[1].id  # The Rekordbox playlist