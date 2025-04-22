#!/usr/bin/env bash
# Script to export playlists to Rekordbox XML format
# Usage: ./export-rekordbox.sh [output_file] [playlist_id]

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

# Default paths
OUTPUT_FILE="${1:-$HOME/rekordbox_export.xml}"
PLAYLIST_ID="$2"
COLLECTION_NAME="Deckdex"

echo "=== Rekordbox XML Export Tool ==="
echo "Output file: $OUTPUT_FILE"
if [ -n "$PLAYLIST_ID" ]; then
  echo "Exporting playlist: $PLAYLIST_ID"
  PLAYLIST_ARG="--playlist-id $PLAYLIST_ID"
else
  echo "Exporting all playlists"
  PLAYLIST_ARG=""
fi

# Export playlists
echo "Exporting playlists..."
uv run -m deckdex export-rekordbox --output "$OUTPUT_FILE" $PLAYLIST_ARG --collection-name "$COLLECTION_NAME" -v

if [ $? -eq 0 ]; then
  echo "✅ Export completed successfully"
  echo ""
  echo "=== Import Instructions for Rekordbox 7.x ==="
  echo "1. Open Rekordbox 7.x"
  echo "2. Click View > Show Browser in the top menu"
  echo "3. In the browser sidebar, right-click on Playlists"
  echo "4. Select Import Playlist"
  echo "5. Choose rekordbox xml from the dropdown"
  echo "6. Navigate to and select: $OUTPUT_FILE"
  echo "7. The playlists should appear in a folder named '$COLLECTION_NAME'"
  echo ""
  echo "File saved to: $OUTPUT_FILE"
else
  echo "❌ Export failed"
fi