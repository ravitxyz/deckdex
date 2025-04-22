# Deckdex-Rekordbox Playlist Export Implementation Plan

## Overview

This document outlines the implementation plan for creating a system to export playlists from Deckdex to Rekordbox 7.0.6, ensuring compatibility and proper functionality.

## Requirements

1. Generate Rekordbox-compatible XML files
2. Support both single-playlist and all-playlist exports
3. Maintain proper track references using the existing track identification system
4. Handle file paths correctly with URI formatting
5. Ensure proper UTF-8 encoding and numeric formatting

## Implementation Steps

### 1. Create Core Export Module

**File: `src/deckdex/rekordbox.py`**

#### Class Structure
```python
class RekordboxExporter:
    def __init__(self, db_path, dj_library_path, output_path, collection_name="Deckdex Export"):
        # Initialize paths and connections
    
    def export_all_playlists(self) -> Path:
        # Export all playlists to a single XML file
    
    def export_playlist(self, playlist_id) -> Path:
        # Export a single playlist to an XML file
```

#### Private Helper Methods
```python
def _create_xml_root(self) -> ET.Element:
    # Create root XML structure with proper DJ_PLAYLISTS element
    
def _add_collection_node(self, root) -> ET.Element:
    # Add COLLECTION node for tracks
    
def _add_playlists_node(self, root) -> ET.Element:
    # Add PLAYLISTS node with proper ROOT and folder structure
    
def _fetch_all_tracks(self) -> List[Dict]:
    # Get all tracks from the DJ library
    
def _fetch_playlist_tracks(self, playlist_id) -> List[Dict]:
    # Get tracks for a specific playlist
    
def _fetch_all_playlists(self) -> List[Dict]:
    # Get all playlists from the database
    
def _fetch_playlist(self, playlist_id) -> Dict:
    # Get a specific playlist's details
    
def _add_tracks_to_collection(self, collection_node, tracks) -> Dict:
    # Add tracks to collection and return ID mapping
    
def _add_playlists_to_xml(self, playlists_node, playlists, track_mapping):
    # Add all playlists to the XML
    
def _add_playlist_to_xml(self, playlists_node, playlist, track_mapping):
    # Add a single playlist to the XML
    
def _add_track_element(self, parent, name, value):
    # Helper to add properly formatted elements
    
def _path_to_uri(self, path) -> str:
    # Convert file paths to Rekordbox URI format
    
def _uri_encode_path_segment(self, segment) -> str:
    # Handle special character encoding in paths
    
def _prettify_xml(self, elem) -> str:
    # Format XML for readability and add declaration
```

### 2. Create Command-Line Interface

**File: `src/deckdex/bin/export_playlists.py`**

- Create a script that provides command-line interface for export functionality
- Support options for exporting all playlists or a specific playlist
- Include option to list available playlists
- Allow configuration of paths and output location

### 3. Database Integration

#### Required Schema Access

1. **Tracks Table:**
   - Basic track information: title, artist, album, year, genre
   - Audio properties: bpm, key, duration, bitrate, sample_rate
   - File information: file_path
   - User data: rating, track_number

2. **Playlists Table:**
   - Basic playlist info: id, name, description, created_at, updated_at

3. **Playlist Tracks Table:**
   - Track ordering: position
   - References: playlist_id, track_id

4. **Track Identifiers Table:**
   - For stable track references: track_id, file_hash

5. **Track Locations Table:**
   - For file path tracking: track_id, file_path

### 4. Rekordbox XML Format Implementation

#### Root Structure
```xml
<?xml version="1.0" encoding="UTF-8"?>
<DJ_PLAYLISTS Version="1.0.0">
    <PRODUCT>
        <NAME>Deckdex</NAME>
        <VERSION>1.0.0</VERSION>
        <COMPANY>Deckdex</COMPANY>
    </PRODUCT>
    <COLLECTION Entries="[count]">
        <!-- Tracks here -->
    </COLLECTION>
    <PLAYLISTS>
        <NODE Type="0" Name="ROOT">
            <NODE Type="0" Name="Deckdex Export">
                <!-- Playlists here -->
            </NODE>
        </NODE>
    </PLAYLISTS>
</DJ_PLAYLISTS>
```

#### Track Format
```xml
<TRACK TrackID="1">
    <Name>Track Title</Name>
    <Artist>Artist Name</Artist>
    <Album>Album Name</Album>
    <!-- Additional metadata -->
    <Location>file://localhost/path/to/file.mp3</Location>
    <!-- Audio properties, ratings, etc. -->
</TRACK>
```

#### Playlist Format
```xml
<NODE Type="1" Name="Playlist Name" Entries="[count]">
    <TRACK Key="1"/>
    <TRACK Key="2"/>
    <!-- More tracks -->
</NODE>
```

### 5. Key Implementation Considerations

1. **URI Formatting:**
   - Properly encode file paths as URIs: `file://localhost/path/to/file.mp3`
   - Handle special characters in filenames
   - Ensure cross-platform compatibility (Linux ↔ MacOS)

2. **Numeric Formatting:**
   - Format float values with proper precision (no locale-specific formatting)
   - Convert ratings from Deckdex scale (0-10) to Rekordbox scale (0-255)

3. **Track Reference Handling:**
   - Ensure track references in playlists point to the correct collection entries
   - Handle cases where tracks in playlists aren't in the collection

4. **XML Compatibility:**
   - Properly encode UTF-8 strings
   - Handle XML special characters
   - Add proper XML declaration

### 6. Testing Strategy

1. **Unit Tests:**
   - Test XML generation for correct format
   - Test path to URI conversion for special cases
   - Test numeric formatting

2. **Integration Tests:**
   - Create a small test database with sample data
   - Verify export of single and multiple playlists
   - Validate XML against Rekordbox schema or examples

3. **Manual Verification:**
   - Import generated XML into Rekordbox 7.0.6
   - Verify playlists and tracks appear correctly
   - Test with various file types and path configurations

### 7. Implementation Timeline

1. **Phase 1: Core XML Generation (Day 1)**
   - Implement RekordboxExporter class structure
   - Create basic XML generation functionality
   - Implement path to URI conversion

2. **Phase 2: Database Integration (Day 1-2)**
   - Add database query functionality
   - Implement track and playlist fetching
   - Create track ID mapping system

3. **Phase 3: CLI Interface (Day 2)**
   - Implement command-line interface
   - Add options for different export modes
   - Create playlist listing functionality

4. **Phase 4: Testing and Refinement (Day 2-3)**
   - Create test cases
   - Validate with Rekordbox
   - Refine implementation based on testing

5. **Phase 5: Documentation and Deployment (Day 3)**
   - Create user documentation
   - Add detailed code comments
   - Finalize integration with main Deckdex system

## Database Schema Adaptation

If the database schema does not match the expected format, the following adjustments may be needed:

1. **Query Modifications:**
   - Adapt SQL queries to match actual schema
   - Create appropriate joins to get all needed information

2. **Data Transformation:**
   - Add code to transform database data into expected formats
   - Handle missing fields by providing defaults

## Final Deliverables

1. `rekordbox.py` - Core export functionality
2. `export_playlists.py` - Command-line interface
3. Unit and integration tests
4. Documentation on usage and file format
