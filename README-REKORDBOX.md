# DeckDex to Rekordbox Integration

## Overview

DeckDex includes support for exporting playlists to Rekordbox, allowing DJs to manage their playlists in both Plex/Plexamp and Rekordbox.

## Features

- Export playlists from DeckDex to Rekordbox XML format
- Synchronize ratings, BPM, and other metadata
- Maintain consistent track references across platforms
- Support for Rekordbox 7.x

## Rekordbox 7.x Support

Rekordbox 7.x has different requirements compared to earlier versions:

1. The import process is different (right-click on Playlists → Import Playlist)
2. The file URL format requires `file://localhost/path` format (not `file:///path`)
3. The XML importer is more strict about formatting and structure

## Usage

### Command Line

```bash
# Export all playlists to Rekordbox XML
deckdex export-rekordbox

# Export to a specific location
deckdex export-rekordbox --output /path/to/rekordbox.xml

# Export a specific playlist
deckdex export-rekordbox --playlist-id PLAYLIST_ID

# Customize the collection folder name
deckdex export-rekordbox --collection-name "My Playlists"
```

### Quick Export Script

```bash
# Export all playlists
./export-rekordbox.sh

# Export to a specific location
./export-rekordbox.sh /path/to/rekordbox.xml

# Export a specific playlist
./export-rekordbox.sh /path/to/rekordbox.xml PLAYLIST_ID
```

## Importing into Rekordbox 7.x

1. Open Rekordbox 7.x
2. Click **View** in the top menu, then select **Show Browser**
3. In the browser sidebar, right-click on **Playlists**
4. Select **Import Playlist**
5. Choose **rekordbox xml** from the dropdown
6. Navigate to and select your XML file
7. The playlists should appear in a folder named "Deckdex" (or your custom folder name)

## Detailed Documentation

For more detailed information, see:

- [Rekordbox 7.x Export Guide](docs/REKORDBOX7-EXPORT.md)
- [Playlist Synchronization Plan](src/deckdex/PLAYLIST_SYNC_PLAN.md)
- [Rekordbox Fix Plan](src/PLAYLIST_REKORDBOX_FIX_PLAN.md)

## Testing

To test the export functionality:

```bash
# Run the test export script
uv run src/deckdex/tests/test_rekordbox_export.py --output /tmp/rekordbox_test.xml

# Run the integration test
uv run src/deckdex/tests/playlist/test_rekordbox_integration.py
```