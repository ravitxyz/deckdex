from pathlib import Path
import logging
from typing import Dict, List, Optional, Mapping
import aiohttp
import json
import aiosqlite
import asyncio
from datetime import datetime, timedelta
from abc import ABC, abstractmethod
from .models import TrackMetadata

logger = logging.getLogger(__name__)

class MetadataProvider(ABC):
    """Base class for metadata providers."""
    
    @abstractmethod
    async def get_metadata(self, audio_file: Path) -> TrackMetadata:
        """Retrieve metadata for an audio file."""
        pass
    
    @abstractmethod
    async def get_provider_name(self) -> str:
        """Get the name of this provider."""
        pass
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the provider with any necessary setup."""
        pass

class MetadataCache:
    """Cache for metadata to reduce API calls."""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
    
    async def _init_db(self):
        """Initialize the cache database."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS metadata_cache (
                    file_path TEXT,
                    provider TEXT,
                    metadata JSON,
                    timestamp DATETIME,
                    PRIMARY KEY (file_path, provider)
                )
            """)
            await db.commit()
    
    async def get(self, file_path: Path, provider: str) -> Optional[TrackMetadata]:
        """Get cached metadata if it exists and is not expired."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT metadata, timestamp 
                FROM metadata_cache 
                WHERE file_path = ? AND provider = ?
                """,
                (str(file_path), provider)
            ) as cursor:
                result = await cursor.fetchone()
                
                if result:
                    metadata_json, timestamp_str = result
                    timestamp = datetime.fromisoformat(timestamp_str)
                    
                    # Check if cache is still valid (24 hours)
                    if datetime.now() - timestamp < timedelta(hours=24):
                        return TrackMetadata(**json.loads(metadata_json))
        
        return None
    
    async def set(self, file_path: Path, provider: str, metadata: TrackMetadata) -> None:
        """Cache metadata for a file."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO metadata_cache 
                (file_path, provider, metadata, timestamp)
                VALUES (?, ?, ?, ?)
                """,
                (
                    str(file_path),
                    provider,
                    json.dumps(metadata),
                    datetime.now().isoformat()
                )
            )
            await db.commit()

class MetadataService:
    """Main service for handling metadata operations."""
    
    def __init__(self, config: Mapping[str, str]):
        self.config = config
        self.providers: List[MetadataProvider] = []
        self.cache = MetadataCache(Path(config['cache_db_path']))
    
    async def initialize(self) -> None:
        """Initialize the service and its dependencies."""
        await self.cache._init_db()
        await self._init_providers()
    
    async def _init_providers(self) -> None:
        """Initialize metadata providers based on configuration."""
        # TODO: implement provider initialization
        for provider in self.providers:
            await provider.initialize()
    
    async def get_metadata(self, audio_file: Path) -> TrackMetadata:
        """Get metadata from all providers and merge results."""
        all_metadata: Dict[str, TrackMetadata] = {}
        
        for provider in self.providers:
            try:
                provider_name = await provider.get_provider_name()
                
                # Check cache first
                cached = await self.cache.get(audio_file, provider_name)
                if cached is not None:
                    all_metadata[provider_name] = cached
                    continue
                
                # If not in cache, fetch from provider
                metadata = await provider.get_metadata(audio_file)
                await self.cache.set(audio_file, provider_name, metadata)
                all_metadata[provider_name] = metadata
                
            except Exception as e:
                provider_name = await provider.get_provider_name()
                logger.error(f"Error getting metadata from {provider_name}: {e}")
                continue
        
        return self._merge_metadata(all_metadata)
    
    def _merge_metadata(self, all_metadata: Mapping[str, TrackMetadata]) -> TrackMetadata:
        """Merge metadata from different providers with basic conflict resolution."""
        merged: TrackMetadata = {}
        fields = [
            'title', 'artist', 'album', 'year', 'genre', 
            'track_number', 'duration', 'bpm', 'key', 'energy'
        ]
        
        for field in fields:
            for provider_data in all_metadata.values():
                if field in provider_data and provider_data[field] is not None:
                    merged[field] = provider_data[field]
                    break
        
        return merged
