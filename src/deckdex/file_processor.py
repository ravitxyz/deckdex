import logging
from typing import Optional
from pathlib import Path
from datetime import datetime
import hashlib
import subprocess
from .identifier.service import TrackIdentifierService

class FileProcessor:
    def __init__(self, source_dir: Path, dest_dir: Path, track_identifier: Optional[TrackIdentifierService] = None):
        self.source_dir = Path(source_dir)
        self.dest_dir = Path(dest_dir)
        self.track_identifier = track_identifier
        self.logger = logging.getLogger(__name__)
        
        # Setup detailed logging
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)
        
        # Add a file handler for diagnostic logging
        fh = logging.FileHandler('file_processor_diagnostic.log')
        fh.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)

    def _get_file_hash(self, file_path: Path) -> str:
        """Get a quick hash of the first 1MB of the file for change detection."""
        hasher = hashlib.md5()
        with open(file_path, 'rb') as f:
            # Read first 1MB for quick comparison
            chunk = f.read(1024 * 1024)
            hasher.update(chunk)
        return hasher.hexdigest()

    def _needs_processing(self, src_file: Path, dest_file: Path) -> tuple[bool, str]:
        """
        Enhanced check if file needs processing with detailed reason tracking.
        Returns (needs_processing, reason)
        """
        if not dest_file.exists():
            return True, "Destination file doesn't exist"

        try:
            src_mtime = src_file.stat().st_mtime
            dst_mtime = dest_file.stat().st_mtime
            src_size = src_file.stat().st_size
            dst_size = dest_file.stat().st_size

            # Log detailed timing information
            self.logger.debug(f"Source: {src_file}")
            self.logger.debug(f"  mtime: {datetime.fromtimestamp(src_mtime)}")
            self.logger.debug(f"  size: {src_size}")
            self.logger.debug(f"Destination: {dest_file}")
            self.logger.debug(f"  mtime: {datetime.fromtimestamp(dst_mtime)}")
            self.logger.debug(f"  size: {dst_size}")

            # Check file sizes first
            if src_size != dst_size:
                return True, f"Size mismatch: src={src_size}, dst={dst_size}"

            # If sizes match, check quick hash
            src_hash = self._get_file_hash(src_file)
            dst_hash = self._get_file_hash(dest_file)
            
            if src_hash != dst_hash:
                return True, f"Content hash mismatch"

            # If we get here, files are identical
            return False, "Files are identical"

        except OSError as e:
            self.logger.error(f"Error checking files: {e}")
            # If we can't check properly, assume we need to process
            return True, f"Error checking files: {e}"

    async def process_file(self, file_path: Path) -> Optional[TrackIdentifierService]:
        """Process a file and identify if it track_identifier is available"""
        try:
            # First identify if the track has a track identifier.
            identification_result = None
            if self.track_identifier:
                identification_result = await self.track_identifier.identify_track(file_path)
                # Extract metadata and update identification if sucessful
                metadata = self._extract_metadata(file_path)
                if metadata and identification_result and identification_result.identifier:
                    identification_result.identifier.metadata.update({
                        'title': metadata.title,
                        'artist ': metadata.artist,
                        'genre': metadata.genre,
                    })
            await self._process_file(file_path)
            return identification_result

        except Exception as e:
            self.logger.error(f"Error processing {file_path}: {e}")
            return None
    

    def process_files(self):
        """Process all audio files and artwork, including loose tracks."""
        processed_count = 0
        skipped_count = 0
        artwork_processed = 0

        for file_path in self.source_dir.rglob('*'):
            if self._is_audio_file(file_path):
                if file_path.parent == self.source_dir:
                    # This is a loose track
                    if self._process_loose_track(file_path):
                        processed_count += 1
                    else:
                        skipped_count += 1
                else:
                    # This is a track in an album folder
                    if self._process_album_track(file_path):
                        processed_count += 1
                    else:
                        skipped_count += 1
            elif self._is_artwork_file(file_path):
                # Process artwork files in album folders
                if file_path.parent != self.source_dir:  # Only process artwork in album folders
                    if self._process_album_artwork(file_path):
                        artwork_processed += 1

        self.logger.info(f"Processing complete. Audio files processed: {processed_count}, Skipped: {skipped_count}, Artwork files processed: {artwork_processed}")

    def _process_loose_track(self, file_path: Path) -> bool:
        """Handle tracks that aren't in album folders. Returns True if processed, False if skipped."""
        singles_dir = self.dest_dir / 'singles'
        singles_dir.mkdir(exist_ok=True)
        
        if self._needs_conversion(file_path):
            dest_file = singles_dir / f"{file_path.stem}.aiff"
        else:
            dest_file = singles_dir / file_path.name

        needs_proc, reason = self._needs_processing(file_path, dest_file)
        self.logger.info(
            f"Processing decision for loose track {file_path.name}: "
            f"needs_processing={needs_proc}, reason={reason}"
        )

        if needs_proc:
            # Process the file
            if self._needs_conversion(file_path):
                self._convert_to_aiff(file_path, dest_file)
                self.logger.info(f"Converted loose track: {file_path.name} -> {dest_file}")
            else:
                self._copy_with_metadata(file_path, dest_file)
                self.logger.info(f"Copied loose track: {file_path.name} -> {dest_file}")
            return True
        return False

    def _process_album_track(self, file_path: Path) -> bool:
        """Handle tracks that are in album folders. Returns True if processed, False if skipped."""
        relative_path = file_path.relative_to(self.source_dir)
        
        if self._needs_conversion(file_path):
            dest_file = self.dest_dir / relative_path.parent / f"{file_path.stem}.aiff"
        else:
            dest_file = self.dest_dir / relative_path

        needs_proc, reason = self._needs_processing(file_path, dest_file)
        self.logger.info(
            f"Processing decision for album track {file_path.name}: "
            f"needs_processing={needs_proc}, reason={reason}"
        )

        if needs_proc:
            # Process the file
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            if self._needs_conversion(file_path):
                self._convert_to_aiff(file_path, dest_file)
                self.logger.info(f"Converted album track: {file_path.name} -> {dest_file}")
            else:
                self._copy_with_metadata(file_path, dest_file)
                self.logger.info(f"Copied album track: {file_path.name} -> {dest_file}")
            return True
        return False
        
    def _process_album_artwork(self, file_path: Path) -> bool:
        """Handle cover art files in album folders. Returns True if processed, False if skipped."""
        relative_path = file_path.relative_to(self.source_dir)
        dest_file = self.dest_dir / relative_path

        needs_proc, reason = self._needs_processing(file_path, dest_file)
        
        if needs_proc:
            # Process the file
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            self._copy_with_metadata(file_path, dest_file)
            self.logger.info(f"Copied album artwork: {file_path.name} -> {dest_file}")
            return True
        return False

    def _is_audio_file(self, file_path: Path) -> bool:
        """Check if file is a supported audio format."""
        return file_path.suffix.lower() in ['.mp3', '.flac', '.aiff', '.wav', '.m4a']
        
    def _is_artwork_file(self, file_path: Path) -> bool:
        """Check if file is a cover art image."""
        return file_path.suffix.lower() in ['.jpg', '.jpeg', '.png'] and file_path.stem.lower() in ['cover', 'folder', 'album', 'front', 'artwork', 'art']

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

    def _copy_with_metadata(self, src: Path, dst: Path):
        """Copy file while preserving timestamps."""
        import shutil
        shutil.copy2(src, dst)  # copy2 preserves metadata