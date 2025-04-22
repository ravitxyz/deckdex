#!/usr/bin/env python3
"""
Rekordbox Integration Test Script

This script creates a test XML file with sample playlists and validates
that Rekordbox can import them properly. It can optionally launch Rekordbox
if it's installed on the system.

Usage:
    python test_rekordbox_integration.py [--launch-rekordbox] [--rekordbox-path PATH]

Options:
    --launch-rekordbox     Attempt to launch Rekordbox after creating the test XML
    --rekordbox-path PATH  Path to the Rekordbox executable
    --test-xml PATH        Path where to save the test XML file
    --use-real-files       Use actual music files from the config instead of dummy paths
"""

import argparse
import asyncio
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import List, Optional
import shutil

# Add the project root to sys.path
project_root = Path(__file__).resolve().parents[4]  # Navigate to project root (parent of src)
sys.path.insert(0, str(project_root))

from src.deckdex.playlist.models import Playlist, PlaylistItem, PlaylistSource
from src.deckdex.playlist.rekordbox import RekordboxXML
from src.deckdex.reorganizer import Config

# Default paths
DEFAULT_REKORDBOX_PATHS = [
    "/Applications/rekordbox 6/rekordbox.app/Contents/MacOS/rekordbox",  # macOS
    "C:\\Program Files\\Pioneer\\rekordbox 6\\rekordbox.exe",  # Windows
    "/usr/bin/rekordbox"  # Linux (if installed)
]


def find_rekordbox():
    """Attempt to find Rekordbox installation."""
    for path in DEFAULT_REKORDBOX_PATHS:
        if os.path.exists(path):
            return path
    return None


def create_test_playlists(use_real_files: bool = False, config_path: Optional[Path] = None) -> List[Playlist]:
    """Create test playlists for validation.
    
    Args:
        use_real_files: Whether to use real music files from config
        config_path: Path to config file to find music files
        
    Returns:
        List of sample playlists
    """
    playlists = []
    
    # Create tracks with real files if requested
    tracks = []
    if use_real_files and config_path:
        try:
            config = Config.load_config(config_path)
            music_dir = config.source_dir
            
            # Find some actual music files
            audio_files = []
            for ext in ['.mp3', '.flac', '.aiff', '.wav', '.m4a']:
                audio_files.extend(list(music_dir.glob(f"**/*{ext}"))[:5])  # Limit to 5 per type
            
            print(f"Found {len(audio_files)} audio files for testing")
            
            for i, file_path in enumerate(audio_files[:10]):  # Limit to 10 total
                # Extract basic metadata from filename
                artist = file_path.parent.name
                title = file_path.stem
                
                tracks.append({
                    "id": f"track-{i}",
                    "title": title or f"Test Track {i}",
                    "artist": artist or f"Test Artist {i}",
                    "album": f"Test Album {i//3}",
                    "path": file_path
                })
                
        except Exception as e:
            print(f"Error loading real files, using dummy data: {e}")
            use_real_files = False
    
    # Fall back to dummy data if needed
    if not use_real_files or not tracks:
        for i in range(10):
            tracks.append({
                "id": f"track-{i}",
                "title": f"Test Track {i}",
                "artist": f"Test Artist {i}",
                "album": f"Test Album {i//3}",
                "path": Path(f"/Users/ravit/Music/test_track_{i}.mp3")
            })
    
    # Create a few test playlists
    playlist_templates = [
        {"name": "Test Dance Playlist", "tracks": tracks[:5]},
        {"name": "Test Chill Playlist", "tracks": tracks[3:8]},
        {"name": "Test Party Playlist", "tracks": [tracks[1], tracks[3], tracks[5], tracks[7], tracks[9]]}
    ]
    
    # Convert to our model objects
    for template in playlist_templates:
        playlist = Playlist(
            name=template["name"],
            source=PlaylistSource.PLEX,
            description=f"Test playlist for Rekordbox integration ({datetime.now().isoformat()})"
        )
        
        # Add items
        items = []
        for i, track in enumerate(template["tracks"]):
            items.append(PlaylistItem(
                playlist_id=playlist.id,
                track_id=track["id"],
                position=i,
                external_id=track["id"]
            ))
        
        playlist.items = items
        playlists.append(playlist)
    
    return playlists, tracks


