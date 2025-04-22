"""Tests for playlist synchronization service."""

import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from deckdex.playlist.models import Playlist, PlaylistItem, PlaylistSource, SyncStatus
from deckdex.playlist.sync import PlaylistSyncService


@pytest.fixture
def mock_playlist_service():
    """Create a mock PlaylistService."""
    mock_service = MagicMock()
    
    # Mock async methods
    mock_service.get_playlists_by_source = MagicMock()
    mock_service.get_playlists_needing_sync = MagicMock()
    mock_service.create_playlist = MagicMock()
    mock_service.update_playlist = MagicMock()
    mock_service.update_sync_status = MagicMock()
    
    # Return mock playlists by source
    async def mock_get_by_source(source):
        if source == PlaylistSource.PLEX:
            return [
                Playlist(
                    id="plex-1",
                    name="Plex Playlist 1",
                    source=PlaylistSource.PLEX,
                    external_id="plex-123"
                )
            ]
        elif source == PlaylistSource.REKORDBOX:
            return [
                Playlist(
                    id="rb-1",
                    name="Rekordbox Playlist 1",
                    source=PlaylistSource.REKORDBOX,
                    external_id="rb-123"
                )
            ]
        return []
    
    mock_service.get_playlists_by_source.side_effect = mock_get_by_source
    
    # Return playlists needing sync
    async def mock_needing_sync(source=None):
        if source == PlaylistSource.PLEX:
            return [("plex-1", MagicMock())]
        elif source == PlaylistSource.REKORDBOX:
            return [("rb-1", MagicMock())]
        return [("plex-1", MagicMock()), ("rb-1", MagicMock())]
    
    mock_service.get_playlists_needing_sync.side_effect = mock_needing_sync
    
    # Mock create_playlist to return ID
    async def mock_create(playlist):
        return playlist.id
    
    mock_service.create_playlist.side_effect = mock_create
    
    # Mock update_playlist to return True
    mock_service.update_playlist.return_value = True
    
    # Mock update_sync_status to return True
    mock_service.update_sync_status.return_value = True
    
    return mock_service


@pytest.fixture
def mock_rekordbox_xml():
    """Create a mock RekordboxXML."""
    mock_rb = MagicMock()
    
    # Mock async methods
    mock_rb.read_xml = MagicMock()
    mock_rb.generate_xml = MagicMock()
    
    # Return sample playlists from read_xml
    async def mock_read(xml_path):
        return [
            Playlist(
                id="rb-xml-1",
                name="XML Playlist 1",
                source=PlaylistSource.REKORDBOX,
                external_id="rb-xml-123"
            )
        ]
    
    mock_rb.read_xml.side_effect = mock_read
    
    # Return True from generate_xml
    mock_rb.generate_xml.return_value = True
    
    return mock_rb


@pytest.mark.asyncio
async def test_sync_from_plex(mock_playlist_service, mock_plex_reader, mock_track_identifier):
    """Test synchronizing from Plex to database."""
    # Create sync service
    sync_service = PlaylistSyncService(
        playlist_service=mock_playlist_service,
        track_identifier=mock_track_identifier,
        plex_reader=mock_plex_reader
    )
    
    # Mock the _convert_playlist method in PlexPlaylistAdapter
    with patch('deckdex.playlist.plex.PlexPlaylistAdapter._convert_playlist') as mock_convert:
        # Mock converting a Plex playlist to internal format
        async def mock_convert_impl(plex_playlist):
            playlist = Playlist(
                id=f"converted-{plex_playlist.id}",
                name=plex_playlist.title,
                source=PlaylistSource.PLEX,
                external_id=plex_playlist.id
            )
            playlist.items = [
                PlaylistItem(
                    playlist_id=playlist.id,
                    track_id=f"track-{i}",
                    position=i,
                    external_id=f"plex-track-{i}"
                )
                for i in range(3)
            ]
            return playlist
        
        mock_convert.side_effect = mock_convert_impl
        
        # Run sync
        added, updated, failed = await sync_service.sync_from_plex()
        
        # Verify results
        # With our mock setup, we expect each playlist to be "added"
        # The exact numbers will depend on the mock_plex_playlists fixture
        assert added >= 1
        
        # Verify expected methods were called
        mock_plex_reader.get_playlists.assert_called_once()
        assert mock_playlist_service.create_playlist.call_count == added
        # Should've updated sync status for each created playlist
        assert mock_playlist_service.update_sync_status.call_count >= added


@pytest.mark.asyncio
async def test_sync_to_rekordbox(mock_playlist_service, mock_rekordbox_xml, mock_track_identifier):
    """Test synchronizing from database to Rekordbox."""
    # Create temp file for output
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tmp:
        xml_path = Path(tmp.name)
        
        # Create sync service
        sync_service = PlaylistSyncService(
            playlist_service=mock_playlist_service,
            track_identifier=mock_track_identifier,
            rekordbox_xml=mock_rekordbox_xml,
            rekordbox_xml_path=xml_path
        )
        
        # Run sync
        result = await sync_service.sync_to_rekordbox()
        
        # Verify results
        assert result is True
        
        # Verify expected methods were called
        mock_playlist_service.get_playlists_needing_sync.assert_called_once_with(
            PlaylistSource.REKORDBOX
        )
        mock_playlist_service.get_playlists_by_source.assert_called_once_with(
            PlaylistSource.PLEX
        )
        mock_rekordbox_xml.generate_xml.assert_called_once()
        
        # Should've updated sync status for each synced playlist
        assert mock_playlist_service.update_sync_status.call_count >= 1
        
        # Clean up temp file
        os.unlink(xml_path)


