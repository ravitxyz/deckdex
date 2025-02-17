import pytest
import asyncio
from pathlib import Path

from deckdex.metadata.providers.acoustid import AcoustIDProvider, AcoustIDResult

@pytest.mark.asyncio
async def test_acoustid_provider_initialization():
    """Test basic provider initialization"""
    provider = AcoustIDProvider(api_key="xctbyUYyHX")
    assert provider.api_key == 'xctbyUYyHX'
    assert provider.name == "AcoustID"
    assert provider.cache is None
    assert provider._session is None

@pytest.mark.asyncio
async def test_context_manager():
    """Test context manager properly initializes and cleans up"""
    provider = AcoustIDProvider(api_key="xctbyUYyHX")

    # session should not exist before context
    assert provider._session is None

    async with provider as p:
        # session should be intialized within context
        assert p._session is not None

    # session shoud be cleaned up after context
    assert provider._session is None


@pytest.mark.asyncio
async def test_cache_initialization():
    """Test that cache is properly initialized"""
    mock_cache = {}
    provider = AcoustIDProvider(api_key="xctbyUYyHX", cache=mock_cache)
    assert provider.cache == mock_cache

if __name__ == "__main__":
    async def main():
        provider = AcoustIDProvider(api_key="test_key")
        print("Testing provider initialization...")
        assert provider.api_key == "test_key"
        assert provider.name == "AcoustID"
        
        print("Testing context manager...")
        async with provider as p:
            assert p._session is not None
            print("Session initialized successfully")
        
        assert provider._session is None
        print("Session cleaned up successfully")
        
        print("All manual tests passed!")

    asyncio.run(main())