async def generate_test_xml(output_path: Path, use_real_files: bool = False, config_path: Optional[Path] = None) -> List[dict]:
    """Generate a test XML file for Rekordbox.
    
    Args:
        output_path: Where to save the XML file
        use_real_files: Whether to use real music files
        config_path: Path to config file
        
    Returns:
        List of track dictionaries used in the XML
    """
    # Create a mock track identifier service
    class MockTrackIdentifier:
        async def get_metadata(self, track_id):
            # Find the track in our tracks list
            for track in tracks:
                if track["id"] == track_id:
                    return {
                        "title": track["title"],
                        "artist": track["artist"],
                        "album": track["album"],
                        "file_path": track["path"] if use_real_files else None
                    }
            return {
                "title": f"Unknown Track {track_id}",
                "artist": "Unknown Artist"
            }
            
        # Add proper URL encoding for file paths that Rekordbox expects
        async def format_location(self, file_path):
            """Format location string properly for Rekordbox XML."""
            from urllib.parse import quote
            path_str = str(file_path)
            # For Mac/Unix absolute paths, use file:// (two slashes)
            if path_str.startswith('/'):
                return f"file://{quote(path_str)}"
            # For Windows paths or non-absolute paths, use file:/// (three slashes)
            return f"file:///{quote(path_str)}"
    
    # Create test playlists and tracks
    playlists, tracks = create_test_playlists(use_real_files, config_path)
    
    # Initialize the RekordboxXML handler
    rb_xml = RekordboxXML(MockTrackIdentifier())
    
    # Generate the XML file
    success = await rb_xml.generate_xml(
        playlists=playlists,
        output_path=output_path
    )
    
    if success:
        print(f"✅ Successfully generated test XML at {output_path}")
        # Validate basic structure
        validate_xml_structure(output_path)
    else:
        print(f"❌ Failed to generate test XML")
    
    return tracks


def validate_xml_structure(xml_path: Path):
    """Validate the basic structure of the generated XML file."""
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        
        # Check basic structure
        if root.tag != "DJ_PLAYLISTS":
            print("❌ Root element is not DJ_PLAYLISTS")
            return False
        
        collection = root.find("COLLECTION")
        if collection is None:
            print("❌ Missing COLLECTION element")
            return False
        
        tracks = collection.findall("TRACK")
        print(f"✓ Found {len(tracks)} tracks in collection")
        
        playlists_elem = root.find("PLAYLISTS")
        if playlists_elem is None:
            print("❌ Missing PLAYLISTS element")
            return False
        
        # Check for Deckdex folder
        deckdex_folder = None
        for node in playlists_elem.findall("NODE"):
            if node.get("Name") == "Deckdex" and node.get("Type") == "0":
                deckdex_folder = node
                break
        
        if deckdex_folder is None:
            print("❌ Missing Deckdex folder node")
            return False
        
        # Check playlists
        playlists = deckdex_folder.findall("NODE[@Type='1']")
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
        return True
        
    except Exception as e:
        print(f"❌ Error validating XML: {e}")
        return False


def launch_rekordbox(rekordbox_path: str, xml_path: Path) -> bool:
    """Attempt to launch Rekordbox with the test XML."""
    try:
        if not os.path.exists(rekordbox_path):
            print(f"❌ Rekordbox not found at {rekordbox_path}")
            return False
        
        print(f"🚀 Launching Rekordbox at {rekordbox_path}")
        
        # The command line args vary by Rekordbox version, this is a best guess
        # May need adjustment based on actual Rekordbox version
        if sys.platform == "darwin":  # macOS
            cmd = ["open", rekordbox_path]
            subprocess.Popen(cmd)
            print(f"✅ Rekordbox launched. Please manually import the XML file from:")
            print(f"   {xml_path}")
        else:  # Windows/Linux
            cmd = [rekordbox_path]
            subprocess.Popen(cmd)
            print(f"✅ Rekordbox launched. Please manually import the XML file from:")
            print(f"   {xml_path}")
        
        return True
    except Exception as e:
        print(f"❌ Error launching Rekordbox: {e}")
        return False


