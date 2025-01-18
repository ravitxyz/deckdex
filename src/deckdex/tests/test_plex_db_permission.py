from pathlib import Path
from deckdex.utils.plex import PlexLibraryReader
import logging

logging.basicConfig(level=logging.INFO)

def test_plex_access():
    plex_db = Path("/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Plug-in Support/Databases/com.plexapp.plugins.library.db")
    music_dir = Path("/home/ravit/drives/tracks")
    
    try:
        # Initialize PlexLibraryReader (will use ~/.cache/deckdex automatically)
        reader = PlexLibraryReader(plex_db, music_dir)
        
        # Try to get some recent rating changes
        changes = reader.get_recent_rating_changes(0)  # Get all changes
        print(f"\nSuccessfully read {len(changes)} track rating changes from Plex")
        
        # Show a few sample changes if any exist
        for path, rating in list(changes.items())[:3]:
            print(f"Track: {path}, Rating: {rating}/5 stars")
            
        # Clean up
        reader.cleanup()
        print("\nTest completed successfully!")
        
    except Exception as e:
        print(f"\nError accessing Plex database: {e}")
        if isinstance(e, PermissionError):
            print("\nTo fix permission issues, run:")
            print(f"sudo chmod 644 '{plex_db}'")

if __name__ == "__main__":
    test_plex_access()
