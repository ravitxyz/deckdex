import argparse
import logging
import asyncio
from pathlib import Path
import sys
import time
from typing import Dict, Optional, Tuple
from datetime import datetime

from deckdex.reorganizer import LibraryReorganizer, Config
from deckdex.library_monitor import LibraryMonitor
from deckdex.utils.plex import PlexLibraryReader
from deckdex.metadata.service import MetadataService
from deckdex.models import MusicLibrary, TrackMetadata
from deckdex.file_processor import FileProcessor
from deckdex.playlist.service import PlaylistService
from deckdex.playlist.sync import PlaylistSyncService
from deckdex.playlist.rekordbox import RekordboxXML
from deckdex.identifier.service import TrackIdentifierService
from deckdex.rekordbox import RekordboxExporter
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

async def playlist_sync_async(args: argparse.Namespace):
    """Synchronize playlists between Plex and Rekordbox."""
    setup_logging(args.verbose)
    
    try:
        # Load configuration
        config = load_config(Path(args.config) if args.config else None)
        
        # Initialize services
        db_path = config.db_path.parent / 'playlists.db'
        
        # Create console for output
        console = Console()
        
        with console.status("[bold green]Initializing playlist services..."):
            # Initialize track identifier service
            track_identifier = TrackIdentifierService(str(config.db_path))
            await track_identifier.initialize()
            
            # Initialize playlist service
            playlist_service = PlaylistService(db_path, track_identifier)
            await playlist_service.initialize()
            
            # Initialize Plex reader
            plex_reader = PlexLibraryReader(config.plex_db_path, config.source_dir)
            
            # Initialize Rekordbox XML handler
            rekordbox_xml = RekordboxXML(track_identifier)
            
            # Default Rekordbox XML path
            default_xml_path = config.dj_library_dir / 'rekordbox.xml'
            xml_path = Path(args.rekordbox_xml) if args.rekordbox_xml else default_xml_path
            
            # Initialize sync service
            sync_service = PlaylistSyncService(
                playlist_service=playlist_service,
                track_identifier=track_identifier,
                plex_reader=plex_reader,
                rekordbox_xml=rekordbox_xml,
                rekordbox_xml_path=xml_path
            )
        
        # Determine sync direction
        if args.dry_run:
            logger.info("Running in dry-run mode (no changes will be made)")
            
            # Check Plex playlists
            with console.status("[bold green]Checking Plex playlists..."):
                plex_playlists = await plex_reader.get_playlists()
                console.print(f"Found {len(plex_playlists)} playlists in Plex")
                for playlist in plex_playlists:
                    console.print(f"  - {playlist.title} ({len(playlist.tracks)} tracks)")
            
            # Check Rekordbox playlists if file exists
            if xml_path.exists():
                with console.status("[bold green]Checking Rekordbox playlists..."):
                    rb_playlists = await rekordbox_xml.read_xml(xml_path)
                    console.print(f"Found {len(rb_playlists)} playlists in Rekordbox XML")
                    for playlist in rb_playlists:
                        console.print(f"  - {playlist.name} ({len(playlist.items)} tracks)")
                        
            # Check database playlists
            with console.status("[bold green]Checking database playlists..."):
                plex_db_playlists = await playlist_service.get_playlists_by_source(
                    PlaylistSource.PLEX
                )
                rb_db_playlists = await playlist_service.get_playlists_by_source(
                    PlaylistSource.REKORDBOX
                )
                console.print(f"Found {len(plex_db_playlists)} Plex playlists in database")
                console.print(f"Found {len(rb_db_playlists)} Rekordbox playlists in database")
                
            return
        
        # Perform synchronization based on direction
        if args.direction == 'plex-to-rekordbox':
            with console.status("[bold green]Importing playlists from Plex..."):
                added, updated, failed = await sync_service.sync_from_plex()
                console.print(f"Imported {added} new, updated {updated} existing, {failed} failed")
            
            with console.status("[bold green]Exporting playlists to Rekordbox..."):
                success = await sync_service.sync_to_rekordbox()
                if success:
                    console.print(f"Successfully exported playlists to {xml_path}")
                else:
                    console.print("[bold red]Failed to export playlists to Rekordbox XML")
                
        elif args.direction == 'rekordbox-to-plex':
            if not xml_path.exists():
                console.print(f"[bold red]Rekordbox XML file not found: {xml_path}")
                return
                
            with console.status("[bold green]Importing playlists from Rekordbox..."):
                added, updated, failed = await sync_service.sync_from_rekordbox()
                console.print(f"Imported {added} new, updated {updated} existing, {failed} failed")
            
            # Note: Currently we can't write back to Plex directly
            console.print("[yellow]Note: Writing back to Plex is not yet supported")
            
        else:  # both directions
            with console.status("[bold green]Syncing playlists in both directions..."):
                added, updated, failed, rb_success = await sync_service.sync_all()
                console.print(f"Synced {added} new, updated {updated} existing, {failed} failed")
                
                if rb_success:
                    console.print(f"Successfully exported playlists to {xml_path}")
                else:
                    console.print("[bold red]Failed to export playlists to Rekordbox XML")
        
    except Exception as e:
        logger.error(f"Error synchronizing playlists: {e}")
        raise

