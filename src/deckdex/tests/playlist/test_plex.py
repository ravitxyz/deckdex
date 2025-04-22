"""Tests for Plex playlist adapter."""

import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from deckdex.playlist.plex import PlexPlaylistAdapter
from deckdex.playlist.models import PlaylistSource
from deckdex.utils.plex import PlexLibraryReader, PlexPlaylist, PlexTrack


@pytest.mark.asyncio
async def test_plex_adapter_init(mock_plex_reader, mock_track_identifier):
    """Test initializing the Plex playlist adapter."""
    adapter = PlexPlaylistAdapter(mock_plex_reader, mock_track_identifier)
    
    # Check properties
    assert adapter.plex_reader is mock_plex_reader
    assert adapter.track_identifier_service is mock_track_identifier


@pytest.mark.asyncio
async def test_get_playlists(mock_plex_reader, mock_track_identifier, mock_plex_playlists):
    """Test getting playlists from Plex."""
    adapter = PlexPlaylistAdapter(mock_plex_reader, mock_track_identifier)
    
    # Mock the convert_playlist method to avoid making actual track ID lookups
    async def mock_convert(plex_playlist):
        from deckdex.playlist.models import Playlist, PlaylistItem
        
        playlist = Playlist(
            name=plex_playlist.title,
            source=PlaylistSource.PLEX,
            external_id=plex_playlist.id
        )
        
        # Add placeholder items
        items = []
        for position, track in enumerate(plex_playlist.tracks):
            items.append(PlaylistItem(
                playlist_id=playlist.id,
                track_id=f"mock-{track.id}",
                position=position,
                external_id=track.id
            ))
        
        playlist.items = items
        return playlist
    
    adapter._convert_playlist = mock_convert
    
    # Get playlists
    playlists = await adapter.get_playlists()
    
    # Verify results
    assert len(playlists) == len(mock_plex_playlists)
    assert playlists[0].name == mock_plex_playlists[0].title
    assert playlists[1].name == mock_plex_playlists[1].title
    assert all(p.source == PlaylistSource.PLEX for p in playlists)
    
    # Check that plex_reader.get_playlists was called
    mock_plex_reader.get_playlists.assert_called_once()


@pytest.mark.asyncio
async def test_get_playlist_by_id(mock_plex_reader, mock_track_identifier, mock_plex_playlists):
    """Test getting a specific playlist by ID."""
    adapter = PlexPlaylistAdapter(mock_plex_reader, mock_track_identifier)
    
    # Create mock playlist by ID method for plex_reader
    async def mock_get_by_id(playlist_id):
        for playlist in mock_plex_playlists:
            if playlist.id == playlist_id:
                return playlist
        return None
    
    mock_plex_reader.get_playlist_by_id = mock_get_by_id
    
    # Mock the convert_playlist method
    async def mock_convert(plex_playlist):
        from deckdex.playlist.models import Playlist, PlaylistItem
        
        playlist = Playlist(
            name=plex_playlist.title,
            source=PlaylistSource.PLEX,
            external_id=plex_playlist.id
        )
        
        # Add placeholder items
        items = []
        for position, track in enumerate(plex_playlist.tracks):
            items.append(PlaylistItem(
                playlist_id=playlist.id,
                track_id=f"mock-{track.id}",
                position=position,
                external_id=track.id
            ))
        
        playlist.items = items
        return playlist
    
    adapter._convert_playlist = mock_convert
    
    # Get playlist by ID
    playlist = await adapter.get_playlist_by_id("plex-123")
    
    # Verify result
    assert playlist is not None
    assert playlist.name == "Plex Test Playlist 1"
    assert playlist.external_id == "plex-123"
    
    # Try with non-existent ID
    playlist = await adapter.get_playlist_by_id("non-existent")
    assert playlist is None


@pytest.mark.asyncio
async def test_convert_playlist(mock_plex_reader, mock_track_identifier):
    """Test converting a Plex playlist to internal format."""
    adapter = PlexPlaylistAdapter(mock_plex_reader, mock_track_identifier)
    
    # Create a test Plex playlist
    tracks = [
        PlexTrack(
            id=f"track-{i}",
            title=f"Track {i}",
            artist=f"Artist {i}",
            file_path=Path(f"/music/track_{i}.mp3") if i % 2 == 0 else None
        )
        for i in range(3)
    ]
    
    plex_playlist = PlexPlaylist(
        id="plex-test",
        title="Test Playlist",
        tracks=tracks
    )
    
    # Set up track_identifier to return predictable IDs
    # Returns track-<filename> for tracks with file paths
    # For tracks without file paths, it should use fallback rekordbox:ID
    
    # Convert the playlist
    playlist = await adapter._convert_playlist(plex_playlist)
    
    # Verify basic properties
    assert playlist.name == "Test Playlist"
    assert playlist.source == PlaylistSource.PLEX
    assert playlist.external_id == "plex-test"
    
    # Verify items
    assert len(playlist.items) == 3
    
    # Tracks with file paths should have track IDs from identifier
    # Tracks without file paths should have "plex:" prefixed IDs
    for i, item in enumerate(playlist.items):
        if i % 2 == 0:  # Has file path
            # track_id should come from track_identifier
            assert item.track_id.startswith("track-")
        else:  # No file path
            # Should use fallback ID
            assert item.track_id.startswith("plex:")
        
        assert item.position == i
        assert item.external_id == f"track-{i}"