from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, Optional

class ProviderError(Exception):
    """Base exception for metadata provider errors."""
    pass

class Provider(ABC):
    """Base class for metadata providers."""
    
    def __init__(self):
        self.name = self.__class__.__name__
    
    @abstractmethod
    async def get_metadata(
        self,
        fingerprint: Optional[str],
        file_path: Path
    ) -> Dict[str, Any]:
        """
        Get metadata for a track.
        
        Args:
            fingerprint: Optional acoustic fingerprint of the track
            file_path: Path to the audio file
            
        Returns:
            Dictionary containing metadata fields
            
        Raises:
            ProviderError: If metadata cannot be retrieved
        """
        pass