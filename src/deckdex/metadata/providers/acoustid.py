from dataclasses import dataclass
from pathlib import Path
import logging
import asyncio
import aiohttp
from typing import Dict, Any, List, Optional
import subprocess
from datetime import datetime
from .base import Provider, ProviderError

@dataclass
class AcoustIDResult:
    """Represents a result from the AcoustID lookup."""
    id: str
    score: float = 0.0
    title: str | None = None
    artist: str | None = None    
    year: str | None = None
    album: str | None = None    
    track_number: str | None = None    
    musicbrainz_id: str | None = None    
    created_at: datetime = datetime.now()

class AcoustIDProvider:
    """Provider for AcoustID audio fingerprinting and metadata lookup"""

    def __init__(self, api_key: str, cache=None):
        self.api_key = api_key
        self.cache = cache
        self.name = "AcoustID"
        self.logger = logging.getLogger(__name__)
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self):
        self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()
            self._session = None

    async def lookup(self, audio_file: Path) -> List[AcoustIDResult]:
        """Lookup metadata for an audio file using AcoustID"""

        if self.cache:
            cache_key = f"acoustid:{audio_file.stem}"
            cached_result = await self.cache.get(cache_key)
            if cached_result:
                self.logger.debug(f"Cache hit for {audio_file.name}")
                return cached_result
        
        try:
            fingerprint, duration = await self._generate_fingerprint(audio_file)
            if not fingerprint:
                raise ValueError(f"Failed to generate fingerprint for {audio_file}")
            
            results = await self._query_acoustid(fingerprint, duration)
            parsed_results = self._parse_results(results)

            if self.cache and parsed_results:
                await self.cache.set(cache_key, parsed_results)

            return parsed_results

        except Exception as e:
            self.logger.error(f"Error looking up {audio_file}: {str(e)}")
            raise

    async def _generate_fingerprint(self, audio_file: Path) -> tuple[str, int]:
        """Generate audio fingerprint using Chromaprint/fpcalc"""
        try:
            # run fpcalc subprocess asynchronously
            proc = await asyncio.create_subprocess_exec(
                'fpcalc', '-json', str(audio_file),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                self.logger.error(f"fpcalc failed: {stderr.decode()}")
                raise RuntimeError(f"Failed to generate fingerprint: {stderr.decode()}")

            result = json.loads(stdout.decode())
            return result['fingerprint'], result['duration']

        except FileNotFoundError:
            self.logger.error(f"fpcalc not found. Please install Chromaprint.")
            raise
        except json.JSONDecodeError:
            self.logger.error(f"Failed to parse fpcalc output")
            raise
        except Exception as e:
            self.logger.error(f"Error generating fingerprint: {str(e)}")


    async def _query_acoustid(self, fingerprint: str, duration: int) -> Dict[str, Any]:
        if not self._session:
            raise RuntimeError("Session not initialized. Use async with context.")

        params = {
            'client': self.api_key,
            'meta': 'recordings releases tracks',
            'fingerprint': fingerprint,
            'duration': str(duration)
        }

        async with self._session.get(
            'http://api.acoustid.org/v2/lookup',
            params=params
        ) as response:
            if response.status != 200:
                error_text = await resonse.text()
                raise RuntimeError(f"AcoustID API error: {error_text}")

            return await respone.json()

    def _parse_results(self, api_response: Dict[str, Any]) -> List[AcoustIDResult]:
        """Parse AcoustID API response into AcoustIDResult object"""

        results = []

        try:
            for result in api_response.get('results', []):
                recordings = result.get('recordings', [])
                if not recordings:
                    continue

            recording = recordings[0] # use first recording (usually best match)

            releases = recording.get('releases', [])
            release = releases[0] if releases else {}

            acoustid_result = AcoustIDResult(
                id=result['id'],
                score=float(result.get('score', 0.0)),
                title=recording.get('title'),
                artist=recording.get('artists', [{}])[0].get('name'),
                album=release.get('title'),
                year=release.get('date', {}).get('year'),
                track_number=release.get('medium', {}).get('track_number'),
                musicbrainz_id=recording.get('id')
            )
            results.append(acoustid_result)

        except Exception as e:
            self.logger.error(f"Error parsing AcoustID results: {str(e)}")
            raise
        return sorted(results, key=lambda x: x.score, reverse=True)

















    
