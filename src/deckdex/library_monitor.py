import asyncio
import subprocess
import time
import logging
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import os
import yaml
import resource

from deckdex.reorganizer import LibraryReorganizer, Config
from deckdex.models import MusicLibrary
from deckdex.file_processor import FileProcessor
from deckdex.utils.plex import PlexLibraryReader

class LibraryEventHandler(FileSystemEventHandler):
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.reorganizer = LibraryReorganizer(config)
        self.processing_files = {}  # Change to dict to store timestamps
        self.source_dir = Path(config.source_dir)
        # Add destination directories to ignore
        self.ignored_dirs = {
            Path(config.listening_library_dir),
            Path(config.dj_library_dir)
        }
        
    def _should_process_path(self, path: Path) -> bool:
        """Determine if a path should be processed."""
        try:
            # Clean up old processing timestamps
            current_time = time.time()
            self.processing_files = {
                k: v for k, v in self.processing_files.items() 
                if current_time - v < 300  # Remove entries older than 5 minutes
            }
            
            # Check if path is in any ignored directory
            for ignored_dir in self.ignored_dirs:
                if str(path).startswith(str(ignored_dir)):
                    return False
                    
            # Only process files in source directory
            if not str(path).startswith(str(self.source_dir)):
                return False
                
            # Skip if file is already being processed
            if str(path) in self.processing_files:
                return False
                
            # Check if this is an audio file we care about
            if path.suffix.lower() not in self.config.supported_formats:
                return False
                
            return True
            
        except Exception:
            return False

    def on_created(self, event):
        if event.is_directory:
            return
        self._handle_file_event("created", event.src_path)

    def on_modified(self, event):
        if event.is_directory:
            return
            
        try:
            path = Path(event.src_path)
            
            if not self._should_process_path(path):
                return
                
            # Add debouncing - wait a short time before processing
            time.sleep(0.1)  # 100ms delay
            
            # Check again after delay in case more modifications occurred
            if not self._should_process_path(path):
                return
                
            self.logger.info(f"Processing modified event for {path}")
            
            # Add to processing set with timestamp
            current_time = time.time()
            file_key = str(path)
            
            # Skip if file was processed in the last 5 seconds
            if file_key in self.processing_files:
                last_process_time = self.processing_files[file_key]
                if current_time - last_process_time < 5:  # 5 second cooldown
                    return
            
            self.processing_files[file_key] = current_time
            
            try:
                self.reorganizer.process_single_file(path)
            finally:
                # Keep timestamp in processing_files for cooldown period
                # Will be cleaned up periodically or on next process attempt
                pass
                
        except Exception as e:
            self.logger.error(f"Error handling modified event for {event.src_path}: {str(e)}")

    def on_moved(self, event):
        if event.is_directory:
            return
        self._handle_file_event("moved", event.src_path)

    def on_deleted(self, event):
        if event.is_directory:
            return
        self._handle_file_event("deleted", event.src_path)

    def _handle_file_event(self, event_type: str, file_path: str):
        """Handle file events by processing only the affected file."""
        try:
            path = Path(file_path)
            
            # Skip if file is already being processed
            if str(path) in self.processing_files:
                return
                
            # Check if this is an audio file we care about
            if path.name.startswith(".") or path.suffix.lower() not in self.config.supported_formats:
                return
                
            self.logger.info(f"Processing {event_type} event for {path}")
            
            # Add to processing set with timestamp
            current_time = time.time()
            self.processing_files[str(path)] = current_time
            
            try:
                # Process only the changed file instead of entire library
                if event_type != "deleted":
                    self.reorganizer.process_single_file(path)
                else:
                    # For deleted files, we might want to clean up any symlinks/copies
                    self.reorganizer.handle_deleted_file(path)
            except Exception as e:
                self.logger.error(f"Error processing {event_type} event for {path}: {e}")
            
        except Exception as e:
            self.logger.error(f"Error handling file event {event_type} for {file_path}: {str(e)}")

