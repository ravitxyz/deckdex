# Configuring Plex to Prefer Local File Metadata

To solve metadata mismatch issues between Plex and your DJ library, follow these steps to configure Plex to prioritize metadata from your music files instead of online sources.

## Plex Music Library Agent Settings (Current Plex Version)

1. Open your Plex web interface and log in
2. Go to Settings (wrench icon) → Libraries
3. Find your music library and click the edit (pencil) button
4. Go to the "Advanced" tab

### For Plex's Modern Interface:
5. Look for "Scanner" - ensure it's set to "Plex Music Scanner"
6. For "Agent" - select "Plex Music" 
7. Find "Use embedded tags" and switch it to "Prefer local metadata"
8. Make sure "Prefer local metadata" is enabled/checked
9. Click "Save Changes"

## Refreshing Your Library Metadata

After changing these settings, you need to refresh your library metadata:

1. Go to your music library
2. Click the three-dot menu (⋮)
3. Choose "Scan Library Files" first (to find any new files)
4. After scanning completes, go to three-dot menu again, choose "Refresh Metadata"
5. In the dialog that appears, select:
   - "Refresh all metadata" (or you can specify specific artists if needed)
   - Check "Force refresh" to ensure all metadata is updated
   - Click "Refresh"

## Additional Configuration (For Older Plex Versions)

If you're using an older version of Plex that still has the "Metadata Agents" configuration option:

1. Under "Metadata Agents", click "Show advanced" if needed
2. Move "Local Media Assets" to the TOP of the list by dragging
3. Ensure "Use local metadata" is checked

## Verifying Metadata Source

To verify Plex is using local metadata:

1. Browse to a track in your library
2. Click on the track to view details
3. Click the (i) information icon
4. The display should match the tags in your files, not online metadata

## Important Notes

- This configuration will ensure that Plex uses the tags from your files as the primary metadata source.
- Plex will still try to download additional metadata like artist images and reviews from online sources.
- For the best results, ensure your music files have complete, accurate ID3/metadata tags.
- Plex may still organize files differently than you expect - this only affects metadata display, not physical file organization.
- Our DeckDex tool will properly handle path preservation for Rekordbox regardless of Plex's organization.

## Troubleshooting

If metadata isn't updating after these changes:

1. Make sure the files have proper tags (you can check with tools like Mp3tag)
2. Try the "Analyze" function on specific tracks to force metadata refresh
3. Check Plex logs for any errors related to the music library
4. In rare cases, you may need to recreate the library if settings aren't applying correctly