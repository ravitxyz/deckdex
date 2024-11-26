import click
from pathlib import Path
import logging
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from datetime import datetime

from ..models import MusicLibrary
from ..file_processor import FileProcessor
from ..utils.plex import PlexLibraryReader

console = Console()
logger = logging.getLogger(__name__)

PLEX_DB_PATH = Path("/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Plug-in Support/Databases/com.plexapp.plugins.library.db")

@click.command()
@click.argument('music_dir', type=click.Path(exists=True, path_type=Path))
@click.argument('db_path', type=click.Path(path_type=Path))
@click.argument('export_dir', type=click.Path(path_type=Path))
@click.option('--dry-run', is_flag=True, help="Show what would be imported without making changes")
@click.option('--skip-plex', is_flag=True, help="Skip importing Plex data")
@click.option('--skip-playlists', is_flag=True, help="Skip importing Plex playlists")
def import_library(
    music_dir: Path,
    db_path: Path,
    export_dir: Path,
    dry_run: bool,
    skip_plex: bool,
    skip_playlists: bool
):
    """Import music library with Plex ratings and playlists."""
    
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(Path.home() / 'dj_library_import.log'),
            logging.StreamHandler()
        ]
    )
    
    # Initialize library
    library = MusicLibrary(db_path, music_dir, export_dir)
    processor = FileProcessor(library)
    
    # Handle Plex data import
    plex_ratings = {}
    plex_playlists = []
    
    if not skip_plex and PLEX_DB_PATH.exists():
        try:
            with console.status("[bold blue]Reading Plex data..."):
                plex_reader = PlexLibraryReader(PLEX_DB_PATH, music_dir)
                
                # Get ratings
                plex_ratings = plex_reader.get_ratings()
                console.print(f"[green]Found {len(plex_ratings)} rated tracks in Plex")
                
                # Get playlists if requested
                if not skip_playlists:
                    plex_playlists = plex_reader.get_playlists()
                    console.print(f"[green]Found {len(plex_playlists)} playlists in Plex")
                
                # Cleanup temporary files
                plex_reader.cleanup()
                
        except Exception as e:
            logger.error(f"Error reading Plex data: {e}")
            if click.confirm("Continue without Plex data?", default=True):
                skip_plex = True
            else:
                return
    
    # Process files
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("[blue]Scanning music library...", total=None)
        
        for file_path in processor.scan_directory(music_dir):
            rel_path = file_path.relative_to(music_dir)
            progress.update(task, description=f"Processing {rel_path}")
            
            if metadata := processor.process_file(file_path):
                # Add Plex rating if available
                if str(rel_path) in plex_ratings:
                    metadata.rating = plex_ratings[str(rel_path)]
                
                if dry_run:
                    console.print(f"Would import: {metadata.title} by {metadata.artist}")
                else:
                    library.add_track(file_path, metadata)
                    logger.info(f"Imported: {metadata.title} by {metadata.artist}")
        
        # Import playlists if we have them
        if plex_playlists and not dry_run and not skip_playlists:
            progress.add_task("[blue]Importing playlists...", total=len(plex_playlists))
            for playlist_name, tracks in plex_playlists:
                if dry_run:
                    console.print(f"Would import playlist: {playlist_name} ({len(tracks)} tracks)")
                else:
                    library.create_playlist(playlist_name, tracks)
                    logger.info(f"Imported playlist: {playlist_name}")

    if dry_run:
        console.print("[yellow]Dry run complete. No changes were made.")
    else:
        console.print("[bold green]Import complete!")
        
    # Print summary
    total_tracks = len(list(music_dir.rglob('*')))
    console.print(f"\nSummary:")
    console.print(f"Total files scanned: {total_tracks}")
    if not skip_plex:
        console.print(f"Tracks with Plex ratings: {len(plex_ratings)}")
        if not skip_playlists:
            console.print(f"Playlists imported: {len(plex_playlists)}")

if __name__ == '__main__':
    import_library()