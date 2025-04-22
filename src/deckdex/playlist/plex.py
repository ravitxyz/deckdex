"""Adapters between Plex playlist data and internal playlist models.

This module provides conversion functionality between Plex data (accessed via utils/plex.py)
and the Deckdex internal playlist models. It does not access the Plex database directly,
but relies on the PlexLibraryReader class instead.
"""

import logging
from pathlib import Path
from typing import List, Optional

from deckdex.identifier.service import TrackIdentifierService
from deckdex.playlist.models import Playlist, PlaylistItem, PlaylistSource
from deckdex.utils.plex import PlexLibraryReader

logger = logging.getLogger(__name__)


class PlexPlaylistAdapter:
    """Adapter for converting between Plex and internal playlist models."""

    def __init__(
        self,
        plex_reader: PlexLibraryReader,
        track_identifier_service: Optional[TrackIdentifierService] = None
    ):
        """Initialize the Plex playlist adapter.
        
        Args:
            plex_reader: Existing PlexLibraryReader instance
            track_identifier_service: Optional service for resolving track identifiers
        """
        self.plex_reader = plex_reader
        self.track_identifier_service = track_identifier_service

    async def get_playlists(self) -> List[Playlist]:
        """Retrieve all playlists from Plex and convert to internal format.
        
        Returns:
            List of playlists in internal format
        """
        plex_playlists = await self.plex_reader.get_playlists()
        return [await self._convert_playlist(playlist) for playlist in plex_playlists]

    async def get_playlist_by_id(self, playlist_id: str) -> Optional[Playlist]:
        """Get a specific playlist by its Plex ID.
        
        Args:
            playlist_id: Plex playlist ID
            
        Returns:
            Playlist if found, None otherwise
        """
        plex_playlist = await self.plex_reader.get_playlist_by_id(playlist_id)
        if not plex_playlist:
            return None
        return await self._convert_playlist(plex_playlist)

    async def _convert_playlist(self, plex_playlist) -> Playlist:
        """Convert a Plex playlist to internal format.
        
        Args:
            plex_playlist: Playlist data from Plex
            
        Returns:
            Playlist in internal format
        """
        items = []
        
        for position, track in enumerate(plex_playlist.tracks):
            track_id = None
            
            # If track identifier service is available, try to identify by path
            if track.file_path and self.track_identifier_service:
                try:
                    track_id = await self.track_identifier_service.identify_by_path(Path(track.file_path))
                except Exception as e:
                    logger.error(f"Error identifying track {track.file_path}: {e}")
            
            # Use Plex ID as fallback
            if not track_id:
                track_id = f"plex:{track.id}"
            
            items.append(PlaylistItem(
                playlist_id=plex_playlist.id,
                track_id=track_id,
                position=position,
                external_id=str(track.id)
            ))
        
        return Playlist(
            name=plex_playlist.title,
            description=plex_playlist.summary,
            source=PlaylistSource.PLEX,
            external_id=str(plex_playlist.id),
            items=items,
            created_at=plex_playlist.created_at,
            modified_at=plex_playlist.updated_at
        )