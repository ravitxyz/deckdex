"""Playlist synchronization logic.

This module handles the synchronization between different playlist sources
(e.g., Plex and Rekordbox).
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set

from ..utils.plex import PlexLibraryReader, PlexPlaylist
from .models import Playlist, PlaylistItem, PlaylistSource, SyncStatus
from .service import PlaylistService
from .rekordbox import RekordboxXML
from ..identifier.service import TrackIdentifierService

logger = logging.getLogger(__name__)


class PlaylistSyncService:
    """Service for synchronizing playlists between different sources."""

    def __init__(
        self,
        playlist_service: PlaylistService,
        track_identifier: TrackIdentifierService,
        plex_reader: Optional[PlexLibraryReader] = None,
        rekordbox_xml: Optional[RekordboxXML] = None,
        rekordbox_xml_path: Optional[Path] = None,
    ):
        """Initialize the playlist sync service.
        
        Args:
            playlist_service: PlaylistService instance for playlist operations
            track_identifier: TrackIdentifierService for track identification
            plex_reader: Optional PlexLibraryReader instance
            rekordbox_xml: Optional RekordboxXML instance
            rekordbox_xml_path: Optional path to Rekordbox XML file
        """
        self.playlist_service = playlist_service
        self.track_identifier = track_identifier
        self.plex_reader = plex_reader
        self.rekordbox_xml = rekordbox_xml or RekordboxXML(track_identifier)
        self.rekordbox_xml_path = rekordbox_xml_path

    async def sync_from_plex(self) -> Tuple[int, int, int]:
        """Synchronize playlists from Plex to the database.
        
        Returns:
            Tuple of (added, updated, failed) counts
        """
        if not self.plex_reader:
            raise ValueError("Plex reader is not configured")
        
        logger.info("Starting synchronization from Plex")
        
        # Get all playlists from Plex
        plex_playlists = await self.plex_reader.get_playlists()
        if not plex_playlists:
            logger.info("No playlists found in Plex")
            return 0, 0, 0
        
        logger.info(f"Found {len(plex_playlists)} playlists in Plex")
        
        # Get existing playlists from database
        db_playlists = await self.playlist_service.get_playlists_by_source(PlaylistSource.PLEX)
        
        # Create a lookup dictionary for existing playlists
        db_playlist_map = {p.external_id: p for p in db_playlists if p.external_id}
        
        # Process each Plex playlist
        added_count = 0
        updated_count = 0
        failed_count = 0
        
        from .plex import PlexPlaylistAdapter
        adapter = PlexPlaylistAdapter(self.plex_reader, self.track_identifier)
        
        for plex_playlist in plex_playlists:
            try:
                # Convert Plex playlist to internal format
                playlist = await adapter._convert_playlist(plex_playlist)
                
                # Check if playlist already exists
                if playlist.external_id in db_playlist_map:
                    existing = db_playlist_map[playlist.external_id]
                    # Check if update is needed
                    if self._playlist_needs_update(existing, playlist):
                        # Copy ID from existing playlist
                        playlist.id = existing.id
                        # Update playlist items with correct playlist ID
                        for item in playlist.items:
                            item.playlist_id = playlist.id
                        # Update in database
                        if await self.playlist_service.update_playlist(playlist):
                            # Update sync status
                            await self.playlist_service.update_sync_status(
                                playlist.id, 
                                PlaylistSource.PLEX,
                                SyncStatus.SYNCED,
                                version=playlist.version
                            )
                            updated_count += 1
                            logger.info(f"Updated playlist from Plex: {playlist.name}")
                        else:
                            failed_count += 1
                            logger.error(f"Failed to update playlist: {playlist.name}")
                else:
                    # Create new playlist
                    playlist_id = await self.playlist_service.create_playlist(playlist)
                    if playlist_id:
                        added_count += 1
                        logger.info(f"Added new playlist from Plex: {playlist.name}")
                    else:
                        failed_count += 1
                        logger.error(f"Failed to add playlist: {playlist.name}")
            except Exception as e:
                failed_count += 1
                logger.error(f"Error processing Plex playlist {plex_playlist.title}: {e}")
        
        logger.info(f"Plex sync complete: {added_count} added, {updated_count} updated, {failed_count} failed")
        return added_count, updated_count, failed_count

    async def sync_to_rekordbox(self, output_path: Optional[Path] = None) -> bool:
        """Synchronize playlists from database to Rekordbox XML.
        
        Args:
            output_path: Optional path to save the XML file
                        (defaults to self.rekordbox_xml_path)
        
        Returns:
            True if successful, False otherwise
        """
        if not self.rekordbox_xml:
            raise ValueError("Rekordbox XML handler is not configured")
        
        # Use provided path or default
        xml_path = output_path or self.rekordbox_xml_path
        if not xml_path:
            raise ValueError("No output path specified for Rekordbox XML")
        
        logger.info(f"Starting synchronization to Rekordbox XML at {xml_path}")
        
        # Get all playlists that need to be synced to Rekordbox
        pending_syncs = await self.playlist_service.get_playlists_needing_sync(
            PlaylistSource.REKORDBOX
        )
        
        # Get all Plex playlists
        plex_playlists = await self.playlist_service.get_playlists_by_source(
            PlaylistSource.PLEX
        )
        
        # Filter playlists that need to be synced
        to_sync_ids = {playlist_id for playlist_id, _ in pending_syncs}
        playlists_to_sync = [p for p in plex_playlists if p.id in to_sync_ids]
        
        logger.info(f"Found {len(playlists_to_sync)} playlists to sync to Rekordbox")
        
        # Check if we should merge with existing file
        merge_with_existing = os.path.exists(xml_path) if xml_path else False
        
        # Generate and save XML
        result = await self.rekordbox_xml.generate_xml(
            playlists_to_sync,
            xml_path,
            merge_with_existing,
            xml_path if merge_with_existing else None
        )
        
        if result:
            # Update sync status for all successfully synced playlists
            for playlist in playlists_to_sync:
                await self.playlist_service.update_sync_status(
                    playlist.id,
                    PlaylistSource.REKORDBOX,
                    SyncStatus.SYNCED,
                    version=playlist.version
                )
            logger.info(f"Successfully synced {len(playlists_to_sync)} playlists to Rekordbox")
            return True
        else:
            logger.error("Failed to sync playlists to Rekordbox")
            return False

    async def sync_from_rekordbox(self, xml_path: Optional[Path] = None) -> Tuple[int, int, int]:
        """Synchronize playlists from Rekordbox XML to the database.
        
        Args:
            xml_path: Optional path to the XML file (defaults to self.rekordbox_xml_path)
            
        Returns:
            Tuple of (added, updated, failed) counts
        """
        if not self.rekordbox_xml:
            raise ValueError("Rekordbox XML handler is not configured")
        
        # Use provided path or default
        xml_path = xml_path or self.rekordbox_xml_path
        if not xml_path or not xml_path.exists():
            raise ValueError(f"Rekordbox XML file not found: {xml_path}")
        
        logger.info(f"Starting synchronization from Rekordbox XML: {xml_path}")
        
        # Read playlists from XML
        rekordbox_playlists = await self.rekordbox_xml.read_xml(xml_path)
        if not rekordbox_playlists:
            logger.info("No playlists found in Rekordbox XML")
            return 0, 0, 0
        
        logger.info(f"Found {len(rekordbox_playlists)} playlists in Rekordbox XML")
        
        # Get existing playlists from database
        db_playlists = await self.playlist_service.get_playlists_by_source(PlaylistSource.REKORDBOX)
        
        # Create a lookup dictionary for existing playlists
        db_playlist_map = {p.name.lower(): p for p in db_playlists}
        
        # Process each Rekordbox playlist
        added_count = 0
        updated_count = 0
        failed_count = 0
        
        for playlist in rekordbox_playlists:
            try:
                # Check if playlist already exists (by name)
                existing = db_playlist_map.get(playlist.name.lower())
                
                if existing:
                    # Update existing playlist if needed
                    if self._playlist_needs_update(existing, playlist):
                        # Copy ID from existing playlist
                        playlist.id = existing.id
                        # Update playlist items with correct playlist ID
                        for item in playlist.items:
                            item.playlist_id = playlist.id
                        # Update in database
                        if await self.playlist_service.update_playlist(playlist):
                            # Update sync status
                            await self.playlist_service.update_sync_status(
                                playlist.id,
                                PlaylistSource.REKORDBOX,
                                SyncStatus.SYNCED,
                                version=playlist.version
                            )
                            updated_count += 1
                            logger.info(f"Updated playlist from Rekordbox: {playlist.name}")
                        else:
                            failed_count += 1
                            logger.error(f"Failed to update playlist: {playlist.name}")
                else:
                    # Create new playlist
                    playlist_id = await self.playlist_service.create_playlist(playlist)
                    if playlist_id:
                        added_count += 1
                        logger.info(f"Added new playlist from Rekordbox: {playlist.name}")
                    else:
                        failed_count += 1
                        logger.error(f"Failed to add playlist: {playlist.name}")
            except Exception as e:
                failed_count += 1
                logger.error(f"Error processing Rekordbox playlist {playlist.name}: {e}")
        
        logger.info(f"Rekordbox sync complete: {added_count} added, {updated_count} updated, {failed_count} failed")
        return added_count, updated_count, failed_count

    async def sync_all(self, rekordbox_xml_path: Optional[Path] = None) -> Tuple[int, int, int, bool]:
        """Perform a full synchronization between Plex and Rekordbox.
        
        This will:
        1. Import playlists from Plex
        2. Export playlists to Rekordbox
        3. Import playlists from Rekordbox
        
        Args:
            rekordbox_xml_path: Optional path to the Rekordbox XML file
            
        Returns:
            Tuple of (added, updated, failed, rekordbox_success)
        """
        # Use provided path or default
        xml_path = rekordbox_xml_path or self.rekordbox_xml_path
        
        # Sync from Plex to database
        added_plex, updated_plex, failed_plex = await self.sync_from_plex()
        
        # Sync from database to Rekordbox
        rekordbox_success = await self.sync_to_rekordbox(xml_path)
        
        # Sync from Rekordbox to database
        added_rb, updated_rb, failed_rb = (0, 0, 0)
        if xml_path and xml_path.exists():
            added_rb, updated_rb, failed_rb = await self.sync_from_rekordbox(xml_path)
        
        total_added = added_plex + added_rb
        total_updated = updated_plex + updated_rb
        total_failed = failed_plex + failed_rb
        
        logger.info(f"Full sync completed: {total_added} added, {total_updated} updated, {total_failed} failed")
        
        return total_added, total_updated, total_failed, rekordbox_success

    def _playlist_needs_update(self, existing: Playlist, new: Playlist) -> bool:
        """Check if a playlist needs to be updated.
        
        Args:
            existing: Existing playlist from database
            new: New playlist from source
            
        Returns:
            True if update is needed, False otherwise
        """
        # If names are different, update
        if existing.name != new.name:
            return True
            
        # If number of tracks is different, update
        if len(existing.items) != len(new.items):
            return True
            
        # Create a set of track IDs for comparison
        existing_tracks = {item.track_id for item in existing.items}
        new_tracks = {item.track_id for item in new.items}
        
        # If the track sets are different, update
        if existing_tracks != new_tracks:
            return True
            
        # Check if track order has changed
        existing_track_order = [(item.position, item.track_id) for item in existing.items]
        new_track_order = [(item.position, item.track_id) for item in new.items]
        
        if existing_track_order != new_track_order:
            return True
            
        # No significant changes detected
        return False</string>