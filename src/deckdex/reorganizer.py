import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, NamedTuple
import shutil
import hashlib
from datetime import datetime
from dataclasses import dataclass
import sqlite3
from concurrent.futures import ThreadPoolExecutor
import subprocess
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.console import Console
import os
import yaml

@dataclass
class Config:
    source_dir: Path
    listening_library_dir: Path
    dj_library_dir: Path
    db_path: Path
    plex_db_path: Path
    plex_library_dir: Path
    min_dj_rating: float
    max_workers: int
    supported_formats: List[str]
    convert_formats: List[str]

    @classmethod
    def load_config(cls, config_path: Path) -> 'Config':
        """Load configuration from YAML file."""
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found at {config_path}")

        with open(config_path) as f:
            config_data = yaml.safe_load(f)
            
        # Debug print
        print(f"Loaded config data: {config_data}")
        
        # Handle both flat and nested structures
        if 'paths' in config_data:
            # Nested structure
            paths = config_data['paths']
            library = config_data['library']
        else:
            # Flat structure
            paths = {
                'source_dir': config_data['source_dir'],
                'listening_lib': config_data['listening_library_dir'],
                'dj_lib': config_data['dj_library_dir'],
                'db_path': config_data['db_path'],
                'plex_db': config_data['plex_db_path']
            }
            library = {
                'rating_threshold': config_data['min_dj_rating'],
                'formats': config_data.get('supported_formats', ['.mp3', '.flac', '.aiff', '.wav', '.m4a']),
                'convert_formats': config_data.get('convert_formats', ['.flac', '.wav'])
            }

        return cls(
            source_dir=Path(paths['source_dir']),
            listening_library_dir=Path(paths['listening_lib']),
            dj_library_dir=Path(paths['dj_lib']),
            db_path=Path(paths['db_path']),
            plex_db_path=Path(paths['plex_db']),
            plex_library_dir=Path(paths['source_dir']),
            min_dj_rating=float(library['rating_threshold']),
            max_workers=config_data.get('max_workers', 4),
            supported_formats=library['formats'],
            convert_formats=library.get('convert_formats', ['.flac', '.wav'])
        )

    def save_config(self, config_path: Path):
        """Save configuration to YAML file."""
        config_data = {
            'source_dir': str(self.source_dir),
            'listening_library_dir': str(self.listening_library_dir),
            'dj_library_dir': str(self.dj_library_dir),
            'db_path': str(self.db_path),
            'plex_db_path': str(self.plex_db_path),
            'min_dj_rating': self.min_dj_rating,
            'max_workers': self.max_workers
        }

        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f, default_flow_style=False)

@dataclass
class TrackFile:
    source_path: Path
    title: str
    artist: str
    needs_conversion: bool
    file_hash: str
    rating: Optional[float] = None  # Plex rating (0-10)
    plex_guid: Optional[str] = None

class PlexMetadata(NamedTuple):
    guid: str
    rating: Optional[float]
    title: str
    artist: str

