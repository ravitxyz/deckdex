import click
from pathlib import Path
import logging
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from datetime import datetime
import sys
from typing import Optional, Dict

from ..models import MusicLibrary
from ..file_processor import FileProcessor
from ..utils.plex import PlexLibraryReader

console = Console()
logger = logging.getLogger(__name__)

class ImportError(Exception):
    """Custom exception for import errors."""
    pass

def setup_logging(verbose: bool) -> None:
    """Configure logging with file and console output."""
    level = logging.DEBUG if verbose else logging.INFO
    log_file = Path.home() / 'dj_library_import.log'
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    
    # Log system information
    logger.debug(f"Python version: {sys.version}")
    logger.debug(f"Running import at: {datetime.now()}")

def get_plex_data(
    plex_db_path: Path,
    music_dir: Path,
    skip_playlists: bool
) -> tuple[Dict[str, int], list]:
    """Get ratings and playlists from Plex."""
    try:
        with console.status("[bold blue]Reading Plex data..."):
            plex_reader = PlexLibraryReader(plex_db_path, music_dir)
            
            # Get ratings
            ratings = plex_reader.get_ratings()
            console.print(f"[green]Found {len(ratings)} rated tracks in Plex")
            
            # Get playlists if requested
            playlists = []
            if not skip_playlists:
                playlists = plex_reader.get_playlists()
                console.print(f"[green]Found {len(playlists)} playlists in Plex")
            
            # Cleanup
            plex_reader.cleanup()
            return ratings, playlists
            
    except Exception as e:
        logger.error(f"Error reading Plex data: {e}")
        raise ImportError(f"Failed to read Plex data: {e}")

def process_files(
    processor: FileProcessor,
    music_dir: Path,
    plex_ratings: Optional[Dict[str, int]] = None,
    dry_run: bool = False
) -> int:
    """Process music files and return count of processed files."""
    processed_count = 0
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("[blue]Scanning music library...", total=None)
        
        for file_path in processor.scan_directory(music_dir):
            try:
                rel_path = file_path.relative_to(music_dir)
                progress.update(task, description=f"Processing {rel_path}")
                
                if metadata := processor.process_file(file_path):
                    # Add Plex rating if available
                    if plex_ratings and str(rel_path) in plex_ratings:
                        metadata.rating = plex_ratings[str(rel_path)]
                    
                    if dry_run:
                        console.print(f"Would import: {metadata.title} by {metadata.artist}")
                    else:
                        processor.library.add_track(file_path, metadata)
                        logger.info(f"Imported: {metadata.title} by {metadata.artist}")
                    
                    processed_count += 1
                    
            except Exception as e:
                logger.error(f"Error processing {file_path}: {e}")
                continue
                
    return processed_count

@click.command()
@click.argument('music_dir', type=click.Path(exists=True, path_type=Path))
@click.argument('db_path', type=click.Path(path_type=Path))
@click.argument('export_dir', type=click.Path(path_type=Path))
@click.option('--dry-run', is_flag=True, help="Show what would be imported without making changes")
@click.option('--skip-plex', is_flag=True, help="Skip importing Plex data")
@click.option('--skip-playlists', is_flag=True, help="Skip importing Plex playlists")
@click.option('--verbose', is_flag=True, help="Enable debug logging")
def import_library(
    music_dir: Path,
    db_path: Path,
    export_dir: Path,
    dry_run: bool,
    skip_plex: bool,
    skip_playlists: bool,
    verbose: bool
):
    """Import music library with Plex ratings and playlists."""
    
    setup_logging(verbose)
    logger.info(f"Starting import from {music_dir}")
    
    try:
        # Initialize library
        library = MusicLibrary(db_path, music_dir, export_dir)
        processor = FileProcessor(library)
        
        # Handle Plex data import
        plex_ratings = {}
        plex_playlists = []
        
        if not skip_plex and PLEX_DB_PATH.exists():
            try:
                plex_ratings, plex_playlists = get_plex_data(
                    PLEX_DB_PATH,
                    music_dir,
                    skip_playlists
                )
            except ImportError as e:
                if not click.confirm("Continue without Plex data?", default=True):
                    return
        
        # Process files
        processed_count = process_files(processor, music_dir, plex_ratings, dry_run)
        
        # Import playlists if we have them
        if plex_playlists and not dry_run and not skip_playlists:
            with console.status("[blue]Importing playlists...") as status:
                for playlist_name, tracks in plex_playlists:
                    try:
                        if dry_run:
                            console.print(f"Would import playlist: {playlist_name}")
                        else:
                            library.create_playlist(playlist_name, tracks)
                            logger.info(f"Imported playlist: {playlist_name}")
                    except Exception as e:
                        logger.error(f"Error importing playlist {playlist_name}: {e}")
        
        # Print summary
        if dry_run:
            console.print("[yellow]Dry run complete. No changes were made.")
        else:
            console.print("[bold green]Import complete!")
        
        console.print(f"\nSummary:")
        console.print(f"Total files processed: {processed_count}")
        if not skip_plex:
            console.print(f"Tracks with Plex ratings: {len(plex_ratings)}")
            if not skip_playlists:
                console.print(f"Playlists imported: {len(plex_playlists)}")
                
    except Exception as e:
        logger.error(f"Fatal error during import: {e}")
        raise click.ClickException(str(e))

if __name__ == '__main__':
    import_library()