def verification_instructions(tracks, xml_path):
    """Print verification instructions for the user."""
    print("\n" + "="*80)
    print("REKORDBOX 7.x IMPORT VERIFICATION INSTRUCTIONS")
    print("="*80)
    print("\n1. Open Rekordbox 7.x")
    print("2. Click View > Show Browser in the top menu")
    print("3. In the browser sidebar, right-click on Playlists")
    print("4. Select Import Playlist")
    print("5. Choose rekordbox xml from the dropdown")
    print(f"6. Navigate to and select: {xml_path}")
    print("7. Verify the following:")
    print("   - A 'Deckdex' folder appears in the playlists section")
    print("   - The folder contains the following playlists:")
    print("     * Test Dance Playlist")
    print("     * Test Chill Playlist")
    print("     * Test Party Playlist")
    print("   - Each playlist contains the expected tracks")
    print("\nTrack list for reference:")
    for i, track in enumerate(tracks[:10]):
        print(f"  {i+1}. {track['artist']} - {track['title']}")
    
    print("\n4. Try playing the tracks (if using real files)")
    
    # Add instructions for checking Rekordbox's internal database
    rekordbox_data_dir = os.path.expanduser("~/Library/Pioneer/rekordbox")
    if os.path.exists(rekordbox_data_dir):
        print("\n5. Rekordbox data directory found at:")
        print(f"   {rekordbox_data_dir}")
        print("   After importing, check this directory to verify data was stored.")
        
        # Try to find the database file
        database_dir = os.path.join(rekordbox_data_dir, "database.v1")
        if os.path.exists(database_dir):
            db_files = [f for f in os.listdir(database_dir) if f.endswith('.edb')]
            if db_files:
                print(f"   Database files: {', '.join(db_files)}")
            
        # Check for master.db
        master_db = os.path.join(rekordbox_data_dir, "master.db")
        if os.path.exists(master_db):
            print(f"   Master database: {master_db}")
    else:
        print("\n5. Rekordbox data directory not found at the expected location.")
        print("   Expected: ~/Library/Pioneer/rekordbox")
    
    print("\nTest results:")
    print("  □ All playlists appeared correctly")
    print("  □ All tracks are present in the correct playlists")
    print("  □ Track metadata (artist, title) is displayed correctly")
    print("  □ Tracks can be played (if using real files)")
    print("  □ Data persisted in Rekordbox after restarting the application")
    print("\n" + "="*80)


