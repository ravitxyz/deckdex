from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import sqlite3
from typing import List, Optional
import subprocess
import hashlib
import logging

logger = logging.getLogger(__name__)

class TrackStage(Enum):
    WARMUP = "warmup"
    BUILDUP = "buildup"
    PEAK = "peak"
    COOLDOWN = "cooldown"

class TrackVibe(Enum):
    CHILL = "chill"
    SOIREE = "soiree"
    GOINGFORIT = "goingforit"
    SPOOKY = "spooky"
    HARD = "hard"

@dataclass
class TrackMetadata:
    file_path: Path
    title: str
    artist: str
    genre: str
    bpm: Optional[float] = None
    key: Optional[str] = None
    stage: Optional[TrackStage] = None
    vibe: Optional[TrackVibe] = None
    energy_level: Optional[int] = None  # 1-10
    rating: Optional[int] = None  # 1-10
    file_hash: Optional[str] = None

class MusicLibrary:
    def __init__(self, db_path: Path, music_dir: Path, export_dir: Path):
        self.db_path = db_path
        self.music_dir = music_dir
        self.export_dir = export_dir
        self.init_db()

    def init_db(self):
        """Initialize SQLite database with schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tracks (
                    file_hash TEXT PRIMARY KEY,
                    file_path TEXT NOT NULL,
                    title TEXT NOT NULL,
                    artist TEXT NOT NULL,
                    genre TEXT,
                    bpm REAL,
                    key TEXT,
                    stage TEXT,
                    vibe TEXT,
                    energy_level INTEGER,
                    rating INTEGER,
                    last_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS playlists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS playlist_tracks (
                    playlist_id INTEGER,
                    track_hash TEXT,
                    position INTEGER,
                    FOREIGN KEY (playlist_id) REFERENCES playlists(id),
                    FOREIGN KEY (track_hash) REFERENCES tracks(file_hash)
                )
            """)

    def calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of file for tracking changes."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def convert_flac_to_aiff(self, flac_path: Path) -> Path:
        """Convert FLAC to AIFF using ffmpeg."""
        aiff_path = self.export_dir / flac_path.with_suffix('.aiff').name
        
        # Ensure export directory exists
        aiff_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert using ffmpeg
        cmd = [
            'ffmpeg', '-i', str(flac_path),
            '-c:a', 'pcm_s16be',  # Use 16-bit PCM for maximum compatibility
            '-f', 'aiff',
            str(aiff_path)
        ]
        
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            return aiff_path
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to convert {flac_path}: {e.stderr.decode()}")
            raise

    def add_track(self, track_path: Path, metadata: TrackMetadata) -> None:
        """Add or update track in the library."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO tracks 
                (file_hash, file_path, title, artist, genre, bpm, key, stage, vibe, energy_level, rating)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                metadata.file_hash,
                str(track_path),
                metadata.title,
                metadata.artist,
                metadata.genre,
                metadata.bpm,
                metadata.key,
                metadata.stage.value if metadata.stage else None,
                metadata.vibe.value if metadata.vibe else None,
                metadata.energy_level,
                metadata.rating
            ))

    def get_tracks_by_vibe(self, vibe: TrackVibe) -> List[TrackMetadata]:
        """Retrieve tracks matching a specific vibe."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT * FROM tracks WHERE vibe = ?
            """, (vibe.value,))
            
            return [self._row_to_metadata(row) for row in cursor.fetchall()]

    def get_tracks_by_stage(self, stage: TrackStage) -> List[TrackMetadata]:
        """Retrieve tracks matching a specific stage."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT * FROM tracks WHERE stage = ?
            """, (stage.value,))
            
            return [self._row_to_metadata(row) for row in cursor.fetchall()]

    def _row_to_metadata(self, row) -> TrackMetadata:
        """Convert database row to TrackMetadata object."""
        return TrackMetadata(
            file_path=Path(row[1]),
            title=row[2],
            artist=row[3],
            genre=row[4],
            bpm=row[5],
            key=row[6],
            stage=TrackStage(row[7]) if row[7] else None,
            vibe=TrackVibe(row[8]) if row[8] else None,
            energy_level=row[9],
            rating=row[10],
            file_hash=row[0]
        )