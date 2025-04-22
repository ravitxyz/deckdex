# Playlist Synchronization Module

This module provides functionality to synchronize playlists between different sources, primarily Plex and Rekordbox.

## Overview

The playlist synchronization system consists of several components:

1. **Core data models** (`models.py`): Defines the internal representation of playlists.
2. **Playlist service** (`service.py`): Handles storage and retrieval of playlists.
3. **Plex adapter** (`plex.py`): Converts between Plex playlists and internal format.
4. **Rekordbox XML handler** (`rekordbox.py`): Handles reading and writing Rekordbox XML.
5. **Synchronization service** (`sync.py`): Orchestrates synchronization between sources.

## Usage

### Command Line

Synchronize playlists using the command line:

```bash
# Full synchronization (both directions)
python -m deckdex playlist-sync

# Plex to Rekordbox only
python -m deckdex playlist-sync --direction plex-to-rekordbox

# Rekordbox to Plex only
python -m deckdex playlist-sync --direction rekordbox-to-plex

# Specify custom Rekordbox XML file
python -m deckdex playlist-sync --rekordbox-xml /path/to/rekordbox.xml

# Dry run (no changes)
python -m deckdex playlist-sync --dry-run
```

### Programmatic Usage

```python
# Initialize services
playlist_service = PlaylistService(db_path, track_identifier)
await playlist_service.initialize()

# Initialize sync service
sync_service = PlaylistSyncService(
    playlist_service=playlist_service,
    track_identifier=track_identifier,
    plex_reader=plex_reader,
    rekordbox_xml=rekordbox_xml,
    rekordbox_xml_path=xml_path
)

# Synchronize from Plex to database
added, updated, failed = await sync_service.sync_from_plex()

# Synchronize from database to Rekordbox
success = await sync_service.sync_to_rekordbox()

# Synchronize from Rekordbox to database
added, updated, failed = await sync_service.sync_from_rekordbox()

# Full two-way synchronization
added, updated, failed, rb_success = await sync_service.sync_all()
```

## Implementation Details

### Playlist Identification

- Plex playlists are identified by their external ID
- Rekordbox playlists are identified by name (case-insensitive)

### Track Identification

The system uses the track identifier service to match tracks across platforms:

1. First tries to match by file path
2. Falls back to using external IDs with platform prefix (e.g., "plex:123", "rekordbox:456")

### Synchronization Strategy

1. **Plex to Rekordbox**:
   - Import playlists from Plex database to internal storage
   - Export playlists from internal storage to Rekordbox XML

2. **Rekordbox to Plex**:
   - Import playlists from Rekordbox XML to internal storage
   - Currently, writing back to Plex is not supported through the API

3. **Two-way sync**:
   - Perform both operations above
   - Handle conflicts in the database based on timestamps

## Limitations

- Direct writing to Plex is not currently supported (Plex doesn't provide a public API for this)
- Smart playlists in Rekordbox may not be properly supported
- Track matching relies on consistent file paths or previous mapping

## Future Improvements

- Add direct Plex write support if an API becomes available
- Improve conflict resolution for two-way synchronization
- Add support for playlist folder organization
- Add proper support for Rekordbox smart playlists
- Enhance track matching with audio fingerprinting