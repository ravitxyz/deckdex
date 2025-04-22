"""Tests for Rekordbox XML handling."""

import os
import pytest
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import MagicMock, patch

from deckdex.playlist.rekordbox import RekordboxXML
from deckdex.playlist.models import Playlist, PlaylistItem, PlaylistSource


@pytest.mark.asyncio
async def test_read_xml(rekordbox_xml_file, mock_track_identifier):
    """Test reading playlists from a Rekordbox XML file."""
    # Create RekordboxXML handler
    rb_xml = RekordboxXML(track_identifier_service=mock_track_identifier)
    
    # Read playlists from XML
    playlists = await rb_xml.read_xml(rekordbox_xml_file)
    
    # Verify results
    assert len(playlists) == 2
    assert playlists[0].name == "Test Playlist 1"
    assert playlists[1].name == "Test Playlist 2"
    assert playlists[0].source == PlaylistSource.REKORDBOX
    assert playlists[1].source == PlaylistSource.REKORDBOX
    
    # Check items in first playlist
    assert len(playlists[0].items) == 2
    # Track IDs should be either identified by track_identifier or prefixed with "rekordbox:"
    assert all(item.track_id.startswith(("track-", "rekordbox:")) for item in playlists[0].items)
    
    # Check items in second playlist
    assert len(playlists[1].items) == 2


@pytest.mark.asyncio
async def test_read_xml_nonexistent_file(mock_track_identifier):
    """Test reading from a nonexistent XML file."""
    # Create RekordboxXML handler
    rb_xml = RekordboxXML(track_identifier_service=mock_track_identifier)
    
    # Try to read from nonexistent file
    playlists = await rb_xml.read_xml(Path("/nonexistent/file.xml"))
    
    # Should return empty list
    assert playlists == []


@pytest.mark.asyncio
async def test_read_xml_invalid_file(mock_track_identifier):
    """Test reading from an invalid XML file."""
    # Create temp file with invalid XML
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tmp:
        tmp.write(b"<invalid>XML</")
        tmp.flush()
        
        # Create RekordboxXML handler
        rb_xml = RekordboxXML(track_identifier_service=mock_track_identifier)
        
        # Try to read from invalid file
        playlists = await rb_xml.read_xml(Path(tmp.name))
        
        # Should return empty list
        assert playlists == []
        
        # Clean up
        os.unlink(tmp.name)


@pytest.mark.asyncio
async def test_generate_xml(sample_playlists, mock_track_identifier):
    """Test generating Rekordbox XML."""
    # Create RekordboxXML handler
    rb_xml = RekordboxXML(track_identifier_service=mock_track_identifier)
    
    # Create temp output file
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tmp:
        output_path = Path(tmp.name)
        
        # Generate XML
        result = await rb_xml.generate_xml(
            sample_playlists,
            output_path=output_path
        )
        
        # Verify result
        assert result is True
        assert output_path.exists()
        
        # Parse the generated XML
        tree = ET.parse(output_path)
        root = tree.getroot()
        
        # Verify structure
        assert root.tag == "DJ_PLAYLISTS"
        assert root.get("Version") == "1.0.0"
        
        # Verify collection
        collection = root.find("COLLECTION")
        assert collection is not None
        tracks = collection.findall("TRACK")
        # There should be at least as many tracks as unique tracks in playlists
        unique_tracks = set()
        for playlist in sample_playlists:
            for item in playlist.items:
                unique_tracks.add(item.track_id)
        assert len(tracks) >= len(unique_tracks)
        
        # Verify playlists
        playlists_elem = root.find("PLAYLISTS")
        assert playlists_elem is not None
        
        # There should be a Deckdex folder
        deckdex_folder = None
        for node in playlists_elem.findall("NODE"):
            if node.get("Name") == "Deckdex" and node.get("Type") == "0":
                deckdex_folder = node
                break
        assert deckdex_folder is not None
        
        # Verify playlist nodes
        playlist_nodes = deckdex_folder.findall("NODE[@Type='1']")
        assert len(playlist_nodes) == len(sample_playlists)
        
        # Check playlist names
        playlist_names = [node.get("Name") for node in playlist_nodes]
        assert all(p.name in playlist_names for p in sample_playlists)
        
        # Clean up
        os.unlink(output_path)


@pytest.mark.asyncio
async def test_generate_xml_merge_with_existing(rekordbox_xml_file, sample_playlists, mock_track_identifier):
    """Test merging with an existing XML file."""
    # Create RekordboxXML handler
    rb_xml = RekordboxXML(track_identifier_service=mock_track_identifier)
    
    # Create temp output file
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tmp:
        output_path = Path(tmp.name)
        
        # Generate XML with merge
        result = await rb_xml.generate_xml(
            sample_playlists,
            output_path=output_path,
            merge_with_existing=True,
            existing_xml_path=rekordbox_xml_file
        )
        
        # Verify result
        assert result is True
        assert output_path.exists()
        
        # Parse the generated XML
        tree = ET.parse(output_path)
        root = tree.getroot()
        
        # Verify structure
        assert root.tag == "DJ_PLAYLISTS"
        
        # Verify collection
        collection = root.find("COLLECTION")
        assert collection is not None
        
        # There should be tracks from both the original file and new playlists
        tracks = collection.findall("TRACK")
        assert len(tracks) >= 3  # At least the original 3 tracks
        
        # Verify playlists
        playlists_elem = root.find("PLAYLISTS")
        assert playlists_elem is not None
        
        # There should be a Deckdex folder
        deckdex_folder = None
        for node in playlists_elem.findall("NODE"):
            if node.get("Name") == "Deckdex" and node.get("Type") == "0":
                deckdex_folder = node
                break
        assert deckdex_folder is not None
        
        # Check number of playlists
        # Should have the original "Test Playlist 1" and "Test Playlist 2" plus new ones
        all_playlists = playlists_elem.findall(".//NODE[@Type='1']")
        assert len(all_playlists) >= 2 + len(sample_playlists)
        
        # Clean up
        os.unlink(output_path)


@pytest.mark.asyncio
async def test_get_track_metadata(mock_track_identifier):
    """Test getting track metadata for XML export."""
    # Create RekordboxXML handler
    rb_xml = RekordboxXML(track_identifier_service=mock_track_identifier)
    
    # Get metadata for a track
    metadata = await rb_xml._get_track_metadata("track-123")
    
    # Verify basic metadata
    assert metadata["Name"] == "Track 123"
    assert metadata["Artist"] == "Artist 123"
    assert metadata["Album"] == "Album 123"
    
    # Location should be URL-encoded
    assert metadata["Location"].startswith("file:///")
    assert "track-123.mp3" in metadata["Location"]
    
    # Test with no track identifier
    rb_xml = RekordboxXML(track_identifier_service=None)
    metadata = await rb_xml._get_track_metadata("track-456")
    
    # Should return basic defaults
    assert metadata["Name"] == "Unknown Track"
    assert metadata["Artist"] == "Unknown Artist"