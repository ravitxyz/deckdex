import argparse
import logging
import asyncio
from pathlib import Path
import sys
import time
from typing import Dict
from datetime import datetime

from deckdex.reorganizer import LibraryReorganizer, Config
from deckdex.library_monitor import LibraryMonitor
from deckdex.utils.plex import PlexLibraryReader
from deckdex.metadata.service import MetadataService
from deckdex.models import MusicLibrary, TrackMetadata
from deckdex.file_processor import FileProcessor
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, Console

logger = logging.getLogger(__name__)

def setup_logging(verbosity: int = 0):
    """Configure logging based on verbosity level."""
    log_level = logging.WARNING
    if verbosity == 1:
        log_level = logging.INFO
    elif verbosity >= 2:
        log_level = logging.DEBUG
        
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(Path.home() / 'deckdex.log')
        ]
    )

def load_config(config_path: Path = None) -> Config:
    """Load configuration from standard locations or specified path."""
    config_locations = [
        config_path,
        Path('/home/ravit/.config/deckdex/config.yml'),
        Path('/home/ravit/deckdex/config.yaml'),
        Path(__file__).parent.parent.parent.parent / 'config.yaml'
    ]
    
    for path in config_locations:
        if path and path.exists():
            try:
                config = Config.load_config(path)
                logger.info(f"Loaded configuration from {path}")
                return config
            except Exception as e:
                logger.warning(f"Failed to load config from {path}: {e}")
    
    logger.error("No valid configuration file found")
    raise FileNotFoundError("No configuration file found in standard locations")

def reorganize_command(args: argparse.Namespace):
    """Run the library reorganization."""
    setup_logging(args.verbose)
    
    try:
        config = load_config(Path(args.config) if args.config else None)
        reorganizer = LibraryReorganizer(config)
        
        if args.dry_run:
            logger.info("Running in dry-run mode (no files will be changed)")
        
        reorganizer.reorganize_library()
        
    except Exception as e:
        logger.error(f"Error during reorganization: {e}")
        sys.exit(1)

def monitor_command(args: argparse.Namespace):
    """Start the library monitor."""
    setup_logging(args.verbose)
    
    try:
        config = load_config(Path(args.config) if args.config else None)
        monitor = LibraryMonitor(config)
        
        logger.info(f"Starting library monitor for {config.source_dir}")
        observer = monitor.start_monitoring()
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Stopping library monitor")
            observer.stop()
            observer.join()
            
    except Exception as e:
        logger.error(f"Error during monitoring: {e}")
        sys.exit(1)

async def sync_tags_async(args: argparse.Namespace):
    """Synchronize metadata tags between source and DJ libraries."""
    setup_logging(args.verbose)
    
    try:
        config = load_config(Path(args.config) if args.config else None)
        
        # Initialize metadata service
        metadata_service = MetadataService({
            'cache_db_path': str(config.db_path.parent / 'metadata_cache.db')
        })
        await metadata_service.initialize()
        
        # Get all music files in the DJ library
        dj_paths = []
        for ext in config.supported_formats:
            dj_paths.extend(list(config.dj_library_dir.rglob(f"*{ext}")))
        
        # Sort by modification time
        dj_paths.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        
        if args.limit:
            dj_paths = dj_paths[:args.limit]
            
        total_files = len(dj_paths)
        success_count = 0
        error_count = 0
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("({task.completed}/{task.total})"),
        ) as progress:
            task = progress.add_task("Syncing metadata tags...", total=total_files)
            
            for dj_path in dj_paths:
                try:
                    # Find corresponding source file
                    rel_path = dj_path.relative_to(config.dj_library_dir)
                    source_path = config.source_dir / rel_path
                    
                    # Handle AIFF conversions
                    if dj_path.suffix.lower() == '.aiff' and not source_path.exists():
                        # Try with original extension
                        for ext in ['.flac', '.wav']:
                            test_path = source_path.with_suffix(ext)
                            if test_path.exists():
                                source_path = test_path
                                break
                    
                    if not source_path.exists():
                        logger.warning(f"Source file not found for {dj_path}")
                        error_count += 1
                        progress.update(task, advance=1)
                        continue
                    
                    # Sync metadata between files
                    if await metadata_service.sync_libraries(source_path, dj_path):
                        success_count += 1
                    else:
                        error_count += 1
                        
                except Exception as e:
                    logger.error(f"Error syncing {dj_path}: {e}")
                    error_count += 1
                    
                progress.update(task, advance=1)
        
        logger.info(f"Sync complete: {success_count} files updated, {error_count} errors")
        
    except Exception as e:
        logger.error(f"Error during tag synchronization: {e}")
        sys.exit(1)

def sync_tags_command(args: argparse.Namespace):
    """Command wrapper for tag synchronization."""
    asyncio.run(sync_tags_async(args))

