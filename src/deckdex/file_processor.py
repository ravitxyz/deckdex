# src/deckdex/file_processor.py

import logging
from pathlib import Path
from typing import Optional, Iterator
import hashlib
from mutagen import File as MutagenFile
from mutagen.easyid3 import EasyID3

from .models import TrackMetadata, MusicLibrary

logger = logging.getLogger(__name__)

class FileProcessor:
    """Process music files and extract metadata."""
    
    SUPPORTED_EXTENSIONS = {'.mp3', '.flac', '.aiff', '.wav', '.m4a'}
    
    def __init__(self, library: MusicLibrary):
        self.library = library
    
    def scan_directory(self, directory: Path) -> Iterator[Path]:
        """Scan directory for music files recursively."""
        if not directory.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")
            
        for file_path in directory.rglob('*'):
            if file_path.is_file() and file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS:
                logger.debug(f"Found music file: {file_path}")
                yield file_path
    
    def process_file(self, file_path: Path) -> Optional[TrackMetadata]:
        """Process a single music file and extract metadata."""
        try:
            # Calculate file hash first
            file_hash = self.library.calculate_file_hash(file_path)
            
            # Extract metadata using mutagen
            audio = MutagenFile(file_path)
            if audio is None:
                logger.warning(f"Could not read metadata from {file_path}")
                return self._create_basic_metadata(file_path, file_hash)
            
            # Try to get ID3 tags for MP3s
            if file_path.suffix.lower() == '.mp3':
                try:
                    audio = EasyID3(file_path)
                except:
                    logger.warning(f"Could not read ID3 tags from {file_path}")
                    return self._create_basic_metadata(file_path, file_hash)
            
            # Extract metadata
            metadata = self._extract_metadata(file_path, audio, file_hash)
            logger.debug(f"Processed metadata for {file_path}: {metadata}")
            return metadata
            
        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
            return None
    
    def _extract_metadata(self, file_path: Path, audio, file_hash: str) -> TrackMetadata:
        """Extract metadata from audio file using mutagen."""
        # Default values
        title = file_path.stem
        artist = "Unknown"
        genre = "Unknown"
        bpm = None
        key = None
        
        # Try to extract basic metadata
        if hasattr(audio, 'tags') and audio.tags:
            # Handle MP3 (ID3) tags
            if isinstance(audio, EasyID3):
                title = audio.get('title', [file_path.stem])[0]
                artist = audio.get('artist', ['Unknown'])[0]
                genre = audio.get('genre', ['Unknown'])[0]
                
                # Try to get BPM
                if 'bpm' in audio:
                    try:
                        bpm = float(audio['bpm'][0])
                    except (ValueError, IndexError):
                        pass
                
                # Try to get key
                key = audio.get('key', [None])[0]
            
            # Handle other formats
            else:
                tags = audio.tags
                title = str(tags.get('title', [file_path.stem])[0])
                artist = str(tags.get('artist', ['Unknown'])[0])
                genre = str(tags.get('genre', ['Unknown'])[0])
                
                # Try to get BPM
                if 'bpm' in tags:
                    try:
                        bpm = float(str(tags['bpm'][0]))
                    except (ValueError, IndexError):
                        pass
                
                # Try to get key
                if 'key' in tags:
                    key = str(tags['key'][0])
        
        return TrackMetadata(
            file_path=file_path,
            title=title,
            artist=artist,
            genre=genre,
            bpm=bpm,
            key=key,
            stage=None,  # These will be set manually/through UI
            vibe=None,   # These will be set manually/through UI
            energy_level=None,
            rating=None,
            file_hash=file_hash
        )
    
    def _create_basic_metadata(self, file_path: Path, file_hash: str) -> TrackMetadata:
        """Create basic metadata from filename when tags can't be read."""
        return TrackMetadata(
            file_path=file_path,
            title=file_path.stem,
            artist="Unknown",
            genre="Unknown",
            file_hash=file_hash
        )
    
    def handle_flac_conversion(self, file_path: Path) -> Optional[Path]:
        """Convert FLAC to AIFF if needed."""
        if file_path.suffix.lower() == '.flac':
            try:
                aiff_path = self.library.convert_flac_to_aiff(file_path)
                logger.info(f"Converted {file_path} to {aiff_path}")
                return aiff_path
            except Exception as e:
                logger.error(f"Failed to convert {file_path} to AIFF: {e}")
                return None
        return None