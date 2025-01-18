import aiohttp
import asyncio
import json
from datetime import datetime

async def test_plex_connection():
    """Test connection to Plex server and list available playlists"""
    
    # Configuration
    SERVER_URL = "http://localhost:32400"
    TOKEN = "89r763HysGzoViPXRPCG"
    
    # Headers required for Plex API
    headers = {
        'X-Plex-Token': TOKEN,
        'Accept': 'application/json'
    }
    
    async with aiohttp.ClientSession(headers=headers) as session:
        # First, test basic server connection
        try:
            async with session.get(f"{SERVER_URL}/identity") as response:
                if response.status == 200:
                    identity = await response.json()
                    print(f"\n✅ Successfully connected to Plex server:")
                    print(f"   Machine Name: {identity['MediaContainer']['machineIdentifier']}")
                else:
                    print(f"❌ Failed to connect to Plex server: Status {response.status}")
                    return
        except Exception as e:
            print(f"❌ Error connecting to Plex server: {e}")
            return

        # Now, let's check for playlists
        try:
            async with session.get(f"{SERVER_URL}/playlists") as response:
                if response.status == 200:
                    data = await response.json()
                    playlists = data['MediaContainer'].get('Metadata', [])
                    
                    print(f"\n📋 Found {len(playlists)} playlists:")
                    for playlist in playlists:
                        print(f"\n   🎵 {playlist['title']}")
                        print(f"      - Type: {playlist.get('playlistType', 'unknown')}")
                        print(f"      - Items: {playlist.get('leafCount', 0)}")
                        
                        # Print all available fields for debugging
                        print("\n      Available fields:")
                        for key, value in playlist.items():
                            print(f"      - {key}: {value}")
                        
                        # Let's look at the first track
                        try:
                            playlist_id = playlist['ratingKey']
                            print(f"\n      First track details:")
                            async with session.get(f"{SERVER_URL}/playlists/{playlist_id}/items") as items_response:
                                if items_response.status == 200:
                                    items_data = await items_response.json()
                                    if items_data['MediaContainer'].get('Metadata'):
                                        first_track = items_data['MediaContainer']['Metadata'][0]
                                        print("\n      Track fields:")
                                        for key, value in first_track.items():
                                            if key != 'Media':  # Skip media array for brevity
                                                print(f"      - {key}: {value}")
                                        
                                        # If we have media info, let's look at the file path
                                        if 'Media' in first_track:
                                            for media in first_track['Media']:
                                                if 'Part' in media:
                                                    for part in media['Part']:
                                                        print(f"      - File: {part.get('file', 'Unknown')}")
                                else:
                                    print(f"      ❌ Error fetching tracks: Status {items_response.status}")
                        except Exception as e:
                            print(f"      ❌ Error fetching track details: {e}")
                else:
                    print(f"❌ Failed to fetch playlists: Status {response.status}")
        except Exception as e:
            print(f"❌ Error fetching playlists: {e}")

if __name__ == "__main__":
    asyncio.run(test_plex_connection())