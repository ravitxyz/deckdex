import logging
from pathlib import Path
from typing import Optional, Iterator
import hashlib
from dataclasses import dataclass

logger = logging.getlogger(__name__)

@dataclass
class TrackMetadata:
    title: str
    artist: str
    genre: Optional[str] = None
    bpm: Optional[float] = None
    key: Optional[str] = None
    stage: Optional[str] = None
    vibe: Optional[str] = None
    energy_level: Optional[str] = None
    rating: Optional[int] = None

class FileProcessor:
    """Process audio files and extract metadata."""

    SUPPORTED_FILE_EXTENSIONS = {".mp3", ".flac", ".wav", ".m4a", ".aiff"}

    def __init__(self, library):
        self.library = library

    def scan_directory(self, directory: Path) -> Iterator[Path]:
        """Scan directory for music files recursively."""
        if not directory.exists():
            raise FileNotFoundError(f"Directory does not exist: {directory}")

        for file_path in directory.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in self.SUPPORTED_FILE_EXTENSIONS:
                yield file_path

    def process_file(self, file_path: Path) -> Optional[TrackMetadata]:
        """Process a single file and extract metadata."""
        try:
            # TODO: Implemenent proper metadata extraction
            title = file_path.stem
            artist = "Unknown" # we'll extract this later from tags

            metadata = TrackMetadata(
                title=title,
                artist=artist
            )
            logger.debug(f"Processed file: {file_path}")
            return metadata
        except Exception as e:
            logger.error(f"Error processing file {file_path}: {e}")
            return None


    def calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of a file."""
        sha256_hash = hashlib.sha256()

        with file_path.open("rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)

        return sha256_hash.hexdigest()