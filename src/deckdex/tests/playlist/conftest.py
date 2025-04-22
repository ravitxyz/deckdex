"""Test fixtures for playlist module."""

import os
import pytest
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List
from unittest.mock import MagicMock

from deckdex.playlist.models import Playlist, PlaylistItem, PlaylistSource, SyncStatus
from deckdex.utils.plex import PlexPlaylist, PlexTrack


@pytest.fixture
def sample_playlist() -> Playlist:
    """Create a sample playlist for testing."""
    playlist = Playlist(
        id="test-playlist-id",
        name="Test Playlist",
        source=PlaylistSource.PLEX,
        description="Test playlist description",
        external_id="plex-123",
        created_at=datetime(2023, 1, 1, 12, 0, 0),
        modified_at=datetime(2023, 1, 2, 12, 0, 0),
        version=1,
        is_active=True
    )
    
    # Add items to playlist
    items = [
        PlaylistItem(
            playlist_id=playlist.id,
            track_id=f"track-{i}",
            position=i,
            external_id=f"plex-track-{i}",
            added_at=datetime(2023, 1, 1, 12, 0, 0)
        )
        for i in range(3)
    ]
    playlist.items = items
    
    return playlist


@pytest.fixture
def sample_playlists() -> List[Playlist]:
    """Create a list of sample playlists for testing."""
    playlists = []
    
    # Plex playlist
    plex_playlist = Playlist(
        id="plex-playlist-id",
        name="Plex Playlist",
        source=PlaylistSource.PLEX,
        description="Plex playlist description",
        external_id="plex-123",
        version=1
    )
    plex_playlist.items = [
        PlaylistItem(
            playlist_id=plex_playlist.id,
            track_id=f"track-{i}",
            position=i,
            external_id=f"plex-track-{i}"
        )
        for i in range(3)
    ]
    playlists.append(plex_playlist)
    
    # Rekordbox playlist
    rb_playlist = Playlist(
        id="rb-playlist-id",
        name="Rekordbox Playlist",
        source=PlaylistSource.REKORDBOX,
        description="Rekordbox playlist description",
        external_id="rb-123",
        version=1
    )
    rb_playlist.items = [
        PlaylistItem(
            playlist_id=rb_playlist.id,
            track_id=f"track-{i}",
            position=i,
            external_id=f"rb-track-{i}"
        )
        for i in range(3)
    ]
    playlists.append(rb_playlist)
    
    return playlists


@pytest.fixture
def mock_plex_playlists() -> List[PlexPlaylist]:
    """Create mock Plex playlists for testing."""
    playlists = []
    
    # Create some tracks
    tracks = [
        PlexTrack(
            id=f"plex-track-{i}",
            title=f"Track {i}",
            artist=f"Artist {i}",
            album=f"Album {i}" if i % 2 == 0 else None,
            file_path=Path(f"/music/track_{i}.mp3") if i % 3 != 0 else None,
            duration=180 + i * 30,
            updated_at=datetime(2023, 1, 1)
        )
        for i in range(5)
    ]
    
    # Create a playlist
    playlist1 = PlexPlaylist(
        id="plex-123",
        title="Plex Test Playlist 1",
        tracks=tracks[:3],
        summary="Test playlist 1 description",
        created_at=datetime(2023, 1, 1),
        updated_at=datetime(2023, 1, 2)
    )
    playlists.append(playlist1)
    
    # Create another playlist
    playlist2 = PlexPlaylist(
        id="plex-456",
        title="Plex Test Playlist 2",
        tracks=tracks[2:],
        summary="Test playlist 2 description",
        created_at=datetime(2023, 1, 3),
        updated_at=datetime(2023, 1, 4)
    )
    playlists.append(playlist2)
    
    return playlists


@pytest.fixture
def sample_rekordbox_xml() -> str:
    """Create a sample Rekordbox XML for testing."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<DJ_PLAYLISTS Version="1.0.0">
  <COLLECTION>
    <TRACK TrackID="1" Name="Track 1" Artist="Artist 1" Album="Album 1" Genre="House" 
           Location="file:///music/track_1.mp3" TotalTime="180000" AverageBpm="128" />
    <TRACK TrackID="2" Name="Track 2" Artist="Artist 2" Album="Album 2" Genre="Techno" 
           Location="file:///music/track_2.mp3" TotalTime="210000" AverageBpm="130" />
    <TRACK TrackID="3" Name="Track 3" Artist="Artist 3" Album="Album 3" Genre="Trance" 
           Location="file:///music/track_3.mp3" TotalTime="240000" AverageBpm="138" />
  </COLLECTION>
  <PLAYLISTS>
    <NODE Name="ROOT" Type="0">
      <NODE Name="Rekordbox Playlists" Type="0">
        <NODE Name="Test Playlist 1" Type="1" KeyType="0">
          <TRACK Key="1" />
          <TRACK Key="2" />
        </NODE>
        <NODE Name="Test Playlist 2" Type="1" KeyType="0">
          <TRACK Key="2" />
          <TRACK Key="3" />
        </NODE>
      </NODE>
    </NODE>
  </PLAYLISTS>
</DJ_PLAYLISTS>
"""


@pytest.fixture
def rekordbox_xml_file():
    """Create a temporary Rekordbox XML file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tmp:
        # Get sample XML
        xml_content = sample_rekordbox_xml()
        # Write to temporary file
        tmp.write(xml_content.encode('utf-8'))
        tmp.flush()
        
        yield Path(tmp.name)
        
        # Clean up temp file
        os.unlink(tmp.name)


@pytest.fixture
def mock_plex_reader():
    """Create a mock PlexLibraryReader for testing."""
    mock = MagicMock()
    mock.get_playlists = MagicMock()
    mock.get_playlists.return_value = mock_plex_playlists()
    return mock


@pytest.fixture
def mock_track_identifier():
    """Create a mock TrackIdentifierService for testing."""
    mock = MagicMock()
    # Mock identify_by_path to return a predictable track ID
    mock.identify_by_path = MagicMock()
    mock.identify_by_path.side_effect = lambda path: f"track-{path.stem}"
    # Mock get_metadata to return basic metadata
    mock.get_metadata = MagicMock()
    mock.get_metadata.side_effect = lambda track_id: {
        "title": f"Track {track_id.split('-')[-1]}",
        "artist": f"Artist {track_id.split('-')[-1]}",
        "album": f"Album {track_id.split('-')[-1]}",
        "file_path": Path(f"/music/{track_id}.mp3")
    }
    return mock