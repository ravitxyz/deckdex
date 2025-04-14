# Deckdex Playlist Sync Implementation Plan
*Last Updated: April 13, 2025*

## Overview

This document outlines the implementation plan for adding playlist synchronization functionality between Plex (via Plexamp) and Rekordbox to the Deckdex project. The goal is to create a robust two-way sync system that maintains playlist integrity across platforms while leveraging the existing track identification infrastructure.

## Core Components

### 1. Playlist Data Models
- Define consistent models for playlist representation
- Support both Plex and Rekordbox-specific metadata
- Track version history and sync status

### 2. Plex Playlist Reader
- Extract playlist structures from Plex database
- Track playlist changes and modifications
- Map Plex track references to internal track identifiers

### 3. Rekordbox Playlist Writer
- Generate compatible Rekordbox XML output
- Support playlist folders and organization
- Handle incremental updates and modifications

### 4. Track Matching Service
- Utilize existing track identification system
- Create reliable mapping between platform-specific IDs
- Handle edge cases (missing tracks, duplicates, etc.)

### 5. Sync Management Service
- Orchestrate synchronization operations
- Track sync status and version history
- Detect and resolve conflicts

## Implementation Steps

### Phase 1: Core Infrastructure (1-2 weeks)

1. **Create Playlist Module Structure**
   ```
   /src/deckdex/
   ├── playlist/
   │   ├── __init__.py
   │   ├── models.py       # Playlist data models
   │   ├── service.py      # Main playlist service
   │   ├── plex.py         # Plex playlist reader
   │   ├── rekordbox.py    # Rekordbox XML handling
   │   └── sync.py         # Sync logic
   ```

2. **Implement Core Playlist Models**
   - Define `PlaylistItem`, `Playlist`, and `PlaylistVersion` classes
   - Implement database schema for persistent storage
   - Add serialization/deserialization utilities

3. **Setup Database Integration**
   - Add playlist tables to existing Deckdex database
   - Implement CRUD operations for playlists
   - Set up version tracking and history

### Phase 2: Plex Integration (1-2 weeks)

1. **Plex Database Connection**
   - Extend existing `PlexLibraryReader` for playlist access
   - Identify necessary Plex database tables and schema
   - Implement connection and query logic

2. **Playlist Extraction**
   - Extract playlist metadata (name, description, etc.)
   - Retrieve track listings and order
   - Map to internal track identifiers

3. **Change Detection**
   - Implement logic to detect playlist changes
   - Add periodic scanning for modifications
   - Create initial playlist snapshots

### Phase 3: Rekordbox Integration (2-3 weeks)

1. **XML Format Analysis**
   - Analyze Rekordbox XML structure and requirements
   - Determine necessary fields and attributes
   - Identify versioning and compatibility concerns

2. **XML Generation**
   - Implement XML writer for Rekordbox format
   - Support proper track references
   - Generate compatible folder structures

3. **Export Functionality**
   - Create configurable export locations
   - Implement automatic export triggers
   - Add manual export capabilities

### Phase 4: Track Matching (1-2 weeks)

1. **ID Mapping System**
   - Build on existing track identification system
   - Implement ID mapping between platforms
   - Handle missing or unmatched tracks

2. **Confidence Scoring**
   - Extend confidence scoring for playlist matches
   - Add manual override capabilities
   - Record match quality metrics

3. **Matching Optimization**
   - Improve matching speed for playlist operations
   - Add caching for frequent operations
   - Implement batch processing for playlists

### Phase 5: Two-Way Sync (2-3 weeks)

1. **Rekordbox Import**
   - Implement XML parser for Rekordbox playlists
   - Extract playlist structure and track references
   - Map to internal representations

2. **Conflict Detection**
   - Identify sync conflicts between platforms
   - Define conflict resolution strategies
   - Implement version comparison

3. **Synchronization Logic**
   - Develop core sync algorithm
   - Implement bidirectional updates
   - Add user-configurable sync preferences

### Phase 6: Testing and Refinement (1-2 weeks)