def analyze_rekordbox_data():
    """Analyze the Rekordbox data directory for changes after import."""
    rekordbox_data_dir = os.path.expanduser("~/Library/Pioneer/rekordbox")
    
    if not os.path.exists(rekordbox_data_dir):
        print("❌ Rekordbox data directory not found.")
        return
    
    print(f"\n📂 Analyzing Rekordbox data directory: {rekordbox_data_dir}")
    
    # Look for database files
    database_dir = os.path.join(rekordbox_data_dir, "database.v1")
    if os.path.exists(database_dir):
        db_files = [f for f in os.listdir(database_dir) if f.endswith('.edb')]
        if db_files:
            print(f"📊 Database files found: {', '.join(db_files)}")
            
            # List files with timestamps and sizes for comparison
            print("\nDatabase file details (for before/after comparison):")
            for file in db_files:
                file_path = os.path.join(database_dir, file)
                size = os.path.getsize(file_path)
                mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                print(f"  - {file}: {size} bytes, modified {mtime.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Check for settings and logs that might contain import information
    settings_dir = os.path.join(rekordbox_data_dir, "settings")
    if os.path.exists(settings_dir):
        settings_files = os.listdir(settings_dir)
        print(f"\n⚙️ Settings files: {len(settings_files)} files found")
    
    # Look for playlist-specific files
    playlist_dirs = [
        os.path.join(rekordbox_data_dir, "playlists"),
        os.path.join(rekordbox_data_dir, "playlist")
    ]
    
    for playlist_dir in playlist_dirs:
        if os.path.exists(playlist_dir):
            print(f"\n🎵 Playlist directory found: {playlist_dir}")
            playlist_files = os.listdir(playlist_dir)
            print(f"   Contains {len(playlist_files)} files")
            for file in playlist_files[:5]:  # Show only first 5 to avoid clutter
                file_path = os.path.join(playlist_dir, file)
                size = os.path.getsize(file_path)
                mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                print(f"  - {file}: {size} bytes, modified {mtime.strftime('%Y-%m-%d %H:%M:%S')}")
            if len(playlist_files) > 5:
                print(f"  - ...and {len(playlist_files) - 5} more files")
    
    # Check for master.db
    master_db = os.path.join(rekordbox_data_dir, "master.db")
    if os.path.exists(master_db):
        size = os.path.getsize(master_db)
        mtime = datetime.fromtimestamp(os.path.getmtime(master_db))
        print(f"\n🔍 Master database: {size} bytes, modified {mtime.strftime('%Y-%m-%d %H:%M:%S')}")
    
    print("\n📋 Instructions for validation:")
    print("1. Note these file sizes and timestamps")
    print("2. Import the XML file into Rekordbox")
    print("3. Run this script again with --analyze-only to see changes")
    print("4. Compare before and after timestamps/sizes to identify modified files")


async def main():
    """Run the integration test."""
    parser = argparse.ArgumentParser(description="Test Rekordbox XML integration")
    parser.add_argument("--launch-rekordbox", action="store_true", 
                      help="Attempt to launch Rekordbox after creating the test XML")
    parser.add_argument("--rekordbox-path", type=str, 
                      help="Path to Rekordbox executable")
    parser.add_argument("--test-xml", type=str,
                      help="Path to save the test XML file")
    parser.add_argument("--use-real-files", action="store_true",
                      help="Use actual music files from config")
    parser.add_argument("--config", type=str,
                      help="Path to configuration file")
    parser.add_argument("--analyze-only", action="store_true",
                      help="Only analyze Rekordbox data directory, don't generate XML")
    
    args = parser.parse_args()
    
    # If analyze-only mode, just analyze the Rekordbox data directory
    if args.analyze_only:
        print("Analyzing Rekordbox data directory...")
        analyze_rekordbox_data()
        return
    
    # Determine output path for the XML
    if args.test_xml:
        xml_path = Path(args.test_xml)
    else:
        # Create in user's home directory by default
        xml_path = Path.home() / "deckdex_test.xml"
    
    # Determine config path
    config_path = None
    if args.config:
        config_path = Path(args.config)
    else:
        # Try standard locations
        for path in [
            Path('/Users/ravit/deckdex/config.yaml'),
            Path('/home/ravit/.config/deckdex/config.yml'),
            Path(__file__).parents[3] / 'config.yaml'
        ]:
            if path.exists():
                config_path = path
                break
    
    # Analyze Rekordbox data directory before import
    print("Analyzing Rekordbox data directory before import...")
    analyze_rekordbox_data()
    
    # Generate the test XML
    tracks = await generate_test_xml(
        xml_path, 
        use_real_files=args.use_real_files,
        config_path=config_path
    )
    
    # Launch Rekordbox if requested
    if args.launch_rekordbox:
        rekordbox_path = args.rekordbox_path or find_rekordbox()
        if rekordbox_path:
            launch_rekordbox(rekordbox_path, xml_path)
        else:
            print("❌ Rekordbox executable not found. Please specify with --rekordbox-path")
    
    # Print verification instructions
    verification_instructions(tracks, xml_path)
    
    print("\n⚠️ IMPORTANT: After importing in Rekordbox, run this script again with:")
    print(f"python {__file__} --analyze-only")
    print("This will help you confirm the data was stored in Rekordbox's database.")


if __name__ == "__main__":
    asyncio.run(main())