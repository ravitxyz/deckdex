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
        
    async def update_file_tags(self, audio_file: Path, metadata: TrackMetadata) -> bool:
        """Write metadata to audio file tags.
        
        Args:
            audio_file: Path to the audio file
            metadata: Metadata to write to the file
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Import mutagen here to avoid global dependency
            import mutagen
            from mutagen.id3 import ID3, TIT2, TPE1, TALB, TRCK, TCON, TDRC
            from mutagen.flac import FLAC
            from mutagen.mp3 import MP3
            from mutagen.aiff import AIFF
            from mutagen.mp4 import MP4
            
            file_ext = audio_file.suffix.lower()
            
            # Handle different file formats
            if file_ext == '.mp3':
                try:
                    # Try to load existing tags first
                    tags = ID3(audio_file)
                except:
                    # Create new tag structure if none exists
                    tags = ID3()
                    
                # Update tag fields
                if 'title' in metadata:
                    tags["TIT2"] = TIT2(encoding=3, text=metadata['title'])
                if 'artist' in metadata:
                    tags["TPE1"] = TPE1(encoding=3, text=metadata['artist'])
                if 'album' in metadata:
                    tags["TALB"] = TALB(encoding=3, text=metadata['album'])
                if 'track_number' in metadata:
                    tags["TRCK"] = TRCK(encoding=3, text=str(metadata['track_number']))
                if 'genre' in metadata:
                    tags["TCON"] = TCON(encoding=3, text=metadata['genre'])
                if 'year' in metadata:
                    tags["TDRC"] = TDRC(encoding=3, text=str(metadata['year']))
                    
                # Save tags to file
                tags.save(audio_file)
                
            elif file_ext == '.flac':
                audio = FLAC(audio_file)
                
                # Update tag fields
                if 'title' in metadata:
                    audio["title"] = metadata['title']
                if 'artist' in metadata:
                    audio["artist"] = metadata['artist']
                if 'album' in metadata:
                    audio["album"] = metadata['album']
                if 'track_number' in metadata and metadata['track_number']:
                    audio["tracknumber"] = str(metadata['track_number'])
                if 'genre' in metadata:
                    audio["genre"] = metadata['genre']
                if 'year' in metadata and metadata['year']:
                    audio["date"] = str(metadata['year'])
                    
                # Save tags to file
                audio.save()
                
            elif file_ext == '.m4a':
                audio = MP4(audio_file)
                
                # Map our fields to MP4 tags
                if 'title' in metadata:
                    audio["\xa9nam"] = [metadata['title']]
                if 'artist' in metadata:
                    audio["\xa9ART"] = [metadata['artist']]
                if 'album' in metadata:
                    audio["\xa9alb"] = [metadata['album']]
                if 'track_number' in metadata and metadata['track_number']:
                    audio["trkn"] = [(metadata['track_number'], 0)]
                if 'genre' in metadata:
                    audio["\xa9gen"] = [metadata['genre']]
                if 'year' in metadata and metadata['year']:
                    audio["\xa9day"] = [str(metadata['year'])]
                    
                # Save tags to file
                audio.save()
                
            elif file_ext == '.aiff':
                audio = AIFF(audio_file)
                
                # Create ID3 tags if they don't exist
                if audio.tags is None:
                    from mutagen.id3 import ID3
                    audio.tags = ID3()
                    
                # Update tag fields (using ID3 format for AIFF)
                if 'title' in metadata:
                    audio.tags["TIT2"] = TIT2(encoding=3, text=metadata['title'])
                if 'artist' in metadata:
                    audio.tags["TPE1"] = TPE1(encoding=3, text=metadata['artist'])
                if 'album' in metadata:
                    audio.tags["TALB"] = TALB(encoding=3, text=metadata['album'])
                if 'track_number' in metadata:
                    audio.tags["TRCK"] = TRCK(encoding=3, text=str(metadata['track_number']))
                if 'genre' in metadata:
                    audio.tags["TCON"] = TCON(encoding=3, text=metadata['genre'])
                if 'year' in metadata:
                    audio.tags["TDRC"] = TDRC(encoding=3, text=str(metadata['year']))
                    
                # Save tags to file
                audio.save()
                
            else:
                # For other formats, try generic approach
                audio = mutagen.File(audio_file)
                if audio:
                    # Update metadata based on available fields
                    for key, value in metadata.items():
                        if value is not None:
                            audio[key] = value
                    audio.save()
                else:
                    logger.warning(f"Unsupported file format for tagging: {file_ext}")
                    return False
                
            logger.info(f"Updated tags for {audio_file}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating tags for {audio_file}: {e}")
            return False
            
    async def sync_libraries(self, source_file: Path, dj_file: Path) -> bool:
        """Synchronize metadata between source library file and DJ library file.
        
        Args:
            source_file: Path to file in source library
            dj_file: Path to corresponding file in DJ library
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # First get enriched metadata
            metadata = await self.get_metadata(source_file)
            
            # Update tags in both files
            source_success = await self.update_file_tags(source_file, metadata)
            dj_success = await self.update_file_tags(dj_file, metadata)
            
            return source_success and dj_success
            
        except Exception as e:
            logger.error(f"Error syncing libraries: {e}")
            return False