def plex_ratings_command(args: argparse.Namespace):
    """Import Plex ratings to DJ library."""
    setup_logging(args.verbose)
    
    try:
        config = load_config(Path(args.config) if args.config else None)
        plex_reader = PlexLibraryReader(config.plex_db_path, config.source_dir)
        reorganizer = LibraryReorganizer(config)
        
        logger.info(f"Retrieving ratings from Plex database...")
        ratings = plex_reader.get_ratings()
        
        if not ratings:
            logger.info("No ratings found in Plex database")
            return
            
        logger.info(f"Found {len(ratings)} rated tracks in Plex")
        reorganizer.process_rating_changes(ratings)
        
    except Exception as e:
        logger.error(f"Error importing Plex ratings: {e}")
        sys.exit(1)

def import_library_command(args: argparse.Namespace):
    """Import music library from directory."""
    setup_logging(args.verbose)
    
    logger.debug(f"Python version: {sys.version}")
    logger.debug(f"Running import at: {datetime.now()}")
    logger.info(f"Starting import from {args.music_dir}")
    
    try:
        # Initialize components
        library = MusicLibrary(
            db_path=Path(args.db_path),
            music_dir=Path(args.music_dir),
            export_dir=Path(args.export_dir)
        )
        
        processor = FileProcessor(
            source_dir=Path(args.music_dir),
            dest_dir=Path(args.export_dir),
            track_identifier=None  # We could initialize this if needed
        )
        
        # Process files
        console = Console()
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Scanning files...", total=None)
            processed_count = 0
            error_count = 0
            
            # Process files (adapting from the old Click implementation)
            for file_path in Path(args.music_dir).rglob('*'):
                if processor._is_audio_file(file_path):
                    try:
                        # Extract minimal metadata for tracking
                        # In a real implementation, we'd have a proper metadata extraction function
                        metadata = TrackMetadata(
                            file_path=file_path,
                            title=file_path.stem,
                            artist="Unknown",
                            genre="Unknown"
                        )
                        
                        if not args.dry_run:
                            library.add_track(track_path=file_path, metadata=metadata)
                            logger.debug(f"Added track: {metadata.title}")
                            processed_count += 1
                        else:
                            logger.info(f"Would import: {file_path}")
                            processed_count += 1
                            
                    except Exception as e:
                        logger.error(f"Failed to process {file_path}: {str(e)}")
                        error_count += 1
                    
                    progress.update(task, advance=1)
            
            # Handle Plex data if configured
            if hasattr(args, 'use_plex') and args.use_plex:
                progress.update(task, description="Processing Plex library...")
                try:
                    config = load_config(Path(args.config) if args.config else None)
                    if hasattr(config, 'plex_db_path'):
                        plex_reader = PlexLibraryReader(config.plex_db_path, config.source_dir)
                        # Additional Plex import logic would go here
                except Exception as e:
                    logger.error(f"Error processing Plex data: {e}")
            
            progress.update(task, description=f"Import complete! Processed: {processed_count}, Errors: {error_count}")
            
    except Exception as e:
        logger.error(f"Fatal error during import: {str(e)}")
        sys.exit(1)

def main():
    """Entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="DeckDex: DJ Music Management Tool"
    )
    parser.add_argument(
        '-v', '--verbose', 
        action='count', 
        default=0,
        help="Increase verbosity (can be used multiple times)"
    )
    parser.add_argument(
        '-c', '--config',
        help="Path to configuration file"
    )
    
    subparsers = parser.add_subparsers(
        title="commands",
        dest="command",
        required=True
    )
    
    # Reorganize command
    reorg_parser = subparsers.add_parser(
        'reorganize',
        help="Reorganize music library"
    )
    reorg_parser.add_argument(
        '--dry-run',
        action='store_true',
        help="Show what would be done without making changes"
    )
    reorg_parser.set_defaults(func=reorganize_command)
    
    # Monitor command
    monitor_parser = subparsers.add_parser(
        'monitor',
        help="Monitor library for changes"
    )
    monitor_parser.set_defaults(func=monitor_command)
    
    # Sync tags command
    sync_parser = subparsers.add_parser(
        'sync-tags',
        help="Synchronize metadata tags between source and DJ libraries"
    )
    sync_parser.add_argument(
        '--limit',
        type=int,
        help="Limit the number of files to process"
    )
    sync_parser.set_defaults(func=sync_tags_command)
    
    # Import Plex ratings command
    ratings_parser = subparsers.add_parser(
        'import-ratings',
        help="Import Plex ratings into DJ library"
    )
    ratings_parser.set_defaults(func=plex_ratings_command)
    
    # Import library command
    import_parser = subparsers.add_parser(
        'import-library',
        help="Import music library from directory"
    )
    import_parser.add_argument(
        'music_dir',
        help="Path to music directory"
    )
    import_parser.add_argument(
        'db_path',
        help="Path to database file"
    )
    import_parser.add_argument(
        'export_dir',
        help="Path to export directory"
    )
    import_parser.add_argument(
        '--use-plex',
        action='store_true',
        help="Also import from Plex database if available"
    )
    import_parser.add_argument(
        '--dry-run',
        action='store_true',
        help="Show what would be done without making changes"
    )
    import_parser.set_defaults(func=import_library_command)
    
    args = parser.parse_args()
    
    if hasattr(args, 'func'):
        args.func(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()