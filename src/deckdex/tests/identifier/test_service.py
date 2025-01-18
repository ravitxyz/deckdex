import pytest
import asyncio
from pathlib import Path
import tempfile
import shutil
import sqlite3
from unittest.mock import Mock, patch
from datetime import datetime, timedelta
from ...identifier.models import (
    TrackIdentifier,
    AudioFingerprint,
    TrackLocation,
    IdentificationMethod,
    ConfidenceLevel
)
from ...identifier.service import TrackIdentifierService

@pytest.fixture
def temp_db():
    """Create a temporary database for testing"""
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    yield Path(db_path)
    # Cleanup
    import os
    os.close(db_fd)
    os.unlink(db_path)

@pytest.fixture
def temp_music_dir():
    """Create a temporary directory for test audio files"""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    # Cleanup
    shutil.rmtree(temp_dir)

@pytest.fixture
def service(temp_db):
    """Create a track identification service instance"""
    return TrackIdentificationService(temp_db)

@pytest.fixture
def sample_fingerprint():
    """Create a sample audio fingerprint"""
    return AudioFingerprint(
        fingerprint="TEST_FINGERPRINT_DATA",
        duration=180.5,
        sample_rate=44100
    )

@pytest.fixture
def sample_audio_file(temp_music_dir):
    """Create a sample audio file for testing"""
    file_path = temp_music_dir / "test_track.mp3"
    # Create a dummy file with some content
    file_path.write_bytes(b"DUMMY_AUDIO_CONTENT")
    return file_path

class TestTrackIdentificationService:
    @pytest.mark.asyncio
    async def test_identify_new_track(self, service, sample_audio_file):
        """Test identification of a completely new track"""
        result = await service.identify_track(sample_audio_file)
        
        assert result.is_new == True
        assert result.confidence_level == ConfidenceLevel.LOW
        assert IdentificationMethod.HASH in result.matched_methods
        assert result.identifier.current_location().file_path == sample_audio_file

    @pytest.mark.asyncio
    async def test_identify_existing_track_by_hash(
        self, service, sample_audio_file, mocker
    ):
        """Test identification of an existing track by hash"""
        # First identification
        first_result = await service.identify_track(sample_audio_file)
        
        # Second identification of same file
        second_result = await service.identify_track(sample_audio_file)
        
        assert second_result.is_new == False
        assert second_result.identifier.track_id == first_result.identifier.track_id
        assert IdentificationMethod.UUID in second_result.matched_methods

    @pytest.mark.asyncio
    async def test_identify_moved_track(self, service, temp_music_dir):
        """Test identification of a track that has been moved"""
        # Create initial file
        original_path = temp_music_dir / "original.mp3"
        original_path.write_bytes(b"DUMMY_AUDIO_CONTENT")
        
        # First identification
        first_result = await service.identify_track(original_path)
        
        # Move file to new location
        new_path = temp_music_dir / "moved.mp3"
        shutil.move(original_path, new_path)
        
        # Identify at new location
        second_result = await service.identify_track(new_path)
        
        assert second_result.is_new == False
        assert second_result.identifier.track_id == first_result.identifier.track_id
        assert len(second_result.identifier.locations) == 2
        assert not original_path.exists()
        assert new_path.exists()

    @pytest.mark.asyncio
    async def test_identify_by_fingerprint(self, service, sample_audio_file, mocker):
        """Test identification by audio fingerprint when hash doesn't match"""
        # Mock fingerprint generation
        mock_fingerprint = AudioFingerprint(
            fingerprint="TEST_FINGERPRINT",
            duration=180.0,
            sample_rate=44100
        )
        mocker.patch.object(
            service,
            '_generate_fingerprint',
            return_value=mock_fingerprint
        )
        
        # First identification
        first_result = await service.identify_track(sample_audio_file)
        
        # Create slightly modified file (different hash, same content)
        modified_path = sample_audio_file.parent / "modified.mp3"
        modified_path.write_bytes(b"SLIGHTLY_MODIFIED_CONTENT")
        
        # Second identification should match by fingerprint
        second_result = await service.identify_track(modified_path)
        
        assert second_result.is_new == False
        assert second_result.identifier.track_id == first_result.identifier.track_id
        assert IdentificationMethod.FINGERPRINT in second_result.matched_methods

    @pytest.mark.asyncio
    async def test_confidence_levels(self, service, sample_audio_file, mocker):
        """Test confidence level assignment under different scenarios"""
        # Mock fingerprint generation
        mock_fingerprint = AudioFingerprint(
            fingerprint="TEST_FINGERPRINT",
            duration=180.0,
            sample_rate=44100
        )
        mocker.patch.object(
            service,
            '_generate_fingerprint',
            return_value=mock_fingerprint
        )
        
        # Test new track with just hash
        mocker.patch.object(service, '_generate_fingerprint', return_value=None)
        hash_only_result = await service.identify_track(sample_audio_file)
        assert hash_only_result.confidence_level == ConfidenceLevel.LOW
        
        # Test with fingerprint
        mocker.patch.object(
            service,
            '_generate_fingerprint',
            return_value=mock_fingerprint
        )
        fingerprint_result = await service.identify_track(sample_audio_file)
        assert fingerprint_result.confidence_level in (
            ConfidenceLevel.MEDIUM,
            ConfidenceLevel.HIGH
        )

    @pytest.mark.asyncio
    async def test_database_persistence(self, service, sample_audio_file):
        """Test that tracks are properly persisted in the database"""
        # Initial identification
        result = await service.identify_track(sample_audio_file)
        
        # Create new service instance with same DB
        new_service = TrackIdentificationService(service.db_path)
        
        # Try to find same track
        second_result = await new_service.identify_track(sample_audio_file)
        
        assert second_result.identifier.track_id == result.identifier.track_id
        assert not second_result.is_new
        assert len(second_result.identifier.locations) == len(
            result.identifier.locations
        )

    @pytest.mark.asyncio
    async def test_error_handling(self, service, temp_music_dir):
        """Test error handling for various failure scenarios"""
        # Test with non-existent file
        with pytest.raises(FileNotFoundError):
            await service.identify_track(temp_music_dir / "nonexistent.mp3")
        
        # Test with unreadable file
        unreadable_file = temp_music_dir / "unreadable.mp3"
        unreadable_file.touch()
        unreadable_file.chmod(0o000)  # Remove all permissions
        with pytest.raises(PermissionError):
            await service.identify_track(unreadable_file)
        
        # Cleanup
        unreadable_file.chmod(0o666)  # Restore permissions for deletion

    @pytest.mark.asyncio
    async def test_concurrent_identification(self, service, temp_music_dir):
        """Test concurrent identification of multiple files"""
        # Create multiple test files
        files = []
        for i in range(5):
            file_path = temp_music_dir / f"track_{i}.mp3"
            file_path.write_bytes(f"AUDIO_CONTENT_{i}".encode())
            files.append(file_path)
        
        # Identify all files concurrently
        tasks = [service.identify_track(f) for f in files]
        results = await asyncio.gather(*tasks)
        
        # Check results
        assert len(results) == len(files)
        assert len(set(r.identifier.track_id for r in results)) == len(files)  # All unique

    @pytest.mark.asyncio
    async def test_location_history(self, service, temp_music_dir):
        """Test tracking of file location history"""
        # Create and identify initial file
        file_path = temp_music_dir / "track.mp3"
        file_path.write_bytes(b"AUDIO_CONTENT")
        result = await service.identify_track(file_path)
        
        # Move file several times
        paths = []
        for i in range(3):
            new_path = temp_music_dir / f"track_moved_{i}.mp3"
            shutil.copy(file_path, new_path)
            paths.append(new_path)
            result = await service.identify_track(new_path)
        
        # Check location history
        locations = result.identifier.locations
        assert len(locations) == 4  # Original + 3 moves
        assert all(not loc.active for loc in locations[:-1])  # Old locations inactive
        assert locations[-1].active  # Latest location active
        assert str(paths[-1]) == str(locations[-1].file_path)  # Latest path matches