1. **Test Suite Development**
   - Create unit tests for all components
   - Implement integration tests for sync scenarios
   - Add performance benchmarks

2. **Edge Case Handling**
   - Test with large playlists (1000+ tracks)
   - Handle network interruptions
   - Test with varied track metadata

3. **Performance Optimization**
   - Improve sync speed for large libraries
   - Reduce memory usage
   - Optimize background operations

## Implementation Details

### Database Schema Additions

```sql
-- Playlist table
CREATE TABLE IF NOT EXISTS playlists (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    source TEXT NOT NULL,  -- 'plex' or 'rekordbox'
    external_id TEXT,      -- ID in source system
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    version INTEGER DEFAULT 1,
    is_active BOOLEAN DEFAULT TRUE
);

-- Playlist items (tracks)
CREATE TABLE IF NOT EXISTS playlist_items (
    playlist_id TEXT,
    track_id TEXT,         -- Internal track identifier
    position INTEGER,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    external_id TEXT,      -- ID in source system
    PRIMARY KEY (playlist_id, track_id),
    FOREIGN KEY (playlist_id) REFERENCES playlists(id),
    FOREIGN KEY (track_id) REFERENCES track_identifiers(track_id)
);

-- Sync status tracking
CREATE TABLE IF NOT EXISTS playlist_sync (
    playlist_id TEXT PRIMARY KEY,
    last_plex_sync TIMESTAMP,
    last_rekordbox_sync TIMESTAMP,
    plex_version INTEGER DEFAULT 0,
    rekordbox_version INTEGER DEFAULT 0,
    sync_status TEXT DEFAULT 'pending',  -- 'pending', 'synced', 'conflict'
    FOREIGN KEY (playlist_id) REFERENCES playlists(id)
);

-- Sync history
CREATE TABLE IF NOT EXISTS playlist_sync_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    playlist_id TEXT,
    sync_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source TEXT NOT NULL,  -- 'plex' or 'rekordbox'
    action TEXT NOT NULL,  -- 'create', 'update', 'delete'
    status TEXT NOT NULL,  -- 'success', 'failure'
    details TEXT,
    FOREIGN KEY (playlist_id) REFERENCES playlists(id)
);
```

### Core Data Models

```python
@dataclass
class PlaylistItem:
    playlist_id: str
    track_id: str         # Internal track identifier
    position: int
    added_at: datetime = field(default_factory=datetime.now)
    external_id: Optional[str] = None  # ID in source system

@dataclass
class Playlist:
    id: str = field(default_factory=lambda: str(uuid4()))
    name: str
    description: Optional[str] = None
    source: str  # 'plex' or 'rekordbox'
    external_id: Optional[str] = None  # ID in source system
    items: List[PlaylistItem] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    modified_at: datetime = field(default_factory=datetime.now)
    version: int = 1
    is_active: bool = True

@dataclass
class SyncStatus:
    playlist_id: str
    last_plex_sync: Optional[datetime] = None
    last_rekordbox_sync: Optional[datetime] = None
    plex_version: int = 0
    rekordbox_version: int = 0
    sync_status: str = "pending"  # 'pending', 'synced', 'conflict'
```

### Plex Database Query Examples

```python
def get_playlists_from_plex(self, conn: sqlite3.Connection) -> List[Playlist]:
    """Extract playlists from Plex database."""
    playlists = []
    
    # Query Plex playlists
    cursor = conn.execute("""
        SELECT id, title, summary, updated_at, created_at
        FROM playlist_items
        WHERE metadata_type = 10  -- Audio playlists
    """)
    
    for row in cursor.fetchall():
        plex_id, title, summary, updated_at, created_at = row
        
        # Get playlist items
        cursor_items = conn.execute("""
            SELECT playlistitem.id, playlistitem.item_id, mi.id AS metadata_id, 
                   playlistitem.order_id
            FROM playlistitem
            JOIN metadata_items mi ON playlistitem.item_id = mi.id
            WHERE playlistitem.playlist_id = ?
            ORDER BY playlistitem.order_id
        """, (plex_id,))
        
        items = []
        for item_row in cursor_items.fetchall():
            item_id, metadata_id, plex_metadata_id, position = item_row
            
            # Find corresponding track in our system
            track_id = self._find_track_by_plex_id(plex_metadata_id)
            if track_id:
                items.append(PlaylistItem(
                    playlist_id=str(plex_id),
                    track_id=track_id,
                    position=position,
                    external_id=str(item_id)
                ))
        
        # Create playlist object
        playlist = Playlist(
            name=title,
            description=summary,
            source="plex",
            external_id=str(plex_id),
            items=items,
            created_at=datetime.fromisoformat(created_at),
            modified_at=datetime.fromisoformat(updated_at)
        )
        playlists.append(playlist)
    
    return playlists
```

