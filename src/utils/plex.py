import sqlite3
from pathlib import Path
import logging
from typing import Dict, List, Tuple
import shutil
from datetime import datetime

logger = logging.getLogger(__name__)

class PlexLibraryReader:
    """Handle reading data from Plex's SQLite database."""
    
    def __init__(self, plex_db_path: Path, music_dir: Path):
        self.plex_db_path = plex_db_path
        self.music_dir = music_dir
        self._verify_db()

    def _verify_db(self) -> None:
        """Verify Plex database exists and create a working copy."""
        if not self.plex_db_path.exists():
            raise FileNotFoundError(f"Plex database not found at {self.plex_db_path}")
            
        # Create a working copy to avoid corrupting the live database
        self.working_db = self.plex_db_path.parent / f"plex_working_copy_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        shutil.copy2(self.plex_db_path, self.working_db)
        logger.info(f"Created working copy of Plex database at {self.working_db}")

    def get_ratings(self) -> Dict[str, int]:
        """
        Get track ratings from Plex database.
        Returns a dictionary mapping file paths to ratings (1-5).
        """
        ratings = {}
        
        try:
            with sqlite3.connect(self.working_db) as conn:
                # Using the more comprehensive query from the forum
                cursor = conn.execute("""
                    SELECT 
                        metadata_items.title,
                        COALESCE(metadata_item_settings.rating, metadata_items.rating) as rating,
                        media_parts.file
                    FROM media_items
                    INNER JOIN metadata_items
                        ON media_items.metadata_item_id = metadata_items.id
                    LEFT JOIN metadata_item_settings
                        ON metadata_items.guid = metadata_item_settings.guid
                    LEFT JOIN media_parts
                        ON media_items.id = media_parts.media_item_id
                    WHERE (metadata_item_settings.rating IS NOT NULL 
                           OR metadata_items.rating IS NOT NULL)
                    AND metadata_items.metadata_type = '10'
                """)
                
                for title, rating, file_path in cursor:
                    if not file_path:
                        continue
                        
                    try:
                        # Convert absolute path to relative
                        rel_path = Path(file_path).relative_to(self.music_dir)
                        # Convert Plex's 0-10 rating to our 1-5 scale
                        normalized_rating = max(1, min(5, round(float(rating) / 2)))
                        ratings[str(rel_path)] = normalized_rating
                        logger.debug(f"Found rating {normalized_rating} for {title}")
                    except ValueError as e:
                        logger.warning(f"Skipping file outside music dir: {file_path}")
                    except TypeError as e:
                        logger.warning(f"Invalid rating value for {title}: {rating}")
                        
        except sqlite3.Error as e:
            logger.error(f"Error reading Plex database: {e}")
            raise
            
        return ratings

    def get_playlists(self) -> List[Tuple[str, List[str]]]:
        """
        Get playlists and their tracks from Plex.
        Returns list of (playlist_name, [track_paths]) tuples.
        """
        playlists = []
        
        try:
            with sqlite3.connect(self.working_db) as conn:
                # First get all music playlists
                playlist_cursor = conn.execute("""
                    SELECT id, name 
                    FROM metadata_items 
                    WHERE metadata_type = '15'  -- Playlist type
                """)
                
                for playlist_id, playlist_name in playlist_cursor:
                    # Get tracks for this playlist
                    track_cursor = conn.execute("""
                        SELECT mp.file
                        FROM playlist_items pi
                        JOIN metadata_items mi ON pi.metadata_item_id = mi.id
                        JOIN media_items mmi ON mi.id = mmi.metadata_item_id
                        JOIN media_parts mp ON mmi.id = mp.media_item_id
                        WHERE pi.playlist_id = ?
                        ORDER BY pi."order"
                    """, (playlist_id,))
                    
                    tracks = []
                    for (file_path,) in track_cursor:
                        try:
                            rel_path = Path(file_path).relative_to(self.music_dir)
                            tracks.append(str(rel_path))
                        except ValueError:
                            logger.warning(f"Skipping playlist track outside music dir: {file_path}")
                    
                    if tracks:  # Only add playlists that have valid tracks
                        playlists.append((playlist_name, tracks))
                        logger.info(f"Found playlist {playlist_name} with {len(tracks)} tracks")
                    
        except sqlite3.Error as e:
            logger.error(f"Error reading Plex playlists: {e}")
            raise
            
        return playlists

    def cleanup(self):
        """Remove the working copy of the database."""
        try:
            self.working_db.unlink()
            logger.info("Removed working copy of Plex database")
        except Exception as e:
            logger.warning(f"Failed to remove working database: {e}")