@pytest.fixture
def audio_fingerprint():
    return AudioFingerprint(
        fingerprint="1,2,3,4,5",
        duration=180.5,
        sample_rate=44100
    )

@pytest.fixture
def similar_fingerprint():
    return AudioFingerprint(
        fingerprint="1,2,3,4,6",  # One digit different
        duration=180.5,
        sample_rate=44100
    )

@pytest.fixture
def different_fingerprint():
    return AudioFingerprint(
        fingerprint="7,8,9,10,11",
        duration=190.0,
        sample_rate=44100
    )

class TestAudioFingerprint:
    def test_fingerprint_similarity_identical(self, audio_fingerprint):
        """Test similarity score of identical fingerprints"""
        score = audio_fingerprint.similarity_score(audio_fingerprint)
        assert score == 1.0

    def test_fingerprint_similarity_similar(self, audio_fingerprint, similar_fingerprint):
        """Test similarity score of slightly different fingerprints"""
        score = audio_fingerprint.similarity_score(similar_fingerprint)
        assert 0.8 <= score < 1.0

    def test_fingerprint_similarity_different(self, audio_fingerprint, different_fingerprint):
        """Test similarity score of completely different fingerprints"""
        score = audio_fingerprint.similarity_score(different_fingerprint)
        assert score < 0.5

    def test_fingerprint_different_lengths(self):
        """Test similarity comparison with different length fingerprints"""
        fp1 = AudioFingerprint(
            fingerprint="1,2,3",
            duration=10.0,
            sample_rate=44100
        )
        fp2 = AudioFingerprint(
            fingerprint="1,2,3,4,5",
            duration=10.0,
            sample_rate=44100
        )
        score = fp1.similarity_score(fp2)
        assert 0.0 <= score <= 1.0

    def test_invalid_algorithm_version(self, audio_fingerprint):
        """Test comparing fingerprints with different algorithm versions"""
        other = AudioFingerprint(
            fingerprint="1,2,3,4,5",
            duration=180.5,
            sample_rate=44100,
            algorithm_version="different_version"
        )
        with pytest.raises(ValueError):
            audio_fingerprint.similarity_score(other)