@pytest.mark.asyncio
async def test_sync_from_rekordbox(mock_playlist_service, mock_rekordbox_xml, mock_track_identifier):
    """Test synchronizing from Rekordbox to database."""
    # Create temp file for input
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tmp:
        xml_path = Path(tmp.name)
        tmp.write(b"<DJ_PLAYLISTS></DJ_PLAYLISTS>")  # Minimal valid XML
        tmp.flush()
        
        # Create sync service
        sync_service = PlaylistSyncService(
            playlist_service=mock_playlist_service,
            track_identifier=mock_track_identifier,
            rekordbox_xml=mock_rekordbox_xml,
            rekordbox_xml_path=xml_path
        )
        
        # Run sync
        added, updated, failed = await sync_service.sync_from_rekordbox()
        
        # Verify results
        # With our mock setup, we expect each playlist to be "added"
        assert added >= 1
        
        # Verify expected methods were called
        mock_rekordbox_xml.read_xml.assert_called_once_with(xml_path)
        assert mock_playlist_service.create_playlist.call_count == added
        # Should've updated sync status for each created playlist
        assert mock_playlist_service.update_sync_status.call_count >= added
        
        # Clean up temp file
        os.unlink(xml_path)


@pytest.mark.asyncio
async def test_sync_all(mock_playlist_service, mock_plex_reader, mock_rekordbox_xml, mock_track_identifier):
    """Test full synchronization."""
    # Create temp file for output
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tmp:
        xml_path = Path(tmp.name)
        tmp.write(b"<DJ_PLAYLISTS></DJ_PLAYLISTS>")  # Minimal valid XML
        tmp.flush()
        
        # Create sync service
        sync_service = PlaylistSyncService(
            playlist_service=mock_playlist_service,
            track_identifier=mock_track_identifier,
            plex_reader=mock_plex_reader,
            rekordbox_xml=mock_rekordbox_xml,
            rekordbox_xml_path=xml_path
        )
        
        # Mock the internal sync methods
        with patch.object(sync_service, 'sync_from_plex') as mock_from_plex, \
             patch.object(sync_service, 'sync_to_rekordbox') as mock_to_rb, \
             patch.object(sync_service, 'sync_from_rekordbox') as mock_from_rb:
            
            # Set mock return values
            mock_from_plex.return_value = (2, 1, 0)  # 2 added, 1 updated, 0 failed
            mock_to_rb.return_value = True
            mock_from_rb.return_value = (1, 0, 0)  # 1 added, 0 updated, 0 failed
            
            # Run full sync
            added, updated, failed, rb_success = await sync_service.sync_all()
            
            # Verify results
            assert added == 3  # 2 from Plex + 1 from Rekordbox
            assert updated == 1
            assert failed == 0
            assert rb_success is True
            
            # Verify expected methods were called
            mock_from_plex.assert_called_once()
            mock_to_rb.assert_called_once_with(xml_path)
            mock_from_rb.assert_called_once_with(xml_path)
        
        # Clean up temp file
        os.unlink(xml_path)


def test_playlist_needs_update():
    """Test the playlist update detection logic."""
    sync_service = PlaylistSyncService(
        playlist_service=MagicMock(),
        track_identifier=MagicMock()
    )
    
    # Create base playlist
    playlist1 = Playlist(
        id="test-id",
        name="Test Playlist",
        source=PlaylistSource.PLEX
    )
    playlist1.items = [
        PlaylistItem(
            playlist_id=playlist1.id,
            track_id=f"track-{i}",
            position=i
        )
        for i in range(3)
    ]
    
    # Create identical playlist - should not need update
    playlist2 = Playlist(
        id="test-id",
        name="Test Playlist",
        source=PlaylistSource.PLEX
    )
    playlist2.items = [
        PlaylistItem(
            playlist_id=playlist2.id,
            track_id=f"track-{i}",
            position=i
        )
        for i in range(3)
    ]
    
    # Should not need update
    assert sync_service._playlist_needs_update(playlist1, playlist2) is False
    
    # Change name - should need update
    playlist2.name = "Changed Name"
    assert sync_service._playlist_needs_update(playlist1, playlist2) is True
    
    # Reset name, remove an item - should need update
    playlist2.name = playlist1.name
    playlist2.items = playlist2.items[:2]
    assert sync_service._playlist_needs_update(playlist1, playlist2) is True
    
    # Reset items, change order - should need update
    playlist2.items = [
        PlaylistItem(
            playlist_id=playlist2.id,
            track_id=f"track-{i}",
            position=i
        )
        for i in range(3)
    ]
    # Swap positions
    playlist2.items[0].position, playlist2.items[1].position = \
        playlist2.items[1].position, playlist2.items[0].position
    assert sync_service._playlist_needs_update(playlist1, playlist2) is True