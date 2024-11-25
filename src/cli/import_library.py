import click
import sqlite3
from pathlib import Path
import logging
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
import shutil
from datetime import datetime

from ..models import MusicLibrary
from ..file_processor import FileProcessor

console = Console()
logger = logging.getLogger(__name__)

PLEX_DB_PATH = Path("/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Plug-in Support/Databases/com.plexapp.plugins.library.db")

def backup_database(db_path: Path) -> None:
    """Create a backup of the database if it exists."""
    if db_path.exists():
        backup_path = db_path.with_suffix(f".backup-{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}")
        shutil.copy2(db_path, backup_path)
        logger.info(f"Created backup of database at {backup_path}")

def get_plex_ratings()