class TestTrackIdentifier:
    @pytest.fixture
    def track_identifier(self):
        return TrackIdentifier(
            file_hash="abc123",
            audio_fingerprint=AudioFingerprint(
                fingerprint="1,2,3,4,5",
                duration=180.5,
                sample_rate=44100
            )
        )

    def test_add_location(self, track_identifier):
        """Test adding new locations and deactivating old ones"""
        # Add first location
        path1 = Path("/test/path1.mp3")
        loc1 = track_identifier.add_location(path1)
        assert loc1.active
        assert loc1.file_path == path1

        # Add second location
        path2 = Path("/test/path2.mp3")
        loc2 = track_identifier.add_location(path2)
        assert loc2.active
        assert not loc1.active  # First location should be deactivated

    def test_current_location(self, track_identifier):
        """Test getting current active location"""
        path1 = Path("/test/path1.mp3")
        path2 = Path("/test/path2.mp3")
        
        track_identifier.add_location(path1)
        track_identifier.add_location(path2)
        
        current = track_identifier.current_location()
        assert current is not None
        assert current.file_path == path2
        assert current.active

    def test_confidence_level_updates(self, track_identifier):
        """Test confidence level updates based on available methods"""
        # Start with hash only
        track_identifier.audio_fingerprint = None
        track_identifier._update_confidence_level()
        assert track_identifier.confidence_level == ConfidenceLevel.LOW

        # Add fingerprint
        track_identifier.update_fingerprint(AudioFingerprint(
            fingerprint="1,2,3,4,5",
            duration=180.5,
            sample_rate=44100
        ))
        assert track_identifier.confidence_level == ConfidenceLevel.HIGH

class TestTrackIdentifierService:
    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing"""
        fd, path = tempfile.mkstemp()
        os.close(fd)
        yield path
        os.unlink(path)

    @pytest.fixture
    def service(self, temp_db):
        library = Mock()
        library.db_path = temp_db
        service = TrackIdentifierService(library)
        service._init_db()
        return service

    @pytest.mark.asyncio
    async def test_identify_new_track(self, service, tmp_path):
        """Test identifying a completely new track"""
        # Create test file
        test_file = tmp_path / "test.mp3"
        test_file.write_bytes(b"test content")

        # Mock fingerprint generation
        with patch.object(service, '_generate_fingerprint') as mock_fp:
            mock_fp.return_value = AudioFingerprint(
                fingerprint="1,2,3,4,5",
                duration=180.5,
                sample_rate=44100
            )
            
            result = await service.identify_track(test_file)
            
            assert result.is_new
            assert IdentificationMethod.HASH in result.matched_methods
            assert IdentificationMethod.FINGERPRINT in result.matched_methods

    @pytest.mark.asyncio
    async def test_identify_existing_track(self, service, tmp_path):
        """Test identifying an existing track by hash"""
        # Create and identify initial file
        test_file = tmp_path / "test.mp3"
        test_file.write_bytes(b"test content")
        
        first_result = await service.identify_track(test_file)
        
        # Create copy with same content
        test_file2 = tmp_path / "test_copy.mp3"
        test_file2.write_bytes(b"test content")
        
        second_result = await service.identify_track(test_file2)
        
        assert not second_result.is_new
        assert first_result.identifier.track_id == second_result.identifier.track_id

    @pytest.mark.asyncio
    async def test_identify_similar_track(self, service, tmp_path):
        """Test identifying a track by fingerprint similarity"""
        # Create and identify initial file
        test_file = tmp_path / "test1.mp3"
        test_file.write_bytes(b"test content 1")
        
        with patch.object(service, '_generate_fingerprint') as mock_fp:
            mock_fp.return_value = AudioFingerprint(
                fingerprint="1,2,3,4,5",
                duration=180.5,
                sample_rate=44100
            )
            first_result = await service.identify_track(test_file)
        
        # Create similar file with different content but similar fingerprint
        test_file2 = tmp_path / "test2.mp3"
        test_file2.write_bytes(b"test content 2")
        
        with patch.object(service, '_generate_fingerprint') as mock_fp:
            mock_fp.return_value = AudioFingerprint(
                fingerprint="1,2,3,4,6",  # Similar but not identical
                duration=180.5,
                sample_rate=44100
            )
            second_result = await service.identify_track(test_file2)
        
        assert not second_result.is_new
        assert IdentificationMethod.FINGERPRINT in second_result.matched_methods