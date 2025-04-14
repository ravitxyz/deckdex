import pytest
import asyncio
from pathlib import Path
import tempfile
import shutil
import sqlite3
from unittest.mock import Mock, patch
from datetime import datetime, timedelta

from deckdex.identifier.models import (
    TrackIdentifier,
    AudioFingerprint,
    TrackLocation,
    IdentificationMethod,
    ConfidenceLevel
)
from deckdex.identifier.service import TrackIdentificationService

@pytest.fixture
def temp_db():
    """Create a temporary database for testing"""
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    yield Path(db_path)
    #