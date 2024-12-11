from pathlib import Path
import logging
from typing import Optional, Tuple
from mutagen import File as MutagenFile
from .models import TrackMetadata
import hashlib

class FileProcessor:
    def __init__(self, source_dir: Path, dest_dir: Path):
        self.source_dir = Path(source_dir)
        self.dest_dir = Path(dest_dir)
        self.logger = logging.getLogger(__name__)

    def process_directory(self):
        """Process all audio files in directory and yield (path, metadata) tuples."""
        for file_path in self.source_dir.rglob('*'):
            if self._is_audio_file(file_path):
                try:
                    metadata = self._extract_metadata(file_path)
                    if metadata:
                        yield file_path, metadata
                except Exception as e:
                    self.logger.error(f"Failed to process {file_path}: {str(e)}")

    def _extract_metadata(self, file_path: Path) -> Optional[TrackMetadata]:
        """Extract metadata from audio file."""
        try:
            audio = MutagenFile(file_path)
            if audio is None:
                return None

            # Basic metadata extraction
            return TrackMetadata(
                file_path=file_path,
                title=file_path.stem,  # Default to filename
                artist=file_path.parent.name,  # Default to parent directory name
                genre="",
                file_hash=self._calculate_file_hash(file_path)
            )
        except Exception as e:
            self.logger.error(f"Metadata extraction failed for {file_path}: {str(e)}")
            return None

    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of file content."""
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            # Read in chunks to handle large files efficiently
            for chunk in iter(lambda: f.read(65536), b''):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _is_audio_file(self, file_path: Path) -> bool:
        """Check if file is a supported audio format."""
        if file_path.name.startswith('.'):
            return False
        return file_path.suffix.lower() in ['.mp3', '.flac', '.aiff', '.wav', '.m4a']

    def process_files(self):
        """Process all audio files."""
        for file_path in self.source_dir.rglob('*'):
            if self._is_audio_file(file_path):
                self._process_file(file_path)

    def _process_file(self, file_path: Path):
        """Process a single audio file."""
        if self._needs_conversion(file_path):
            relative_path = file_path.relative_to(self.source_dir)
            dest_file = self.dest_dir / relative_path.parent / f"{file_path.stem}.aiff"
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            self._convert_to_aiff(file_path, dest_file)
        else:
            relative_path = file_path.relative_to(self.source_dir)
            dest_file = self.dest_dir / relative_path
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, dest_file)

    def _needs_conversion(self, file_path: Path) -> bool:
        """Check if file needs conversion to AIFF."""
        return file_path.suffix.lower() in ['.flac', '.wav']

    def _convert_to_aiff(self, source_file: Path, dest_file: Path):
        """Convert audio file to AIFF format."""
        cmd = [
            'ffmpeg', '-i', str(source_file),
            '-c:a', 'pcm_s16be',
            '-f', 'aiff',
            str(dest_file),
            '-y'
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Conversion failed for {source_file}: {e}")
            raise