#!/bin/bash
# Script to fix Rekordbox XML format issues

# Get the path to the XML file
XML_PATH="${HOME}/deckdex_test.xml"
if [ ! -f "$XML_PATH" ]; then
    echo "❌ XML file not found at $XML_PATH"
    exit 1
fi

# Create a fixed version
FIXED_PATH="${HOME}/deckdex_test_fixed.xml"

echo "=========================================================="
echo "           Rekordbox XML Format Fixer                     "
echo "=========================================================="
echo

echo "Original XML: $XML_PATH"
echo "Fixed XML will be saved to: $FIXED_PATH"
echo

# Fix the XML file format issues
echo "Fixing XML format..."
# Replace file:/// with file:// for absolute paths (with a leading /)
sed 's#file://///#file://#g' "$XML_PATH" > "$FIXED_PATH"

# Check if the file exists and has content
if [ -s "$FIXED_PATH" ]; then
    echo "✅ Fixed XML created at: $FIXED_PATH"
    echo
    echo "Try importing this fixed XML into Rekordbox."
    echo "If successful, the issue is with the URL format."
    echo
    echo "You can view the fixed XML with: cat $FIXED_PATH"
else
    echo "❌ Failed to create fixed XML file"
    exit 1
fi

# Option to show diff
echo "Show differences between original and fixed XML? (y/n)"
read -r response
if [[ "$response" =~ ^[Yy]$ ]]; then
    echo "Differences:"
    diff -u "$XML_PATH" "$FIXED_PATH" | grep -E "^\+|^\-" | head -20
    echo "..."
fi

echo
echo "Next steps:"
echo "1. Try importing the fixed XML file into Rekordbox"
echo "2. If it works, we've identified the issue with the URL format"
echo "3. If it still doesn't work, the problem may be elsewhere in the XML structure"
echo