def playlist_sync_command(args: argparse.Namespace):
    """Command wrapper for playlist synchronization."""
    asyncio.run(playlist_sync_async(args))

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
    
    # Playlist sync command
    playlist_parser = subparsers.add_parser(
        'playlist-sync',
        help="Synchronize playlists between Plex and Rekordbox"
    )
    playlist_parser.add_argument(
        '--rekordbox-xml',
        help="Path to Rekordbox XML file"
    )
    playlist_parser.add_argument(
        '--direction',
        choices=['plex-to-rekordbox', 'rekordbox-to-plex', 'both'],
        default='both',
        help="Direction of synchronization"
    )
    playlist_parser.add_argument(
        '--dry-run', 
        action='store_true',
        help="Show what would be done without making changes"
    )
    playlist_parser.set_defaults(func=playlist_sync_command)
    
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
    
    # Export Rekordbox XML command
    export_rb_parser = subparsers.add_parser(
        'export-rekordbox',
        help="Export playlists to Rekordbox XML format"
    )
    export_rb_parser.add_argument(
        '--output',
        help="Path to save the XML file (defaults to rekordbox.xml in DJ library)"
    )
    export_rb_parser.add_argument(
        '--playlist-id',
        help="Export a specific playlist (exports all playlists if omitted)"
    )
    export_rb_parser.add_argument(
        '--collection-name',
        default="Deckdex Export",
        help="Name for the collection folder in Rekordbox"
    )
    export_rb_parser.set_defaults(func=export_rekordbox_command)
    
    args = parser.parse_args()
    
    if hasattr(args, 'func'):
        args.func(args)
    else:
        parser.print_help()

async def export_rekordbox_async(args: argparse.Namespace):
    """Export playlists to Rekordbox-compatible XML."""
    setup_logging(args.verbose)
    
    try:
        # Load configuration
        config = load_config(Path(args.config) if args.config else None)
        
        # Initialize console for nice output
        console = Console()
        
        # Determine paths
        db_path = config.db_path.parent / 'playlists.db'
        output_path = Path(args.output) if args.output else config.dj_library_dir / 'rekordbox.xml'
        
        with console.status("[bold green]Initializing exporter..."):
            # Initialize track identifier service
            track_identifier = TrackIdentifierService(str(config.db_path))
            await track_identifier.initialize()
            
            # Initialize the exporter
            exporter = RekordboxExporter(
                db_path=db_path,
                dj_library_path=config.dj_library_dir,
                output_path=output_path,
                track_identifier=track_identifier,
                collection_name=args.collection_name
            )
        
        # Export playlists
        if args.playlist_id:
            with console.status(f"[bold green]Exporting playlist {args.playlist_id}..."):
                xml_path = await exporter.export_playlist(args.playlist_id)
                console.print(f"✅ Successfully exported playlist to [bold]{xml_path}[/bold]")
        else:
            with console.status("[bold green]Exporting all playlists..."):
                xml_path = await exporter.export_all_playlists()
                console.print(f"✅ Successfully exported all playlists to [bold]{xml_path}[/bold]")
        
        # Print instructions for Rekordbox 7.x
        console.print("\n[bold yellow]Import Instructions for Rekordbox 7.x:[/bold yellow]")
        console.print("1. Open Rekordbox 7.x")
        console.print("2. Click [bold]View[/bold] in the top menu, then select [bold]Show Browser[/bold]")
        console.print("3. In the browser sidebar, right-click on [bold]Playlists[/bold]")
        console.print("4. Select [bold]Import Playlist[/bold]")
        console.print("5. Choose [bold]rekordbox xml[/bold] from the dropdown")
        console.print(f"6. Navigate to and select: [bold]{xml_path}[/bold]")
        console.print("7. The playlists should appear in a folder named [bold]Deckdex Export[/bold]")
        
    except Exception as e:
        logger.error(f"Error exporting to Rekordbox XML: {e}")
        raise

def export_rekordbox_command(args: argparse.Namespace):
    """Command wrapper for Rekordbox XML export."""
    asyncio.run(export_rekordbox_async(args))

if __name__ == "__main__":
    main()