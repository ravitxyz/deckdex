import click
from pathlib import Path
import logging
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from datetime import datetime
import sys
from typing import Optional, Dict
import sqlite3

from deckdex.models import MusicLibrary, TrackMetadata
from deckdex.file_processor import FileProcessor
from deckdex.config import config

# Optional Plex import
if config.plex_enabled:
    from deckdex.utils.plex import PlexLibraryReader

console = Console()
logger = logging.getLogger(__name__)

@click.command()
@click.argument('music_dir', type=click.Path(exists=True))
@click.argument('db_path', type=click.Path())
@click.argument('export_dir', type=click.Path())
@click.option('--verbose', is_flag=True, help='Enable verbose logging')
@click.option('--dry-run', is_flag=True, help='Show what would be done without making changes')
def import_library(music_dir: str, db_path: str, export_dir: str, verbose: bool, dry_run: bool):
    """Import music library from directory."""
    
    # Configure logging
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    logger.debug(f"Python version: {sys.version}")
    logger.debug(f"Running import at: {datetime.now()}")
    logger.info(f"Starting import from {music_dir}")
    
    try:
        # Initialize components with all required arguments
        library = MusicLibrary(
            db_path=Path(db_path),
            music_dir=Path(music_dir),
            export_dir=Path(export_dir)
        )
        
        processor = FileProcessor(
            source_path=Path(music_dir),
            export_path=Path(export_dir),
            dry_run=dry_run
        )
        
        # Process files
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Scanning files...", total=None)
            
            # Process direct files
            for track_path, metadata in processor.process_directory():
                if not dry_run and metadata:
                    try:
                        library.add_track(track_path=track_path, metadata=metadata)
                        logger.debug(f"Added track: {metadata.title} by {metadata.artist}")
                    except Exception as e:
                        logger.error(f"Failed to add track {track_path}: {str(e)}")
                progress.update(task, advance=1)
            
            # Process Plex data if enabled
            if config.plex_enabled and config.plex_db_path:
                progress.update(task, description="Processing Plex library...")
                plex_reader = PlexLibraryReader(config.plex_db_path)
                for track_path, metadata in plex_reader.read_library():
                    if not dry_run and metadata:
                        try:
                            library.add_track(track_path=track_path, metadata=metadata)
                            logger.debug(f"Added track from Plex: {metadata.title} by {metadata.artist}")
                        except Exception as e:
                            logger.error(f"Failed to add Plex track: {str(e)}")
                    progress.update(task, advance=1)
            
            progress.update(task, description="Import complete!")
            
    except Exception as e:
        logger.error(f"Fatal error during import: {str(e)}")
        raise click.ClickException(str(e))

if __name__ == '__main__':
    import_library()