### Rekordbox XML Generation Example

```python
def generate_rekordbox_xml(self, playlists: List[Playlist]) -> str:
    """Generate Rekordbox XML for playlists."""
    # Create XML structure
    root = ET.Element("DJ_PLAYLISTS", Version="1.0.0")
    collection = ET.SubElement(root, "COLLECTION")
    
    # Add tracks to collection
    track_ids = set()
    for playlist in playlists:
        for item in playlist.items:
            track_ids.add(item.track_id)
    
    # Add unique tracks to collection
    for track_id in track_ids:
        track = self._get_track(track_id)
        if track:
            track_element = ET.SubElement(collection, "TRACK")
            track_element.set("TrackID", track_id)
            track_element.set("Name", track.title)
            track_element.set("Artist", track.artist)
            # Add other track attributes...
    
    # Add playlists
    playlists_element = ET.SubElement(root, "PLAYLISTS")
    folder = ET.SubElement(playlists_element, "NODE", Name="Deckdex", Type="0")
    
    for playlist in playlists:
        playlist_element = ET.SubElement(folder, "NODE", Name=playlist.name, Type="1")
        playlist_element.set("KeyType", "0")
        
        for item in sorted(playlist.items, key=lambda x: x.position):
            track = self._get_track(item.track_id)
            if track:
                track_element = ET.SubElement(playlist_element, "TRACK")
                track_element.set("Key", track_id)
    
    # Convert to XML string
    return ET.tostring(root, encoding="UTF-8", xml_declaration=True)
```

## Integration Points

### With Existing Systems

1. **Track Identification System**
   - Leverage TrackIdentifier for reliable track matching
   - Use confidence scoring for match quality
   - Maintain track location history for path changes

2. **Library Monitor**
   - Add playlist change detection
   - Trigger sync on relevant file changes
   - Update playlists when tracks move

3. **Metadata Service**
   - Use metadata for track matching improvements
   - Ensure consistent track information across platforms
   - Update metadata when track matches are confirmed

### External Systems

1. **Plex Media Server**
   - Read-only access to Plex database
   - Handle Plex library changes
   - Support Plexamp playlist features

2. **Rekordbox**
   - XML import/export compatibility
   - Support for Rekordbox playlist structure
   - Handle Rekordbox collection specifics

## Success Metrics

1. **Core Functionality**
   - 100% playlist track retention during sync
   - Correct order preservation
   - Reliable two-way updates

2. **Performance**
   - Sync time < 10 seconds for average playlists
   - Low CPU usage during background sync
   - Efficient memory usage

3. **Reliability**
   - Error recovery from interrupted syncs
   - Consistent state after multiple sync cycles
   - Correct conflict resolution

## Timeline

- **Week 1-2**: Core data models and database schema
- **Week 3-4**: Plex playlist reader implementation
- **Week 5-7**: Rekordbox XML export functionality
- **Week 8-9**: Track matching enhancements
- **Week 10-12**: Two-way sync implementation
- **Week 13-14**: Testing, optimization, and refinement

## Next Steps

1. Implement core playlist data models
2. Create database schema for playlist storage
3. Build initial Plex playlist reader
4. Begin Rekordbox XML format analysis

This plan will continue to evolve as implementation progresses.
