import json
import sqlite3
from pathlib import Path
from typing import Dict, Any, Optional
import aiosqlite
import logging

logger = logging.getLogger(__name__)

class MetadataCache:
    """Cache for storing track metadata to avoid repeated API calls."""
    
    def __init__(self, cache_path: Optional[Path] = None):
        """
        Initialize the metadata cache.
        
        Args:
            cache_path: Path to the SQLite database file.
                       If None, uses in-memory database.
        """
        self.db_path = cache_path or ":memory:"
        self._init_db()
    
    def _init_db(self):
        """Initialize the SQLite database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS metadata_cache (
                    cache_key TEXT PRIMARY KEY,
                    metadata TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Index for faster lookups
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp 
                ON metadata_cache(timestamp)
            """)
    
    async def get(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve metadata from cache.
        
        Args:
            cache_key: Unique identifier for the cached metadata
            
        Returns:
            Cached metadata dictionary or None if not found
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    """
                    SELECT metadata 
                    FROM metadata_cache 
                    WHERE cache_key = ?
                    """,
                    (cache_key,)
                ) as cursor:
                    if row := await cursor.fetchone():
                        return json.loads(row[0])
            return None
        except Exception as e:
            logger.error(f"Error retrieving from cache: {e}")
            return None
    
    async def set(
        self,
        cache_key: str,
        metadata: Dict[str, Any],
        expire_days: int = 30
    ) -> None:
        """
        Store metadata in cache.
        
        Args:
            cache_key: Unique identifier for the metadata
            metadata: Dictionary of metadata to cache
            expire_days: Number of days after which to expire the cache
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """
                    INSERT OR REPLACE INTO metadata_cache 
                    (cache_key, metadata) 
                    VALUES (?, ?)
                    """,
                    (cache_key, json.dumps(metadata))
                )
                await db.commit()
                
                # Clean up old entries
                await db.execute(
                    """
                    DELETE FROM metadata_cache 
                    WHERE timestamp < datetime('now', ?)
                    """,
                    (f'-{expire_days} days',)
                )
                await db.commit()
        except Exception as e:
            logger.error(f"Error writing to cache: {e}")
    
    async def clear(self) -> None:
        """Clear all cached metadata."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("DELETE FROM metadata_cache")
                await db.commit()
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
