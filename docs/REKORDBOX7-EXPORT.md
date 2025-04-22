# Rekordbox 7.x Playlist Export Guide

This guide explains how to export playlists from DeckDex to Rekordbox 7.x.

## Export Features

- Export all playlists or a specific playlist
- Properly formatted XML for Rekordbox 7.x
- Correct file URL format (`file://localhost/path/to/file`)
- Maintains playlist organization in a custom folder
- Includes all track metadata (artist, title, album, genre, BPM, key, etc.)

## Export Methods

### Command Line

Use the `export-rekordbox` command:

```bash
# Export all playlists to default location
deckdex export-rekordbox

# Export to a specific location
deckdex export-rekordbox --output /path/to/rekordbox.xml

# Export a specific playlist
deckdex export-rekordbox --playlist-id PLAYLIST_ID

# Customize the collection folder name
deckdex export-rekordbox --collection-name "My Playlists"
```

### Quick Export Script

For convenience, use the included export script:

```bash
# Export all playlists to ~/rekordbox_export.xml
./export-rekordbox.sh

# Export to a custom location
./export-rekordbox.sh /path/to/rekordbox.xml

# Export a specific playlist
./export-rekordbox.sh /path/to/rekordbox.xml PLAYLIST_ID
```

## Importing into Rekordbox 7.x

Rekordbox 7.x has a different import process than earlier versions:

1. Open Rekordbox 7.x
2. Click **View** in the top menu, then select **Show Browser**
3. In the browser sidebar, right-click on **Playlists**
4. Select **Import Playlist**
5. Choose **rekordbox xml** from the dropdown
6. Navigate to and select your XML file
7. The playlists should appear in a folder named "Deckdex" (or your custom folder name)

## Troubleshooting

If you encounter issues with the import:

1. **Grayed-out XML files**: Verify that the XML format is correct. Use the `test_rekordbox_export.py` script to generate a test file.
2. **Missing tracks**: Check if the file paths in the XML match your actual music files. The Rekordbox exporter uses absolute paths.
3. **Playlists appear empty**: Verify that the track IDs in the playlists match the track IDs in the collection.
4. **Import option missing**: Make sure you're right-clicking on "Playlists" in the browser sidebar, not elsewhere in the interface.

## Important Changes in Rekordbox 7.x

Rekordbox 7.x has several differences compared to earlier versions:

1. The import process is different (right-click on Playlists → Import Playlist)
2. The file URL format requires `file://localhost/path` format (not `file:///path`)
3. The XML importer is more strict about formatting and structure
4. The XML import is only for playlists, not for the entire music collection

## Testing the Exporter

To verify the export functionality without affecting your real playlists:

```bash
# Run the test export script
uv run src/deckdex/tests/test_rekordbox_export.py --output /tmp/rekordbox_test.xml

# Import the test file into Rekordbox using the steps above
```