from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List

class ProviderError(Exception):
    """Base class for provider errors"""
    pass

class Provider(ABC):
    """Base class for metadata providers"""

    @abstractmethod
    async def lookup(self, audio_file: Path) -> List[Dict[str, Any]]:
        """Lookup metadata for an audio file"""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name"""
        pass
