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
        self.processing_files = set()  # Track files being processed
        # Only watch the source directory
        self.source_dir = Path(config.source_dir)
        
    def on_created(self, event):
        if event.is_directory:
            return
        self._handle_file_event("created", event.src_path)

    def on_modified(self, event):
        if event.is_directory:
            return
            
        try:
            path = Path(event.src_path)
            
            # Only process files in the source directory
            if not self._is_in_source_dir(path):
                return
                
            # Skip if file is already being processed
            if str(path) in self.processing_files:
                return
                
            # Check if this is an audio file we care about
            if path.suffix.lower() not in self.config.supported_formats:
                return
                
            self.logger.info(f"Processing modified event for {path}")
            
            # Add to processing set
            self.processing_files.add(str(path))
            
            try:
                # Process only the changed file
                self.reorganizer.process_single_file(path)
            finally:
                # Always remove from processing set
                self.processing_files.remove(str(path))
                
        except Exception as e:
            self.logger.error(f"Error handling modified event for {event.src_path}: {str(e)}")
            
    def _is_in_source_dir(self, path: Path) -> bool:
        """Check if the path is within the source directory."""
        try:
            path.relative_to(self.source_dir)
            return True
        except ValueError:
            return False

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
            if file_path in self.processing_files:
                return
                
            # Check if this is an audio file we care about
            if path.name.startswith(".") or path.suffix.lower() not in self.config.supported_formats:
                return
                
            self.logger.info(f"Processing {event_type} event for {path}")
            
            # Add to processing set
            self.processing_files.add(file_path)
            
            try:
                # Process only the changed file instead of entire library
                if event_type != "deleted":
                    self.reorganizer.process_single_file(path)
                else:
                    # For deleted files, we might want to clean up any symlinks/copies
                    self.reorganizer.handle_deleted_file(path)
            finally:
                # Always remove from processing set, even if an error occurred
                self.processing_files.remove(file_path)
            
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
        """Check for Plex rating updates and process affected files."""
        try:
            changes = self.plex_reader.get_recent_rating_changes(self.last_check_time)
            if changes:
                self.logger.info(f"Found {len(changes)} tracks with rating changes")
                self.reorganizer.process_rating_changes(changes)
            self.last_check_time = time.time()
        except Exception as e:
            self.logger.error(f"Error checking Plex updates: {e}")

    def start_monitoring(self):
        """Start monitoring both filesystem and Plex database for changes."""
        event_handler = LibraryEventHandler(self.config)
        observer = Observer()
        observer.schedule(event_handler, self.config.source_dir, recursive=True)
        observer.start()
        
        def plex_check_loop():
            while True:
                self.check_plex_updates()
                time.sleep(300)  # Check every 5 minutes
                
        import threading
        threading.Thread(target=plex_check_loop, daemon=True).start()
        
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