class LibraryReorganizer:
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.console = Console()
        
        # Initialize directories
        self._initialize_directories()

    def _initialize_directories(self):
        """Initialize all required directories."""
        for directory in [
            self.config.listening_library_dir,
            self.config.dj_library_dir,
            self.config.db_path.parent
        ]:
            try:
                directory.mkdir(parents=True, exist_ok=True)
                # Test write permissions
                test_file = directory / '.test'
                test_file.touch()
                test_file.unlink()
            except PermissionError:
                self.logger.error(f"No write permission for directory: {directory}")
                raise
            except Exception as e:
                self.logger.error(f"Failed to initialize directory {directory}: {e}")
                raise

    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of file content."""
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            # Read in chunks to handle large files efficiently
            for chunk in iter(lambda: f.read(65536), b''):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _needs_conversion(self, file_path: Path) -> bool:
        """Check if file needs conversion for DJ library."""
        return file_path.suffix.lower() in ['.flac', '.wav']

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for filesystem compatibility."""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        return filename.strip()

    def _get_plex_metadata(self, file_path: Path) -> Optional[PlexMetadata]:
        """Get metadata from Plex database."""
        try:
            with sqlite3.connect(self.config.plex_db_path) as conn:
                cursor = conn.cursor()
                
                # Convert file path to match Plex's storage format
                plex_path = str(file_path).replace('\\', '/')
                
                query = """
                SELECT 
                    m.guid,
                    mis.rating,
                    m.title,
                    (
                        SELECT mi2.title
                        FROM metadata_items mi2
                        WHERE mi2.id = m.parent_id
                        LIMIT 1
                    ) as artist
                FROM media_parts mp
                JOIN media_items mi ON mp.media_item_id = mi.id
                JOIN metadata_items m ON mi.metadata_item_id = m.id
                LEFT JOIN metadata_item_settings mis ON m.guid = mis.guid
                WHERE mp.file LIKE ?
                """
                
                cursor.execute(query, (f"%{file_path.name}%",))
                result = cursor.fetchone()
                
                if result:
                    return PlexMetadata(
                        guid=result[0],
                        rating=result[1],
                        title=result[2],
                        artist=result[3] or "Unknown Artist"
                    )
                return None
                
        except sqlite3.Error as e:
            self.logger.error(f"Plex database error: {e}")
            return None

    def _convert_to_aiff(
        self, 
        source_file: Path, 
        dest_file: Path
    ) -> Tuple[bool, Optional[str]]:
        """Convert audio file to AIFF format."""
        try:
            cmd = [
                'ffmpeg', '-i', str(source_file),
                '-c:a', 'pcm_s16be',
                '-f', 'aiff',
                str(dest_file),
                '-y'  # Overwrite output files
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            return True, None
            
        except subprocess.CalledProcessError as e:
            return False, f"Conversion failed: {e.stderr}"
        except Exception as e:
            return False, str(e)

    def _get_file_metadata(self, file_path: Path) -> Dict[str, str]:
        """Extract metadata directly from music file tags."""
        try:
            # Use mutagen to read file tags
            import mutagen
            from mutagen.easyid3 import EasyID3
            from mutagen.mp3 import MP3
            from mutagen.flac import FLAC
            from mutagen.aiff import AIFF
            
            metadata = {}
            
            # Handle different file formats
            if file_path.suffix.lower() == '.mp3':
                try:
                    audio = EasyID3(file_path)
                    metadata = dict(audio)
                except:
                    audio = MP3(file_path)
                    # Extract basic tags if available
                    if 'TPE1' in audio:  # Artist
                        metadata['artist'] = str(audio['TPE1'])
                    if 'TIT2' in audio:  # Title
                        metadata['title'] = str(audio['TIT2'])
                    if 'TALB' in audio:  # Album
                        metadata['album'] = str(audio['TALB'])
            elif file_path.suffix.lower() == '.flac':
                audio = FLAC(file_path)
                metadata = dict(audio)
            elif file_path.suffix.lower() == '.aiff':
                audio = AIFF(file_path)
                # Extract ID3 tags if available
                if hasattr(audio, 'tags') and audio.tags:
                    if 'TPE1' in audio.tags:  # Artist
                        metadata['artist'] = str(audio.tags['TPE1'])
                    if 'TIT2' in audio.tags:  # Title
                        metadata['title'] = str(audio.tags['TIT2'])
                    if 'TALB' in audio.tags:  # Album
                        metadata['album'] = str(audio.tags['TALB'])
            else:
                # For other formats, try generic approach
                audio = mutagen.File(file_path)
                if audio and hasattr(audio, 'tags') and audio.tags:
                    metadata = dict(audio.tags)
            
            # Clean up metadata values (handle list values)
            for key, value in metadata.items():
                if isinstance(value, list) and len(value) > 0:
                    metadata[key] = value[0]
            
            # Return cleaned metadata
            return {
                'artist': metadata.get('artist', [file_path.parent.name])[0] if isinstance(metadata.get('artist', []), list) else metadata.get('artist', file_path.parent.name),
                'title': metadata.get('title', [file_path.stem])[0] if isinstance(metadata.get('title', []), list) else metadata.get('title', file_path.stem),
                'album': metadata.get('album', ['Unknown Album'])[0] if isinstance(metadata.get('album', []), list) else metadata.get('album', 'Unknown Album')
            }
        except Exception as e:
            self.logger.error(f"Error reading metadata from {file_path}: {e}")
            # Return default metadata based on filename
            return {
                'artist': file_path.parent.name,
                'title': file_path.stem,
                'album': 'Unknown Album'
            }
    
    def _process_track(
        self, 
        track: TrackFile
    ) -> Tuple[bool, Optional[str]]:
        """Process a single track for both libraries."""
        try:
            # Extract metadata directly from file instead of using Plex metadata
            file_metadata = self._get_file_metadata(track.source_path)
            
            # Use file metadata for organization
            artist_dir = self._sanitize_filename(file_metadata['artist'])
            title = self._sanitize_filename(file_metadata['title'])
            
            # Listening library processing - use file metadata structure
            listening_artist_dir = self.config.listening_library_dir / artist_dir
            listening_artist_dir.mkdir(exist_ok=True)
            listening_dest = listening_artist_dir / track.source_path.name
            
            # Copy to listening library (maintaining original format)
            if not listening_dest.exists():
                shutil.copy2(track.source_path, listening_dest)
            
            # Only process for DJ library if rating meets minimum
            if track.rating and track.rating >= self.config.min_dj_rating:
                # DJ library approach: Preserve the EXACT same paths as in source directory
                # This maintains Rekordbox compatibility since it uses paths as identifiers
                
                # Calculate the relative path from source directory
                try:
                    rel_path = track.source_path.relative_to(self.config.source_dir)
                    dj_dest = self.config.dj_library_dir / rel_path
                except ValueError:
                    # Fallback if the file is not inside the source directory
                    dj_dest = self.config.dj_library_dir / track.source_path.name
                
                # Ensure parent directories exist
                dj_dest.parent.mkdir(parents=True, exist_ok=True)
                
                # Handle artwork files separately - just copy them directly
                if track.source_path.suffix.lower() in ['.jpg', '.jpeg', '.png'] and \
                   track.source_path.stem.lower() in ['cover', 'folder', 'album', 'front', 'artwork', 'art']:
                    if not dj_dest.exists():
                        shutil.copy2(track.source_path, dj_dest)
                        self.logger.info(f"Added artwork to DJ library: {track.source_path.name}")
                    else:
                        self.logger.debug(f"Skipped existing artwork in DJ library: {track.source_path.name}")
                # For FLAC/WAV files, convert to AIFF but maintain original path structure
                elif track.needs_conversion:
                    # Convert to AIFF but keep the same path (just change extension)
                    dj_dest = dj_dest.with_suffix('.aiff')
                    
                    # Only convert if the file doesn't already exist
                    if not dj_dest.exists():
                        success, error = self._convert_to_aiff(
                            track.source_path, 
                            dj_dest
                        )
                        if not success:
                            return False, error
                        self.logger.info(f"Added to DJ library: {track.source_path.name} (Rating: {track.rating/2:.1f} stars)")
                    else:
                        self.logger.debug(f"Skipped existing DJ library file: {track.source_path.name} (Rating: {track.rating/2:.1f} stars)")
                else:
                    # Copy non-FLAC/WAV files directly to the same path structure
                    if not dj_dest.exists():
                        shutil.copy2(track.source_path, dj_dest)
                        self.logger.info(f"Added to DJ library: {track.source_path.name} (Rating: {track.rating/2:.1f} stars)")
                    else:
                        self.logger.debug(f"Skipped existing DJ library file: {track.source_path.name} (Rating: {track.rating/2:.1f} stars)")
            else:
                self.logger.debug(
                    f"Skipped for DJ library: {track.source_path.name} "
                    f"(Rating: {(track.rating or 0)/2:.1f} stars)"
                )
            
            return True, None
            
        except Exception as e:
            return False, str(e)

    def reorganize_library(self):
        """Main method to reorganize the entire library."""
        self.logger.info("Starting library reorganization...")
        
        # First count total files without showing progress
        total_files = sum(
            1 for file_path in self.config.source_dir.rglob("*")
            if (file_path.is_file() 
                and not file_path.name.startswith(".")
                and file_path.suffix.lower() in ['.mp3', '.flac', '.aiff', '.wav', '.m4a'])
        )
        
        # Scan source directory with progress
        tracks_to_process: List[TrackFile] = []
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("({task.completed}/{task.total})"),
            console=Console(force_terminal=True)  # Force terminal output
        ) as progress:
            scan_task = progress.add_task(
                description="Scanning files...", 
                total=total_files
            )
            
            # Add empty line for file names to appear below
            print("")
            
            for file_path in self.config.source_dir.rglob("*"):
                if not file_path.is_file() or file_path.name.startswith("."):
                    continue
                    
                # Check if it's a supported audio file or artwork file
                is_audio = file_path.suffix.lower() in [
                    '.mp3', '.flac', '.aiff', '.wav', '.m4a'
                ]
                is_artwork = file_path.suffix.lower() in ['.jpg', '.jpeg', '.png'] and \
                             file_path.stem.lower() in ['cover', 'folder', 'album', 'front', 'artwork', 'art']
                
                if not (is_audio or is_artwork):
                    continue
                
                # Move cursor up one line and clear it before printing new filename
                print(f"\033[A\033[K{file_path.name}")
                progress.update(scan_task, advance=1)
                
                # Get Plex metadata including rating
                plex_metadata = self._get_plex_metadata(file_path)
                
                if plex_metadata:
                    track = TrackFile(
                        source_path=file_path,
                        title=plex_metadata.title,
                        artist=plex_metadata.artist,
                        needs_conversion=self._needs_conversion(file_path),
                        file_hash=self._calculate_file_hash(file_path),
                        rating=plex_metadata.rating,
                        plex_guid=plex_metadata.guid
                    )
                else:
                    # Fallback to file system info if no Plex metadata
                    track = TrackFile(
                        source_path=file_path,
                        title=file_path.stem,
                        artist=file_path.parent.name,
                        needs_conversion=self._needs_conversion(file_path),
                        file_hash=self._calculate_file_hash(file_path)
                    )
                
                tracks_to_process.append(track)
        
        # Process tracks with progress bar
        with Progress() as progress:
            task = progress.add_task(
                "Reorganizing library...", 
                total=len(tracks_to_process)
            )
            
            with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
                futures = []
                for track in tracks_to_process:
                    future = executor.submit(self._process_track, track)
                    futures.append((future, track))
                
                # Process results as they complete
                for future, track in futures:
                    success, error = future.result()
                    if success:
                        self.logger.info(
                            f"Processed: {track.source_path.name}"
                        )
                    else:
                        self.logger.error(
                            f"Failed to process {track.source_path.name}: {error}"
                        )
                    progress.advance(task)

        self.logger.info("Library reorganization completed!")

    def process_single_file(self, file_path: Path):
        """Process a single file for both libraries."""
        try:
            # Check if this is an artwork file
            is_artwork = file_path.suffix.lower() in ['.jpg', '.jpeg', '.png'] and \
                         file_path.stem.lower() in ['cover', 'folder', 'album', 'front', 'artwork', 'art']
            
            if is_artwork:
                # Create TrackFile object for artwork
                track = TrackFile(
                    source_path=file_path,
                    title=file_path.stem,
                    artist=file_path.parent.name,
                    needs_conversion=False,
                    file_hash=self._calculate_file_hash(file_path),
                    # For artwork, always set a high enough rating to be included in DJ library
                    rating=10.0
                )
                
                # Process the artwork
                self._process_track(track)
                return
            
            # For audio files, get Plex metadata if available
            plex_metadata = self._get_plex_metadata(file_path)
            
            # Create TrackFile object
            track = TrackFile(
                source_path=file_path,
                title=plex_metadata.title if plex_metadata else file_path.stem,
                artist=plex_metadata.artist if plex_metadata else file_path.parent.name,
                needs_conversion=self._needs_conversion(file_path),
                file_hash=self._calculate_file_hash(file_path),
                rating=plex_metadata.rating if plex_metadata else None,
                plex_guid=plex_metadata.guid if plex_metadata else None
            )
            
            # Process the track
            self._process_track(track)
            
        except Exception as e:
            self.logger.error(f"Failed to process file {file_path}: {e}")

    def handle_deleted_file(self, file_path: Path):
        """Clean up any copies/links when a file is deleted."""
        try:
            # Remove from listening library
            listening_path = self.config.listening_library_dir / file_path.relative_to(self.config.source_dir)
            if listening_path.exists():
                listening_path.unlink()
                
            # Remove from DJ library
            dj_path = self.config.dj_library_dir / file_path.relative_to(self.config.source_dir)
            # For audio files that might have been converted to AIFF
            if file_path.suffix.lower() in ['.flac', '.wav']:
                dj_path = dj_path.with_suffix('.aiff')
                
            if dj_path.exists():
                dj_path.unlink()
                
            # Clean up empty directories
            for path in [listening_path.parent, dj_path.parent]:
                if path.exists() and not any(path.iterdir()):
                    path.rmdir()
                    
        except Exception as e:
            self.logger.error(f"Failed to clean up deleted file {file_path}: {e}")


    def process_rating_changes(self, rating_changes: Dict[str, float]):
        """Process files that have had their ratings changed in Plex."""
        for relative_path, new_rating in rating_changes.items():
            try:
                source_path = self.config.source_dir / relative_path
                if not source_path.exists():
                    self.logger.warning(f"Source file not found: {source_path}")
                    continue

                # Get DJ library path
                dj_path = self.config.dj_library_dir / relative_path
                if self._needs_conversion(source_path):
                    dj_path = dj_path.with_suffix('.aiff')

                if new_rating >= self.config.min_dj_rating / 2:  # Convert from 5-star to 10-point scale
                    # Skip existence check at this level - rely on process_single_file's checks 
                    # This avoids path mismatches due to metadata differences
                    
                    # Just process the file - the internal checks in process_single_file 
                    # will determine if conversion/copying is needed
                    self.logger.info(f"Processing track for DJ library: {relative_path}")
                    self.process_single_file(source_path)
                else:
                    # Rating below threshold - remove from DJ library if present
                    if dj_path.exists():
                        dj_path.unlink()
                        self.logger.info(f"Removed from DJ library: {relative_path} (Rating: {new_rating} stars)")
                        
                        # Clean up empty artist directory if this was the last track
                        artist_dir = dj_path.parent
                        if artist_dir.exists() and not any(artist_dir.iterdir()):
                            artist_dir.rmdir()

            except Exception as e:
                self.logger.error(f"Error processing rating change for {relative_path}: {e}") 
def main():
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

    # Load configuration from standard locations
    config_locations = [
        Path('/home/ravit/.config/deckdex/config.yml'),
        Path('/home/ravit/deckdex/config.yaml'),
        Path(__file__).parent.parent.parent / 'config.yaml'
    ]

    config = None
    for config_path in config_locations:
        try:
            print(f"Trying config path: {config_path}")  # Add this line
            config = Config.load_config(config_path)
            logger.info(f"Loaded configuration from {config_path}")
            break
        except FileNotFoundError:
            continue

    if config is None:
        logger.error("No configuration file found")
        raise FileNotFoundError("No configuration file found in standard locations")

    try:
        # Initialize reorganizer
        reorganizer = LibraryReorganizer(config)
        
        # Run reorganization
        reorganizer.reorganize_library()

    except Exception as e:
        logger.error(f"Failed to initialize: {e}")
        raise

if __name__ == "__main__":
    main()