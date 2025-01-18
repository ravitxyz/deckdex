import logging
from pathlib import Path
from typing import List, Optional, Tuple
import uuid
from datetime import datetime 
import sqlite3
import hashlib  # Added missing import

from .models import (
    TrackIdentifier, 
    AudioFingerprint,
    TrackLocation,
    TrackIdentificationResult,
    IdentificationMethod,
    ConfidenceLevel
)

from ..models import MusicLibrary

logger = logging.getLogger(__name__)
from ..models import MusicLibrary

logger = logging.getLogger(__name__)

class TrackIdentifierService:
    def __init__(self, library: MusicLibrary):
        self.library = library
        self.logger = logging.getLogger(__name__)

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn: 
            conn.execute("""
                CREATE TABLE IF NOT EXISTS track_identifiers (
                        track_id TEXT PRIMARY_KEY,
                        file_hash TEXT NOT NULL,
                        fingerprint TEXT,
                        created_at TIMESTAMP,
                        last_seen TIMESTAMP,
                        confidence_level TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS track_locations (
                    track_id TEXT,
                    file_path TEXT,
                    timestamp TIMESTAMP,
                    active BOOLEAN,
                    FOREIGN KEY (track_id) REFERENCES track_identifiers(track_id)
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_file_hash 
                ON track_identifiers(file_hash)
            """)
    async def identify_track(self, file_path: Path) -> TrackIdentificationResult:
        """
        Identify a track using multiple methods (hash, fingerprint, path)
        Returns identification result with confidence level
        """
        file_hash = await self._calculate_file_hash(file_path)
        
        # Try to find existing track by hash first
        if track := await self._find_by_hash(file_hash):
            return await self._update_existing_track(track, file_path)
        
        # Generate fingerprint for new track
        fingerprint = await self._generate_fingerprint(file_path)
        
        # Look for similar tracks by fingerprint
        if fingerprint and (similar_track := await self._find_by_fingerprint(fingerprint)):
            return await self._update_existing_track(similar_track, file_path, fingerprint)
        
        # Create new track if no match found
        return await self._create_new_track(file_path, file_hash, fingerprint)

    async def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of file"""
        sha256_hash = hashlib.sha256()
        
        # Read file in chunks to handle large files
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
                
        return sha256_hash.hexdigest()

    async def _generate_fingerprint(self, file_path: Path) -> Optional[AudioFingerprint]:
        """Generate Chromaprint fingerprint"""
        try:
            import subprocess
            
            # Run fpcalc (Chromaprint) to get fingerprint
            result = subprocess.run(
                ["fpcalc", "-raw", str(file_path)],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                duration = float(lines[0].split('=')[1])
                fingerprint = lines[1].split('=')[1]
                
                return AudioFingerprint(
                    fingerprint=fingerprint,
                    duration=duration,
                    sample_rate=44100  # Default for fpcalc
                )
                
        except Exception as e:
            self.logger.error(f"Error generating fingerprint: {e}")
            
        return None

    async def _find_by_hash(self, file_hash: str) -> Optional[TrackIdentifier]:
        """Find track by file hash"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM track_identifiers WHERE file_hash = ?",
                (file_hash,)
            )
            if row := cursor.fetchone():
                return self._row_to_identifier(row)
        return None

    async def _find_by_fingerprint(
        self, 
        fingerprint: AudioFingerprint,
        similarity_threshold: float = 0.85
    ) -> Optional[TrackIdentifier]:
        """Find track by audio fingerprint similarity"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM track_identifiers WHERE fingerprint IS NOT NULL"
            )
            
            # Compare fingerprints for similarity
            for row in cursor:
                stored_track = self._row_to_identifier(row)
                if stored_track.audio_fingerprint:
                    similarity = fingerprint.similarity_score(
                        stored_track.audio_fingerprint
                    )
                    if similarity >= similarity_threshold:
                        return stored_track
                        
        return None

    async def _update_existing_track(
        self,
        track: TrackIdentifier,
        file_path: Path,
        new_fingerprint: Optional[AudioFingerprint] = None
    ) -> TrackIdentificationResult:
        """Update existing track with new location and optional fingerprint"""
        matched_methods = [IdentificationMethod.UUID]
        similarity_scores = {}
        
        # Add new location
        track.add_location(file_path)
        
        # Update fingerprint if provided
        if new_fingerprint:
            track.audio_fingerprint = new_fingerprint
            matched_methods.append(IdentificationMethod.FINGERPRINT)
            # Add similarity score if we matched by fingerprint
            similarity_scores[IdentificationMethod.FINGERPRINT] = 1.0
            
        # Update last seen timestamp
        track.last_seen = datetime.now()
        
        # Save updates
        await self._save_track(track)
        
        return TrackIdentificationResult(
            identifier=track,
            matched_methods=matched_methods,
            is_new=False,
            confidence_level=track.confidence_level,
            similarity_scores=similarity_scores
        )

    async def _create_new_track(
        self,
        file_path: Path,
        file_hash: str,
        fingerprint: Optional[AudioFingerprint]
    ) -> TrackIdentificationResult:
        """Create and save new track"""
        track = TrackIdentifier(
            file_hash=file_hash,
            audio_fingerprint=fingerprint
        )
        
        # Add initial location
        track.add_location(file_path)
        
        # Save new track
        await self._save_track(track)
        
        matched_methods = [IdentificationMethod.HASH]
        if fingerprint:
            matched_methods.append(IdentificationMethod.FINGERPRINT)
            
        return TrackIdentificationResult(
            identifier=track,
            matched_methods=matched_methods,
            is_new=True,
            confidence_level=track.confidence_level
        )

    async def _save_track(self, track: TrackIdentifier):
        """Save track and its locations to database"""
        with sqlite3.connect(self.db_path) as conn:
            # Save track identifier
            conn.execute("""
                INSERT OR REPLACE INTO track_identifiers (
                    track_id, file_hash, fingerprint, created_at,
                    last_seen, confidence_level
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                track.track_id,
                track.file_hash,
                track.audio_fingerprint.fingerprint if track.audio_fingerprint else None,
                track.created_at,
                track.last_seen,
                track.confidence_level.value
            ))
            
            # Save active location
            if current_location := track.current_location():
                conn.execute("""
                    INSERT INTO track_locations (
                        track_id, file_path, timestamp, active
                    ) VALUES (?, ?, ?, ?)
                """, (
                    track.track_id,
                    str(current_location.file_path),
                    current_location.timestamp,
                    current_location.active
                ))

    def _row_to_identifier(self, row: sqlite3.Row) -> TrackIdentifier:
        """Convert database row to TrackIdentifier"""
        # Get locations for track
        locations = []
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM track_locations WHERE track_id = ?",
                (row['track_id'],)
            )
            for loc_row in cursor:
                locations.append(TrackLocation(
                    track_id=loc_row['track_id'],
                    file_path=Path(loc_row['file_path']),
                    timestamp=datetime.fromisoformat(loc_row['timestamp']),
                    active=bool(loc_row['active'])
                ))
        
        # Create fingerprint if exists
        fingerprint = None
        if row['fingerprint']:
            fingerprint = AudioFingerprint()(
                fingerprint=row['fingerprint'],
                duration=0.0,  # We don't store this currently
                sample_rate=44100
            )
        
        return TrackIdentifier(
            track_id=row['track_id'],
            file_hash=row['file_hash'],
            audio_fingerprint=fingerprint,
            created_at=datetime.fromisoformat(row['created_at']),
            last_seen=datetime.fromisoformat(row['last_seen']),
            confidence_level=ConfidenceLevel(row['confidence_level']),
            locations=locations
        )