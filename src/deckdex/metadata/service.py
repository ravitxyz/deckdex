import logging
from pathlib import Path
from typing import Dict, Any, Optional
import asyncio
import hashlib

from .cache import MetadataCache
from .providers import (
    AcoustIDProvider,
    MusicBrainzProvider,
    DiscogsProvider,
    PlexProvider,
    Provider,
    ProviderError
)

logger = logging.getLogger(__name__)

class MetadataService:
    """
    Centralized service for fetching and managing track metadata from multiple sources.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the metadata service with configuration.
        
        Args:
            config: Dictionary containing configuration parameters:
                - acoustid_api_key: API key for AcoustID service
                - discogs_token: Access token for Discogs API
                - plex_url: URL for Plex server
                - plex_token: Authentication token for Plex
                - cache_path: Path to store metadata cache
        """
        self.config = config
        self.providers: Dict[str, Provider] = {}
        self._init_providers()
        self.cache = MetadataCache(config.get('cache_path'))
        
    def _init_providers(self):
        """Initialize metadata providers based on configuration."""
        if self.config.get('acoustid_api_key'):
            self.providers['acoustid'] = AcoustIDProvider(
                self.config['acoustid_api_key']
            )
            
        if self.config.get('discogs_token'):
            self.providers['discogs'] = DiscogsProvider(
                self.config['discogs_token']
            )
            
        self.providers['musicbrainz'] = MusicBrainzProvider()
        
        if self.config.get('plex_url') and self.config.get('plex_token'):
            self.providers['plex'] = PlexProvider(
                self.config['plex_url'],
                self.config['plex_token']
            )

    async def enhance_track_metadata(self, file_path: Path) -> Dict[str, Any]:
        """
        Get comprehensive metadata for a track from all available sources.
        
        Args:
            file_path: Path to the audio file
            
        Returns:
            Dictionary containing merged metadata from all sources
        """
        cache_key = self._generate_cache_key(file_path)
        
        # Check cache first
        if cached := await self.cache.get(cache_key):
            logger.debug(f"Cache hit for {file_path}")
            return cached

        # Generate audio fingerprint for matching
        fingerprint = await self._generate_fingerprint(file_path)
        
        # Collect metadata from all providers
        metadata: Dict[str, Any] = {}
        tasks = []
        
        for provider in self.providers.values():
            task = self._get_provider_metadata(provider, fingerprint, file_path)
            tasks.append(task)
        
        # Wait for all provider results
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Merge results from successful providers
        for result in results:
            if isinstance(result, Dict):
                metadata = self._merge_metadata(metadata, result)
        
        # Analyze release type
        release_info = self._analyze_release_type(metadata)
        metadata.update(release_info)
        
        # Cache the results
        await self.cache.set(cache_key, metadata)
        
        return metadata
    
    async def _get_provider_metadata(
        self, 
        provider: Provider, 
        fingerprint: str, 
        file_path: Path
    ) -> Optional[Dict[str, Any]]:
        """Safely get metadata from a single provider."""
        try:
            return await provider.get_metadata(fingerprint, file_path)
        except ProviderError as e:
            logger.error(f"Provider {provider.name} failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error from provider {provider.name}: {e}")
            return None
    
    def _generate_cache_key(self, file_path: Path) -> str:
        """Generate a unique cache key for a file based on path and modification time."""
        mtime = file_path.stat().st_mtime
        content = f"{file_path}:{mtime}".encode()
        return hashlib.sha256(content).hexdigest()
    
    async def _generate_fingerprint(self, file_path: Path) -> str:
        """Generate acoustic fingerprint for audio file."""
        # We'll implement this using acoustid's chromaprint
        # For now return a placeholder
        return ""
    
    def _merge_metadata(self, base: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
        """
        Smart merge of metadata dictionaries.
        Handles conflicts by preferring more reliable sources and newer data.
        """
        merged = base.copy()
        
        for key, value in new.items():
            if key not in merged:
                merged[key] = value
            else:
                # If key exists, use some rules to decide which value to keep
                merged[key] = self._resolve_metadata_conflict(
                    key, merged[key], value
                )
        
        return merged
    
    def _resolve_metadata_conflict(
        self,
        key: str,
        old_value: Any,
        new_value: Any
    ) -> Any:
        """
        Resolve conflicts between metadata values.
        Could be expanded with more sophisticated resolution rules.
        """
        # For now, prefer non-None values
        if old_value is None:
            return new_value
        if new_value is None:
            return old_value
            
        # Prefer longer strings as they might contain more information
        if isinstance(old_value, str) and isinstance(new_value, str):
            if len(new_value) > len(old_value):
                return new_value
            return old_value
            
        # Default to keeping existing value
        return old_value
    
    def _analyze_release_type(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Determine if track is a single, album track, etc.
        Returns additional metadata about the release type.
        """
        is_single = False
        release_type = "unknown"
        
        # Check explicit release type information
        if "release_type" in metadata:
            release_type = metadata["release_type"]
            is_single = release_type.lower() == "single"
            
        # Check number of tracks if available
        elif "total_tracks" in metadata:
            is_single = metadata["total_tracks"] == 1
            
        # Check release format
        elif "format" in metadata:
            format_name = metadata["format"].lower()
            is_single = "single" in format_name or "7\"" in format_name
            
        return {
            "is_single": is_single,
            "release_type": release_type,
            "suggested_category": self._suggest_category(metadata)
        }
    
    def _suggest_category(self, metadata: Dict[str, Any]) -> str:
        """Suggest a category for the track based on available metadata."""
        # This could be expanded with more sophisticated categorization logic
        if metadata.get("is_single"):
            return "singles"
        if metadata.get("album"):
            return "albums"
        return "uncategorized"
