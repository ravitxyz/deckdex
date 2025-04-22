"""Playlist management functionality for Deckdex."""

try:
    # When imported as part of package
    from deckdex.playlist.models import PlaylistItem, Playlist, SyncStatus
    from deckdex.playlist.service import PlaylistService
except ImportError:
    # When imported directly or as src.deckdex
    from src.deckdex.playlist.models import PlaylistItem, Playlist, SyncStatus
    from src.deckdex.playlist.service import PlaylistService

__all__ = ["PlaylistItem", "Playlist", "SyncStatus", "PlaylistService"]