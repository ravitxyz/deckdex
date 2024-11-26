import pytest
from pathlib import Path
import sqlite3
import shutil
from unittest.mock import Mock, patch
from datetime import datetime

from deckdex.cli.import_library import import_library
from deckdex.models import MusicLibrary, TrackMetadata
from deckdex.file_processor import FileProcessor
from deckdex.utils.plex import PlexLibraryReader


@pytest.fixture
def temp_dirs(tmp_path):
    """Create temporary directories for testing."""
    music_dir = tmp_path / "music"
    export_dir = tmp_path / "export"
    db_dir = tmp_path / "db"

    for dir in [music_dir, export_dir, db_dir]:
        dir.mkdir()

    (music_dir / "test1.flac").write_text("dummy flac")
    (music_dir / "test2.mp3").write_text("dummy mp3")
    (music_dir / "subfolder").mkdir()
    (music_dir / "subfolder" / "test3.aiff").write_text("dummy aiff")


    return {
        "music_dir": music_dir,
        "export_dir": export_dir,
        "db_path": db_dir / "library.db"
    }


@pytest.fixture
def mock_plex_db(tmp_path):
    """Create a mock Plex database for testing."""
    db_path = tmp_path / "mock_plex.db"
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create minimal schema needed for testing
    cursor.executescript("""
        CREATE TABLE metadata_items (
            id INTEGER PRIMARY KEY,
            title TEXT,
            rating REAL,
            metadata_type TEXT,
            guid TEXT
        );
        
        CREATE TABLE metadata_item_settings (
            guid TEXT,
            rating REAL
        );
        
        CREATE TABLE media_items (
            id INTEGER PRIMARY KEY,
            metadata_item_id INTEGER
        );
        
        CREATE TABLE media_parts (
            id INTEGER PRIMARY KEY,
            media_item_id INTEGER,
            file TEXT
        );
    """)
    
    # Insert some test data
    cursor.executescript("""
        INSERT INTO metadata_items (id, title, rating, metadata_type, guid)
        VALUES 
            (1, 'Test Track 1', 8.0, '10', 'track1guid'),
            (2, 'Test Track 2', NULL, '10', 'track2guid');
            
        INSERT INTO metadata_item_settings (guid, rating)
        VALUES ('track2guid', 6.0);
        
        INSERT INTO media_items (id, metadata_item_id)
        VALUES (1, 1), (2, 2);
        
        INSERT INTO media_parts (id, media_item_id, file)
        VALUES 
            (1, 1, 'test1.flac'),
            (2, 2, 'test2.mp3');
    """)
    
    conn.commit()
    conn.close()
    
    return db_path

def test_basic_import(temp_dirs):
    """Test basic library import without Plex integration."""
    runner = CliRunner()
    result = runner.invoke(import_library, [
        str(temp_dirs["music_dir"]),
        str(temp_dirs["db_path"]),
        str(temp_dirs["export_dir"]),
        "--skip-plex"
    ])
    
    assert result.exit_code == 0
    
    # Verify database was created and contains expected tracks
    library = MusicLibrary(temp_dirs["db_path"], temp_dirs["music_dir"], temp_dirs["export_dir"])
    tracks = library.get_all_tracks()
    assert len(tracks) == 3  # Should find all test files
    
    # Verify log file was created
    log_file = Path.home() / 'dj_library_import.log'
    assert log_file.exists()

def test_plex_integration(temp_dirs, mock_plex_db):
    """Test library import with Plex ratings."""
    with patch('dj_library.cli.import_library.PLEX_DB_PATH', mock_plex_db):
        runner = CliRunner()
        result = runner.invoke(import_library, [
            str(temp_dirs["music_dir"]),
            str(temp_dirs["db_path"]),
            str(temp_dirs["export_dir"])
        ])
        
        assert result.exit_code == 0
        
        # Verify Plex ratings were imported
        library = MusicLibrary(temp_dirs["db_path"], temp_dirs["music_dir"], temp_dirs["export_dir"])
        tracks = library.get_all_tracks()
        
        track1 = library.get_track_by_path(Path("test1.flac"))
        track2 = library.get_track_by_path(Path("test2.mp3"))
        
        assert track1.rating == 4  # 8.0 / 2 rounded to nearest integer
        assert track2.rating == 3  # 6.0 / 2 rounded to nearest integer

def test_dry_run(temp_dirs):
    """Test dry run mode doesn't modify anything."""
    runner = CliRunner()
    result = runner.invoke(import_library, [
        str(temp_dirs["music_dir"]),
        str(temp_dirs["db_path"]),
        str(temp_dirs["export_dir"]),
        "--dry-run"
    ])
    
    assert result.exit_code == 0
    assert not temp_dirs["db_path"].exists()  # Database shouldn't be created in dry run


def test_error_handling(temp_dirs):
    """Test handling of various error conditions."""
    # Test with non-existent music directory
    runner = CliRunner()
    result = runner.invoke(import_library, [
        str(temp_dirs["music_dir"] / "nonexistent"),
        str(temp_dirs["db_path"]),
        str(temp_dirs["export_dir"])
    ])
    assert result.exit_code != 0
    
    # Test with invalid Plex database
    with patch('dj_library.cli.import_library.PLEX_DB_PATH', temp_dirs["music_dir"] / "invalid.db"):
        result = runner.invoke(import_library, [
            str(temp_dirs["music_dir"]),
            str(temp_dirs["db_path"]),
            str(temp_dirs["export_dir"])
        ])
        assert result.exit_code == 0  # Should continue without Plex data