class LibraryMonitor:
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.last_check_time = time.time()
        self.plex_reader = PlexLibraryReader(config.plex_db_path, config.source_dir)
        self.reorganizer = LibraryReorganizer(config)


    def check_plex_updates(self):
        """Check for Plex updates and missing eligible tracks."""
        try:
            # Check for recent rating changes
            changes = self.plex_reader.get_recent_rating_changes(self.last_check_time)
            if changes:
                self.logger.info(f"Found {len(changes)} tracks with rating changes")
                self.reorganizer.process_rating_changes(changes)
                
            # Every hour, do a full scan for eligible tracks not in DJ library
            if not hasattr(self, 'last_full_scan') or time.time() - self.last_full_scan > 3600:
                eligible_tracks = self.plex_reader.get_eligible_tracks()
                missing_tracks = {}
                
                for rel_path, rating in eligible_tracks.items():
                    if rating >= self.config.min_dj_rating / 2:  # Convert from 5-star to 10-point scale
                        source_path = Path(rel_path)
                        dj_path = self.config.dj_library_dir / rel_path
                        if source_path.suffix.lower() in self.config.convert_formats:
                            dj_path = dj_path.with_suffix('.aiff')
                            
                        if not dj_path.exists():
                            missing_tracks[rel_path] = rating
                            
                if missing_tracks:
                    self.logger.info(f"Found {len(missing_tracks)} rated tracks missing from DJ library")
                    self.reorganizer.process_rating_changes(missing_tracks)
                    
                self.last_full_scan = time.time()
                
            self.last_check_time = time.time()
            
        except Exception as e:
            self.logger.error(f"Error checking Plex updates: {e}")
    def start_monitoring(self):
        """Start monitoring both filesystem and Plex database for changes."""
        logger = logging.getLogger(__name__)
        event_handler = LibraryEventHandler(self.config)
        observer = Observer()
        observer.schedule(event_handler, self.config.source_dir, recursive=True)
        observer.start()
        
        def plex_check_loop():
            while True:
                try:
                    self.check_plex_updates()
                    time.sleep(30)  # Check every 30 seconds instead of 5 minutes
                except Exception as e:
                    logger.error(f"Error in Plex check loop: {e}")
                    time.sleep(5)  # Short sleep on error before retrying
                
        import threading
        plex_thread = threading.Thread(target=plex_check_loop, daemon=True, name="PlexMonitor")
        plex_thread.start()
        
        return observer

def main():
    # Increase system file descriptor limit
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    try:
        # Try to increase to hard limit
        resource.setrlimit(resource.RLIMIT_NOFILE, (hard, hard))
    except ValueError:
        # If we can't set to hard limit, try a reasonable number
        try:
            resource.setrlimit(resource.RLIMIT_NOFILE, (8192, hard))
        except ValueError:
            logging.warning("Could not increase file descriptor limit")
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(Path.home() / 'deckdex.log'),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger(__name__)

    # Load configuration from standard locations
    config_locations = [
        Path('/home/ravit/.config/deckdex/config.yml'),
        Path('/home/ravit/deckdex/config.yaml'),
        Path(__file__).parent.parent.parent / 'config.yaml'
    ]

    config = None
    config_errors = []
    for config_path in config_locations:
        try:
            config = Config.load_config(config_path)
            logger.info(f"Loaded configuration from {config_path}")
            break
        except Exception as e:
            config_errors.append(f"Error loading {config_path}: {str(e)}")
            continue

    if config is None:
        error_details = "\n".join(config_errors)
        logger.error(f"No valid configuration file found:\n{error_details}")
        raise FileNotFoundError("No valid configuration file found")

    try:
        # Start monitoring for changes
        monitor = LibraryMonitor(config)
        observer = monitor.start_monitoring()
        logger.info(f"Now monitoring the library for changes in {config.source_dir}")

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        observer.join()
    except Exception as e:
        logger.error(f"Failed to initialize: {e}")
        raise

if __name__ == "__main__":
    main()