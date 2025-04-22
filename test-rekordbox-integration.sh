#!/bin/bash
# Test script for Rekordbox XML integration

# Make the script executable
chmod +x src/deckdex/tests/playlist/test_rekordbox_integration.py

# Default location for Rekordbox on macOS
DEFAULT_REKORDBOX_PATH="/Applications/rekordbox 6/rekordbox.app/Contents/MacOS/rekordbox"
REKORDBOX_PATH=${REKORDBOX_PATH:-$DEFAULT_REKORDBOX_PATH}

# Output XML location
XML_PATH="${HOME}/deckdex_test.xml"

# Parse command line options
ANALYZE_ONLY=0

while [[ $# -gt 0 ]]; do
    case $1 in
        --analyze)
            ANALYZE_ONLY=1
            shift
            ;;
        --help)
            echo "Usage: $0 [options]"
            echo "Options:"
            echo "  --analyze    Only analyze Rekordbox data directory after import"
            echo "  --help       Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Print banner
echo "=========================================================="
echo "           Rekordbox Integration Test                     "
echo "=========================================================="
echo

# Check for Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python 3 is required but not found"
    exit 1
fi

if [ $ANALYZE_ONLY -eq 1 ]; then
    echo "🔍 Analyzing Rekordbox data directory after import..."
    cd "$(dirname "$0")"  # Change to script directory
    python3 -m src.deckdex.tests.playlist.test_rekordbox_integration --analyze-only
    echo
    echo "Analysis complete! Compare with the previous output to see changes."
    echo "Changes in file sizes and timestamps indicate that Rekordbox stored your playlists."
    exit 0
fi

# Run the test script
echo "🔍 Running integration test..."
cd "$(dirname "$0")"  # Change to script directory
python3 -m src.deckdex.tests.playlist.test_rekordbox_integration \
    --test-xml "$XML_PATH" \
    --launch-rekordbox \
    --rekordbox-path "$REKORDBOX_PATH" \
    --use-real-files \
    --config "$(pwd)/config.yaml"

# Script executed
echo
echo "Test complete! 🎉"
echo
echo "If Rekordbox didn't launch automatically, manually import the XML file:"
echo "  $XML_PATH"
echo
echo "After importing the XML in Rekordbox:"
echo "1. Close Rekordbox"
echo "2. Run this script with --analyze to check for changes:"
echo "   $0 --analyze"