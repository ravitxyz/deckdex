import sqlite3
from pathlib import Path
import logging
from typing import Dict, List, Tuple, Optional
import shutil
from datetime import datetime
import os

logger = logging.getLogger(__name__)

class PlexLibraryReader:
    """Handle reading data from Plex's SQLite database."""
    
    def __init__(self, plex_db_path: Path, music_dir: Path):
        self.plex_db_path = Path(plex_db_path)
        self.music_dir = Path(music_dir)
        self._verify_db()

    def _verify_db(self) -> None:
        """Verify Plex database exists and is readable."""
        if not self.plex_db_path.exists():
            raise FileNotFoundError(f"Plex database not found at {self.plex_db_path}")
        
        if not self.plex_db_path.is_file():
            raise ValueError(f"Plex database path is not a file: {self.plex_db_path}")
            
        # Test database connection with improved WAL mode handling
        try:
            with sqlite3.connect(f"file:{self.plex_db_path}?mode=ro", uri=True) as conn:
                # Set WAL journal mode and other pragmas for better concurrent access
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA synchronous=NORMAL;")
                conn.execute("PRAGMA locking_mode=NORMAL;")
                conn.execute("PRAGMA busy_timeout=10000;")  # Wait up to 10 seconds if DB is locked
                
                # Test query
                conn.execute("SELECT 1 FROM metadata_items LIMIT 1")
                logger.info(f"Successfully connected to Plex database at {self.plex_db_path}")
        except sqlite3.Error as e:
            logger.error(f"Cannot access Plex database: {e}")
            raise

    def get_recent_rating_changes(self, since_timestamp: float) -> Dict[str, float]:
        """Get tracks with rating changes since the given timestamp."""
        changes = {}
        
        try:
            # Connect in read-only mode with improved WAL mode handling
            with sqlite3.connect(f"file:{self.plex_db_path}?mode=ro", uri=True) as conn:
                # Configure connection for better concurrent access
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA synchronous=NORMAL;")
                conn.execute("PRAGMA locking_mode=NORMAL;")
                conn.execute("PRAGMA busy_timeout=10000;")
                conn.row_factory = sqlite3.Row
                
                # Query both metadata_items and metadata_item_settings for rating changes
                cursor = conn.execute("""
                    SELECT 
                        mp.file as file_path,
                        COALESCE(mis.rating, mi.rating) as rating,
                        COALESCE(mis.updated_at, mi.updated_at) as updated_at
                    FROM metadata_items mi
                    JOIN media_items mmi ON mi.id = mmi.metadata_item_id
                    JOIN media_parts mp ON mmi.id = mp.media_item_id
                    LEFT JOIN metadata_item_settings mis ON mi.guid = mis.guid
                    WHERE (
                        (mis.updated_at > ? AND mis.rating IS NOT NULL)
                        OR 
                        (mi.updated_at > ? AND mi.rating IS NOT NULL)
                    )
                    AND mi.metadata_type = 10  -- Type 10 is for music tracks
                """, (since_timestamp, since_timestamp))
                
                for row in cursor:
                    try:
                        file_path = Path(row['file_path'])
                        if not file_path.exists():
                            continue
                            
                        rel_path = file_path.relative_to(self.music_dir)
                        rating = float(row['rating'])
                        
                        # Convert Plex's 0-10 rating to 1-5 scale
                        normalized_rating = max(1, min(5, round(rating / 2)))
                        changes[str(rel_path)] = normalized_rating
                        
                        logger.debug(f"Found rating change: {rel_path} -> {normalized_rating}")
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Error processing rating change for {row['file_path']}: {e}")
                        continue
            
            if changes:
                logger.info(f"Found {len(changes)} tracks with rating changes")
            
            return changes
            
        except sqlite3.Error as e:
            logger.error(f"Error reading Plex database: {e}")
            raise
    def get_track_rating(self, file_path: Path) -> Optional[float]:
        """Get rating for a specific track from Plex database."""
        try:
            with sqlite3.connect(f"file:{self.plex_db_path}?mode=ro", uri=True) as conn:
                # Configure connection for better concurrent access
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA synchronous=NORMAL;")
                conn.execute("PRAGMA locking_mode=NORMAL;")
                conn.execute("PRAGMA busy_timeout=10000;")
                
                cursor = conn.execute("""
                    SELECT 
                        COALESCE(mis.rating, mi.rating) as rating
                    FROM metadata_items mi
                    JOIN media_items mmi ON mi.id = mmi.metadata_item_id
                    JOIN media_parts mp ON mmi.id = mp.media_item_id
                    LEFT JOIN metadata_item_settings mis ON mi.guid = mis.guid
                    WHERE mp.file = ?
                    AND mi.metadata_type = 10  -- Type 10 is for music tracks
                    LIMIT 1
                """, (str(file_path),))
                
                row = cursor.fetchone()
                if row and row[0] is not None:
                    rating = float(row[0])
                    # Return the raw Plex 0-10 rating as that's what the LibraryMonitor expects
                    return rating
                return None
                
        except (sqlite3.Error, ValueError, TypeError) as e:
            logger.error(f"Error getting track rating for {file_path}: {e}")
            return None

    def get_ratings(self) -> Dict[str, float]:
        """Get all track ratings from Plex database."""
        return self.get_recent_rating_changes(0)  # Get all ratings by using 0 timestamp

    def get_eligible_tracks(self) -> Dict[str, float]:
        """Get all tracks that meet the DJ library rating threshold."""
        try:
            with sqlite3.connect(f"file:{self.plex_db_path}?mode=ro", uri=True) as conn:
                # Configure connection for better concurrent access
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA synchronous=NORMAL;")
                conn.execute("PRAGMA locking_mode=NORMAL;")
                conn.execute("PRAGMA busy_timeout=10000;")
                
                cursor = conn.execute("""
                    SELECT 
                        mp.file as file_path,
                        COALESCE(mis.rating, mi.rating) as rating
                    FROM metadata_items mi
                    JOIN media_items mmi ON mi.id = mmi.metadata_item_id
                    JOIN media_parts mp ON mmi.id = mp.media_item_id
                    LEFT JOIN metadata_item_settings mis ON mi.guid = mis.guid
                    WHERE COALESCE(mis.rating, mi.rating) IS NOT NULL
                    AND mi.metadata_type = 10  -- Type 10 is for music tracks
                """)
                
                eligible_tracks = {}
                for row in cursor:
                    try:
                        # Get absolute path to the file from Plex DB
                        abs_file_path = Path(row[0]).resolve()
                        if not abs_file_path.exists():
                            logger.warning(f"Plex track not found at {abs_file_path}")
                            continue
                        
                        # Resolve music_dir to absolute path for comparison
                        abs_music_dir = Path(self.music_dir).resolve()
                        
                        # Get relative path from music directory
                        try:
                            rel_path = abs_file_path.relative_to(abs_music_dir)
                            rating = float(row[1])
                            normalized_rating = max(1, min(5, round(rating / 2)))
                            
                            # Store as string for consistent handling
                            eligible_tracks[str(rel_path)] = normalized_rating
                            logger.debug(f"Added eligible track: {rel_path} (Rating: {normalized_rating})")
                        except ValueError:
                            # If file is not under music_dir, log warning
                            logger.warning(f"File {abs_file_path} is not within music directory {abs_music_dir}")
                    except (ValueError, TypeError) as e:
                        logger.error(f"Error processing row from Plex DB: {e}")
                        
                return eligible_tracks
                
        except sqlite3.Error as e:
            self.logger.error(f"Error reading Plex database: {e}")
            raise