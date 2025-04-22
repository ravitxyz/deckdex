#!/bin/bash
# Create a minimal Rekordbox XML file based on known working structure

# Path for the reference XML
REF_XML="${HOME}/rekordbox_reference.xml"

echo "Creating reference Rekordbox XML file..."

# Create a minimal XML file with correct format that should work
cat > "$REF_XML" << 'EOL'
<?xml version="1.0" encoding="UTF-8"?>
<DJ_PLAYLISTS Version="1.0.0">
  <COLLECTION>
    <TRACK TrackID="1" Name="Test Track" Artist="Test Artist" Location="file://$(HOME)/Music/test.mp3"/>
  </COLLECTION>
  <PLAYLISTS>
    <NODE Name="ROOT" Type="0">
      <NODE Name="Reference" Type="0">
        <NODE Name="Test Playlist" Type="1" KeyType="0">
          <TRACK Key="1"/>
        </NODE>
      </NODE>
    </NODE>
  </PLAYLISTS>
</DJ_PLAYLISTS>
EOL

# Expand $(HOME) to actual home path
sed -i.bak -e "s|\$(HOME)|$HOME|g" "$REF_XML"
rm "${REF_XML}.bak"

echo "✅ Reference XML created at: $REF_XML"
echo "Try importing this minimal file to see if Rekordbox accepts it."
echo
echo "If this works but our generated file doesn't, we can compare structures."
echo "If neither works, there may be a Rekordbox configuration issue."