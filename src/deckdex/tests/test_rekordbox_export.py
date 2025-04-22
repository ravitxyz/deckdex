#!/usr/bin/env python3
"""
Rekordbox 7.x Export Test Script

This script creates a test XML file specifically formatted for Rekordbox 7.x import
and validates that the XML structure follows the required format.

Usage:
    python test_rekordbox_export.py [--output PATH] [--use-real-files]
"""

import argparse
import asyncio
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import tempfile
import os

# Add the project root to sys.path
project_root = Path(__file__).resolve().parents[3]  # Navigate to project root
sys.path.insert(0, str(project_root))

from src.deckdex.rekordbox import RekordboxExporter
from src.deckdex.reorganizer import Config

# Sample data for testing
SAMPLE_TRACKS = [
    {
        "id": "track-1",
        "title": "Test Track 1",
        "artist": "Test Artist 1",
        "album": "Test Album 1",
        "genre": "Electronic",
        "bpm": 128.5,
        "key": "1A",
        "year": 2023,
        "duration": 240.5,  # in seconds
        "file_path": "/Users/ravit/Music/test_track_1.mp3"
    },
    {
        "id": "track-2",
        "title": "Test Track 2",
        "artist": "Test Artist 2",
        "album": "Test Album 1",
        "genre": "House",
        "bpm": 124.0,
        "key": "5A",
        "year": 2022,
        "duration": 320.0,
        "file_path": "/Users/ravit/Music/test_track_2.mp3"
    },
    {
        "id": "track-3",
        "title": "Test Track 3",
        "artist": "Test Artist 3",
        "album": "Test Album 2",
        "genre": "Techno",
        "bpm": 140.0,
        "key": "11B",
        "year": 2021,
        "duration": 360.0,
        "file_path": "/Users/ravit/Music/test_track_3.mp3"
    }
]

SAMPLE_PLAYLISTS = [
    {
        "id": "playlist-1",
        "name": "Test Dance Playlist",
        "items": [
            {"track_id": "track-1", "position": 0},
            {"track_id": "track-2", "position": 1}
        ]
    },
    {
        "id": "playlist-2",
        "name": "Test Chill Playlist",
        "items": [
            {"track_id": "track-2", "position": 0},
            {"track_id": "track-3", "position": 1}
        ]
    }
]


class MockTrackIdentifier:
    """Mock track identifier service for testing."""
    
    async def initialize(self):
        """Mock initialization."""
        pass
    
    async def get_metadata(self, track_id):
        """Return metadata for the given track ID."""
        for track in SAMPLE_TRACKS:
            if track["id"] == track_id:
                return track
        return None


async def generate_test_xml(output_path: Path, use_real_files: bool = False, config_path: Optional[Path] = None):
    """Generate a test XML file for Rekordbox 7.x."""
    try:
        # Create temporary directory for the database
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "playlists.db"
            
            # Initialize the exporter with mock data
            exporter = MockRekordboxExporter(
                db_path=db_path,
                dj_library_path=Path("/Users/ravit/Music"),
                output_path=output_path,
                track_identifier=MockTrackIdentifier(),
                collection_name="Deckdex Test"
            )
            
            # Generate the XML
            await exporter.export_all_playlists()
            
            print(f"✅ Successfully generated test XML at {output_path}")
            return validate_xml_structure(output_path)
            
    except Exception as e:
        print(f"❌ Error generating test XML: {e}")
        return False


class MockRekordboxExporter(RekordboxExporter):
    """Mock version of RekordboxExporter that uses sample data."""
    
    async def _fetch_all_playlists(self):
        """Return sample playlists."""
        return SAMPLE_PLAYLISTS
    
    async def _fetch_all_tracks(self, playlists):
        """Return sample tracks."""
        return SAMPLE_TRACKS


