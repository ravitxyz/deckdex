"""Main playlist service for managing playlists across platforms."""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import aiosqlite

from deckdex.identifier.service import TrackIdentifierService
from deckdex.playlist.models import (Playlist, PlaylistItem, PlaylistSource,
                                     PlaylistSyncStatus, SyncHistoryEntry, SyncStatus)

logger = logging.getLogger(__name__)


class PlaylistService:
    """Service for managing playlists across different platforms."""

    def __init__(self, db_path: Path, track_identifier_service: TrackIdentifierService = None):
        """Initialize the playlist service.
        
        Args:
            db_path: Path to the SQLite database
            track_identifier_service: Optional service for resolving track identifiers
        """
        self.db_path = db_path
        self.track_identifier_service = track_identifier_service

    async def initialize(self) -> None:
        """Initialize the database schema."""
        async with aiosqlite.connect(self.db_path) as db:
            # Create playlists table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS playlists (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    source TEXT NOT NULL,
                    external_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    version INTEGER DEFAULT 1,
                    is_active BOOLEAN DEFAULT 1
                )
            """)
            
            # Create playlist items table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS playlist_items (
                    playlist_id TEXT,
                    track_id TEXT,
                    position INTEGER,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    external_id TEXT,
                    PRIMARY KEY (playlist_id, track_id),
                    FOREIGN KEY (playlist_id) REFERENCES playlists(id)
                )
            """)
            
            # Create sync status table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS playlist_sync (
                    playlist_id TEXT PRIMARY KEY,
                    last_plex_sync TIMESTAMP,
                    last_rekordbox_sync TIMESTAMP,
                    plex_version INTEGER DEFAULT 0,
                    rekordbox_version INTEGER DEFAULT 0,
                    sync_status TEXT DEFAULT 'pending',
                    FOREIGN KEY (playlist_id) REFERENCES playlists(id)
                )
            """)
            
            # Create sync history table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS playlist_sync_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    playlist_id TEXT,
                    sync_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    source TEXT NOT NULL,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    details TEXT,
                    FOREIGN KEY (playlist_id) REFERENCES playlists(id)
                )
            """)
            
            # Create indexes for better performance
            await db.execute("CREATE INDEX IF NOT EXISTS idx_playlist_items_track ON playlist_items(track_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_playlists_source ON playlists(source)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_playlists_external_id ON playlists(external_id)")
            
            await db.commit()
            logger.info("Playlist database schema initialized")

    async def create_playlist(self, playlist: Playlist) -> str:
        """Create a new playlist.
        
        Args:
            playlist: The playlist to create
            
        Returns:
            The playlist ID
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO playlists
                (id, name, description, source, external_id, created_at, modified_at, version, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                playlist.id,
                playlist.name,
                playlist.description,
                playlist.source.value,
                playlist.external_id,
                playlist.created_at.isoformat(),
                playlist.modified_at.isoformat(),
                playlist.version,
                1 if playlist.is_active else 0
            ))
            
            # Insert playlist items if any
            for item in playlist.items:
                await db.execute("""
                    INSERT INTO playlist_items
                    (playlist_id, track_id, position, added_at, external_id)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    playlist.id,
                    item.track_id,
                    item.position,
                    item.added_at.isoformat(),
                    item.external_id
                ))
            
            # Initialize sync status
            await db.execute("""
                INSERT INTO playlist_sync
                (playlist_id, sync_status)
                VALUES (?, ?)
            """, (
                playlist.id,
                SyncStatus.PENDING.value
            ))
            
            await db.commit()
            logger.info(f"Created playlist: {playlist.name} (ID: {playlist.id})")
            
            # Record in sync history
            await self._add_sync_history(
                playlist.id,
                playlist.source,
                'create',
                'success',
                f"Created playlist with {len(playlist.items)} tracks"
            )
            
            return playlist.id

    async def update_playlist(self, playlist: Playlist) -> bool:
        """Update an existing playlist.
        
        Args:
            playlist: The updated playlist
            
        Returns:
            True if successful, False otherwise
        """
        async with aiosqlite.connect(self.db_path) as db:
            # Check if playlist exists
            async with db.execute("SELECT id FROM playlists WHERE id = ?", (playlist.id,)) as cursor:
                if not await cursor.fetchone():
                    logger.error(f"Playlist not found: {playlist.id}")
                    return False
            
            # Update playlist
            await db.execute("""
                UPDATE playlists
                SET name = ?, description = ?, source = ?, external_id = ?,
                    modified_at = ?, version = version + 1, is_active = ?
                WHERE id = ?
            """, (
                playlist.name,
                playlist.description,
                playlist.source.value,
                playlist.external_id,
                datetime.now().isoformat(),
                1 if playlist.is_active else 0,
                playlist.id
            ))
            
            # Delete existing items
            await db.execute("DELETE FROM playlist_items WHERE playlist_id = ?", (playlist.id,))
            
            # Insert updated items
            for item in playlist.items:
                await db.execute("""
                    INSERT INTO playlist_items
                    (playlist_id, track_id, position, added_at, external_id)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    playlist.id,
                    item.track_id,
                    item.position,
                    item.added_at.isoformat(),
                    item.external_id
                ))
            
            await db.commit()
            logger.info(f"Updated playlist: {playlist.name} (ID: {playlist.id})")
            
            # Record in sync history
            await self._add_sync_history(
                playlist.id,
                playlist.source,
                'update',
                'success',
                f"Updated playlist with {len(playlist.items)} tracks"
            )
            
            return True

    async def delete_playlist(self, playlist_id: str) -> bool:
        """Delete a playlist.
        
        Args:
            playlist_id: ID of the playlist to delete
            
        Returns:
            True if successful, False otherwise
        """
        async with aiosqlite.connect(self.db_path) as db:
            # Get playlist details for history
            async with db.execute(
                "SELECT name, source FROM playlists WHERE id = ?", 
                (playlist_id,)
            ) as cursor:
                result = await cursor.fetchone()
                if not result:
                    logger.error(f"Playlist not found: {playlist_id}")
                    return False
                
                name, source = result
            
            # Soft delete by marking as inactive
            await db.execute("""
                UPDATE playlists
                SET is_active = 0, modified_at = ?
                WHERE id = ?
            """, (
                datetime.now().isoformat(),
                playlist_id
            ))
            
            await db.commit()
            logger.info(f"Deleted playlist: {name} (ID: {playlist_id})")
            
            # Record in sync history
            await self._add_sync_history(
                playlist_id,
                PlaylistSource(source),
                'delete',
                'success',
                f"Deleted playlist: {name}"
            )
            
            return True

    async def get_playlist(self, playlist_id: str) -> Optional[Playlist]:
        """Get a playlist by ID.
        
        Args:
            playlist_id: ID of the playlist to retrieve
            
        Returns:
            The playlist if found, None otherwise
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = sqlite3.Row
            
            # Get playlist
            async with db.execute("""
                SELECT * FROM playlists
                WHERE id = ? AND is_active = 1
            """, (playlist_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                
                playlist = Playlist(
                    id=row['id'],
                    name=row['name'],
                    description=row['description'],
                    source=PlaylistSource(row['source']),
                    external_id=row['external_id'],
                    created_at=datetime.fromisoformat(row['created_at']),
                    modified_at=datetime.fromisoformat(row['modified_at']),
                    version=row['version'],
                    is_active=bool(row['is_active'])
                )
                
                # Get playlist items
                async with db.execute("""
                    SELECT * FROM playlist_items
                    WHERE playlist_id = ?
                    ORDER BY position
                """, (playlist_id,)) as items_cursor:
                    items = []
                    async for item_row in items_cursor:
                        items.append(PlaylistItem(
                            playlist_id=item_row['playlist_id'],
                            track_id=item_row['track_id'],
                            position=item_row['position'],
                            added_at=datetime.fromisoformat(item_row['added_at']),
                            external_id=item_row['external_id']
                        ))
                    
                    playlist.items = items
                
                return playlist

    async def get_playlists_by_source(self, source: PlaylistSource) -> List[Playlist]:
        """Get all playlists from a specific source.
        
        Args:
            source: The source of the playlists
            
        Returns:
            List of playlists
        """
        playlists = []
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = sqlite3.Row
            
            # Get playlists
            async with db.execute("""
                SELECT id FROM playlists
                WHERE source = ? AND is_active = 1
            """, (source.value,)) as cursor:
                async for row in cursor:
                    playlist = await self.get_playlist(row['id'])
                    if playlist:
                        playlists.append(playlist)
            
            return playlists

    async def get_playlist_by_external_id(self, source: PlaylistSource, external_id: str) -> Optional[Playlist]:
        """Get a playlist by its external ID and source.
        
        Args:
            source: The source of the playlist
            external_id: External ID from the source system
            
        Returns:
            The playlist if found, None otherwise
        """
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT id FROM playlists
                WHERE source = ? AND external_id = ? AND is_active = 1
            """, (source.value, external_id)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                
                return await self.get_playlist(row[0])

    async def update_sync_status(
        self, 
        playlist_id: str, 
        source: PlaylistSource, 
        status: SyncStatus,
        version: Optional[int] = None
    ) -> bool:
        """Update the sync status for a playlist.
        
        Args:
            playlist_id: ID of the playlist
            source: Source being updated
            status: New sync status
            version: Optional version number to update
            
        Returns:
            True if successful, False otherwise
        """
        async with aiosqlite.connect(self.db_path) as db:
            # Check if playlist exists
            async with db.execute("SELECT id FROM playlists WHERE id = ?", (playlist_id,)) as cursor:
                if not await cursor.fetchone():
                    logger.error(f"Playlist not found: {playlist_id}")
                    return False
            
            # Determine which timestamp and version to update
            now = datetime.now().isoformat()
            if source == PlaylistSource.PLEX:
                if version:
                    await db.execute("""
                        UPDATE playlist_sync
                        SET last_plex_sync = ?, sync_status = ?, plex_version = ?
                        WHERE playlist_id = ?
                    """, (now, status.value, version, playlist_id))
                else:
                    await db.execute("""
                        UPDATE playlist_sync
                        SET last_plex_sync = ?, sync_status = ?
                        WHERE playlist_id = ?
                    """, (now, status.value, playlist_id))
            else:
                if version:
                    await db.execute("""
                        UPDATE playlist_sync
                        SET last_rekordbox_sync = ?, sync_status = ?, rekordbox_version = ?
                        WHERE playlist_id = ?
                    """, (now, status.value, version, playlist_id))
                else:
                    await db.execute("""
                        UPDATE playlist_sync
                        SET last_rekordbox_sync = ?, sync_status = ?
                        WHERE playlist_id = ?
                    """, (now, status.value, playlist_id))
            
            await db.commit()
            logger.info(f"Updated sync status for playlist {playlist_id}: {status.value}")
            return True

    async def get_sync_status(self, playlist_id: str) -> Optional[PlaylistSyncStatus]:
        """Get the sync status for a playlist.
        
        Args:
            playlist_id: ID of the playlist
            
        Returns:
            The sync status if found, None otherwise
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = sqlite3.Row
            
            async with db.execute("""
                SELECT * FROM playlist_sync
                WHERE playlist_id = ?
            """, (playlist_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                
                return PlaylistSyncStatus(
                    playlist_id=row['playlist_id'],
                    last_plex_sync=datetime.fromisoformat(row['last_plex_sync']) if row['last_plex_sync'] else None,
                    last_rekordbox_sync=datetime.fromisoformat(row['last_rekordbox_sync']) if row['last_rekordbox_sync'] else None,
                    plex_version=row['plex_version'],
                    rekordbox_version=row['rekordbox_version'],
                    sync_status=SyncStatus(row['sync_status'])
                )

    async def get_playlists_needing_sync(self, source: PlaylistSource = None) -> List[Tuple[str, PlaylistSyncStatus]]:
        """Get playlists that need synchronization.
        
        Args:
            source: Optional source to filter by
            
        Returns:
            List of (playlist_id, sync_status) tuples
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = sqlite3.Row
            
            if source:
                # If source is specified, get playlists that haven't been synced to that source
                if source == PlaylistSource.PLEX:
                    query = """
                        SELECT p.id, ps.*
                        FROM playlists p
                        JOIN playlist_sync ps ON p.id = ps.playlist_id
                        WHERE p.is_active = 1
                        AND (
                            ps.last_plex_sync IS NULL OR
                            ps.sync_status = ? OR
                            datetime(p.modified_at) > datetime(ps.last_plex_sync)
                        )
                    """
                else:
                    query = """
                        SELECT p.id, ps.*
                        FROM playlists p
                        JOIN playlist_sync ps ON p.id = ps.playlist_id
                        WHERE p.is_active = 1
                        AND (
                            ps.last_rekordbox_sync IS NULL OR
                            ps.sync_status = ? OR
                            datetime(p.modified_at) > datetime(ps.last_rekordbox_sync)
                        )
                    """
                
                params = (SyncStatus.PENDING.value,)
            else:
                # Get all playlists with pending or conflict status
                query = """
                    SELECT p.id, ps.*
                    FROM playlists p
                    JOIN playlist_sync ps ON p.id = ps.playlist_id
                    WHERE p.is_active = 1
                    AND (
                        ps.sync_status = ? OR
                        ps.sync_status = ?
                    )
                """
                params = (SyncStatus.PENDING.value, SyncStatus.CONFLICT.value)
            
            results = []
            async with db.execute(query, params) as cursor:
                async for row in cursor:
                    sync_status = PlaylistSyncStatus(
                        playlist_id=row['playlist_id'],
                        last_plex_sync=datetime.fromisoformat(row['last_plex_sync']) if row['last_plex_sync'] else None,
                        last_rekordbox_sync=datetime.fromisoformat(row['last_rekordbox_sync']) if row['last_rekordbox_sync'] else None,
                        plex_version=row['plex_version'],
                        rekordbox_version=row['rekordbox_version'],
                        sync_status=SyncStatus(row['sync_status'])
                    )
                    results.append((row['id'], sync_status))
            
            return results

    async def _add_sync_history(
        self,
        playlist_id: str,
        source: PlaylistSource,
        action: str,
        status: str,
        details: Optional[str] = None
    ) -> int:
        """Add an entry to the sync history.
        
        Args:
            playlist_id: ID of the playlist
            source: Source of the sync operation
            action: Action performed
            status: Status of the operation
            details: Optional details
            
        Returns:
            ID of the history entry
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO playlist_sync_history
                (playlist_id, sync_time, source, action, status, details)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                playlist_id,
                datetime.now().isoformat(),
                source.value,
                action,
                status,
                details
            ))
            await db.commit()
            return cursor.lastrowid

    async def get_sync_history(self, playlist_id: str) -> List[SyncHistoryEntry]:
        """Get sync history for a playlist.
        
        Args:
            playlist_id: ID of the playlist
            
        Returns:
            List of sync history entries
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = sqlite3.Row
            
            history = []
            async with db.execute("""
                SELECT * FROM playlist_sync_history
                WHERE playlist_id = ?
                ORDER BY sync_time DESC
            """, (playlist_id,)) as cursor:
                async for row in cursor:
                    history.append(SyncHistoryEntry(
                        id=row['id'],
                        playlist_id=row['playlist_id'],
                        sync_time=datetime.fromisoformat(row['sync_time']),
                        source=PlaylistSource(row['source']),
                        action=row['action'],
                        status=row['status'],
                        details=row['details']
                    ))
            
            return history