def validate_xml_structure(xml_path: Path):
    """Validate the XML structure for Rekordbox 7.x compatibility."""
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        
        # Check basic structure
        if root.tag != "DJ_PLAYLISTS":
            print("❌ Root element is not DJ_PLAYLISTS")
            return False
        
        # Check PRODUCT element
        product = root.find("PRODUCT")
        if product is None:
            print("❌ Missing PRODUCT element")
            return False
        else:
            print(f"✓ Found PRODUCT element: {product.attrib}")
        
        # Check COLLECTION
        collection = root.find("COLLECTION")
        if collection is None:
            print("❌ Missing COLLECTION element")
            return False
        
        tracks = collection.findall("TRACK")
        print(f"✓ Found {len(tracks)} tracks in collection")
        
        # Check track attributes
        for track in tracks[:2]:  # Just check first two tracks
            track_id = track.get("TrackID")
            print(f"  ✓ Track {track_id} attributes: {', '.join([f'{k}={v}' for k, v in track.attrib.items()])}")
            
            # Verify Location format
            location = track.get("Location")
            if location:
                if "file://localhost" not in location:
                    print(f"  ❌ Track {track_id} has incorrect Location format: {location}")
                    print("    Expected format for Rekordbox 7.x: file://localhost/path/to/file")
                    return False
                print(f"  ✓ Location format correct: {location}")
        
        # Check PLAYLISTS
        playlists_node = root.find("PLAYLISTS")
        if playlists_node is None:
            print("❌ Missing PLAYLISTS element")
            return False
        
        # Check ROOT node
        root_node = playlists_node.find("NODE[@Name='ROOT']")
        if root_node is None or root_node.get("Type") != "0":
            print("❌ Missing or incorrect ROOT node")
            return False
        
        # Check collection folder
        collection_folder = root_node.find("NODE[@Type='0']")
        if collection_folder is None:
            print("❌ Missing collection folder node")
            return False
        
        print(f"✓ Found collection folder: {collection_folder.get('Name')}")
        
        # Check playlists
        playlists = collection_folder.findall("NODE[@Type='1']")
        print(f"✓ Found {len(playlists)} playlists")
        
        for playlist in playlists:
            name = playlist.get("Name", "Unknown")
            tracks = playlist.findall("TRACK")
            print(f"  ✓ Playlist '{name}' has {len(tracks)} tracks")
            
            # Verify each track has a Key attribute
            for track in tracks:
                if track.get("Key") is None:
                    print(f"  ❌ Track in playlist '{name}' is missing Key attribute")
                    return False
        
        print("✅ XML structure validation passed")
        
        # Print preview of XML content
        print("\nXML Preview (first 20 lines):")
        with open(xml_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                if i >= 20:
                    print("...")
                    break
                print(f"  {line.rstrip()}")
        
        # Print import instructions for Rekordbox 7.x
        print("\nIMPORT INSTRUCTIONS FOR REKORDBOX 7.x:")
        print("1. Open Rekordbox 7.x")
        print("2. Click View > Show Browser in the top menu")
        print("3. In the browser sidebar, right-click on Playlists")
        print("4. Select Import Playlist")
        print("5. Choose rekordbox xml from the dropdown")
        print(f"6. Navigate to and select: {xml_path}")
        print("7. The playlists should appear in a folder named 'Deckdex Test'")
        
        return True
        
    except Exception as e:
        print(f"❌ Error validating XML: {e}")
        return False


async def main():
    """Run the export test."""
    parser = argparse.ArgumentParser(description="Test Rekordbox 7.x XML export")
    parser.add_argument("--output", type=str, default=str(Path.home() / "rekordbox_test.xml"),
                      help="Path to save the test XML file")
    parser.add_argument("--use-real-files", action="store_true",
                      help="Use actual music files from config")
    parser.add_argument("--config", type=str,
                      help="Path to configuration file")
    
    args = parser.parse_args()
    
    # Generate the test XML
    output_path = Path(args.output)
    config_path = Path(args.config) if args.config else None
    
    success = await generate_test_xml(
        output_path=output_path,
        use_real_files=args.use_real_files,
        config_path=config_path
    )
    
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())