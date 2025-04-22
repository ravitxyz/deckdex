"""Rekordbox XML import/export functionality for playlists.

This module handles the reading and writing of Rekordbox XML format
for playlist synchronization, following the official Rekordbox XML
specification.

References:
- /docs/xml_format_list.pdf: Official Rekordbox XML format specification
"""

import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from urllib.parse import quote, unquote

from deckdex.identifier.service import TrackIdentifierService
from deckdex.playlist.models import Playlist, PlaylistItem, PlaylistSource

logger = logging.getLogger(__name__)


class RekordboxXML:
    """Handler for Rekordbox XML import/export."""

    def __init__(self, track_identifier_service: Optional[TrackIdentifierService] = None):
        """Initialize the Rekordbox XML handler.
        
        Args:
            track_identifier_service: Optional service for resolving track identifiers
        """
        self.track_identifier_service = track_identifier_service

    async def read_xml(self, xml_path: Path) -> List[Playlist]:
        """Read playlists from a Rekordbox XML file.
        
        Args:
            xml_path: Path to the XML file
            
        Returns:
            List of playlists in internal format
        """
        if not xml_path.exists():
            logger.error(f"Rekordbox XML file not found: {xml_path}")
            return []
        
        try:
            # Parse the XML file
            tree = ET.parse(xml_path)
            root = tree.getroot()
            
            # Check if this is a valid Rekordbox XML file
            if root.tag != "DJ_PLAYLISTS":
                logger.error(f"Not a valid Rekordbox XML file: {xml_path}")
                return []
            
            # First read all tracks from the collection
            tracks_dict = {}
            collection = root.find("COLLECTION")
            if collection is not None:
                for track_elem in collection.findall("TRACK"):
                    track_id = track_elem.get("TrackID")
                    if not track_id:
                        continue
                    
                    # Store track elements by ID for later reference
                    tracks_dict[track_id] = track_elem
            
            # Now read playlists
            playlists = []
            playlists_root = root.find("PLAYLISTS")
            
            if playlists_root is not None:
                # Process the playlist tree recursively
                self._process_playlist_node(playlists_root, "", tracks_dict, playlists)
            
            logger.info(f"Read {len(playlists)} playlists from {xml_path}")
            return playlists
            
        except ET.ParseError as e:
            logger.error(f"Error parsing Rekordbox XML {xml_path}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error reading Rekordbox XML {xml_path}: {e}")
            return []

    async def _process_playlist_node(
        self, 
        node: ET.Element, 
        parent_path: str, 
        tracks_dict: Dict[str, ET.Element], 
        playlists: List[Playlist]
    ) -> None:
        """Recursively process playlist nodes.
        
        Args:
            node: Current XML node
            parent_path: Path of parent folders
            tracks_dict: Dictionary of tracks by ID
            playlists: List to add playlists to
        """
        # Process all child nodes
        for child in node.findall("NODE"):
            node_type = child.get("Type")
            node_name = child.get("Name", "Unknown")
            
            # Current path including this node if it's a folder
            current_path = parent_path
            if node_type == "0":  # Folder
                folder_name = node_name
                if current_path:
                    current_path = f"{current_path}/{folder_name}"
                else:
                    current_path = folder_name
                
                # Process children of this folder
                await self._process_playlist_node(child, current_path, tracks_dict, playlists)
            
            elif node_type == "1":  # Playlist
                # Create playlist
                playlist = Playlist(
                    name=node_name,
                    source=PlaylistSource.REKORDBOX,
                    description=f"Rekordbox playlist: {current_path}/{node_name}" if current_path else f"Rekordbox playlist: {node_name}"
                )
                
                # Add tracks to playlist
                items = []
                position = 0
                for track_ref in child.findall("TRACK"):
                    key = track_ref.get("Key")
                    if key and key in tracks_dict:
                        track_elem = tracks_dict[key]
                        
                        # Try to get file path
                        file_path = None
                        location = track_elem.get("Location")
                        if location and location.startswith("file:///"):
                            # Handle URL-encoded paths
                            path_str = unquote(location[8:])
                            file_path = Path(path_str)
                        
                        # Try to resolve track ID through file path
                        track_id = None
                        if file_path and self.track_identifier_service:
                            try:
                                track_id = await self.track_identifier_service.identify_by_path(file_path)
                            except Exception as e:
                                logger.error(f"Error identifying track {file_path}: {e}")
                        
                        # If we couldn't get a track ID, use the Rekordbox ID
                        if not track_id:
                            track_id = f"rekordbox:{key}"
                        
                        # Create playlist item
                        item = PlaylistItem(
                            playlist_id=playlist.id,
                            track_id=track_id,
                            position=position,
                            external_id=key
                        )
                        items.append(item)
                        position += 1
                
                # Only add playlists that have tracks
                if items:
                    playlist.items = items
                    playlists.append(playlist)

    async def generate_xml(
        self, 
        playlists: List[Playlist], 
        output_path: Path,
        merge_with_existing: bool = False,
        existing_xml_path: Optional[Path] = None
    ) -> bool:
        """Generate and save Rekordbox XML file for the given playlists.
        
        Args:
            playlists: List of playlists to include
            output_path: Path to save the XML file
            merge_with_existing: Whether to merge with an existing XML file
            existing_xml_path: Path to existing XML file to merge with
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Determine if we should load an existing XML file
            if merge_with_existing:
                if existing_xml_path and existing_xml_path.exists():
                    try:
                        tree = ET.parse(existing_xml_path)
                        root = tree.getroot()
                        logger.info(f"Merging with existing XML file: {existing_xml_path}")
                    except Exception as e:
                        logger.error(f"Error loading existing XML, creating new file: {e}")
                        root = ET.Element("DJ_PLAYLISTS", Version="1.0.0")
                else:
                    logger.warning("No existing XML file found, creating new file")
                    root = ET.Element("DJ_PLAYLISTS", Version="1.0.0")
            else:
                # Create new XML structure
                root = ET.Element("DJ_PLAYLISTS", Version="1.0.0")
            
            # Ensure required sections exist
            collection = root.find("COLLECTION")
            if collection is None:
                collection = ET.SubElement(root, "COLLECTION")
            
            playlists_elem = root.find("PLAYLISTS")
            if playlists_elem is None:
                playlists_elem = ET.SubElement(root, "PLAYLISTS")
            
            # Get existing tracks from collection if merging
            existing_tracks = {}
            if merge_with_existing:
                for track_elem in collection.findall("TRACK"):
                    track_id = track_elem.get("TrackID")
                    if track_id:
                        existing_tracks[track_id] = track_elem
            
            # Track all unique tracks across all playlists
            new_tracks = {}
            track_id_mapping = {}  # Map internal track IDs to Rekordbox IDs
            
            # First pass: collect all tracks and generate/retrieve Rekordbox IDs
            for playlist in playlists:
                for item in playlist.items:
                    # Skip if already processed
                    if item.track_id in track_id_mapping:
                        continue
                    
                    # If we have an external ID from Rekordbox, use it
                    rb_id = None
                    if item.external_id and not item.external_id.startswith("plex:"):
                        rb_id = item.external_id
                    
                    # Otherwise generate a new ID
                    if not rb_id:
                        # Generate a stable hash as ID
                        import hashlib
                        rb_id = f"DPDX{hashlib.md5(item.track_id.encode()).hexdigest()[:8]}"
                    
                    # Store mapping
                    track_id_mapping[item.track_id] = rb_id
                    
                    # If this is a new track (not in existing XML), get metadata
                    if rb_id not in existing_tracks:
                        metadata = await self._get_track_metadata(item.track_id)
                        new_tracks[rb_id] = metadata
            
            # Add new tracks to collection
            for rb_id, metadata in new_tracks.items():
                track_elem = ET.SubElement(collection, "TRACK")
                track_elem.set("TrackID", rb_id)
                
                # Set track attributes from metadata
                for key, value in metadata.items():
                    if value is not None:
                        track_elem.set(key, str(value))
            
            # Find or create the Deckdex folder in playlists
            deckdex_folder = None
            for node in playlists_elem.findall("NODE"):
                if node.get("Name") == "Deckdex" and node.get("Type") == "0":
                    deckdex_folder = node
                    # Clear existing playlists if not merging
                    if not merge_with_existing:
                        for child in list(deckdex_folder):
                            deckdex_folder.remove(child)
                    break
            
            if deckdex_folder is None:
                deckdex_folder = ET.SubElement(playlists_elem, "NODE", Name="Deckdex", Type="0")
            
            # Add each playlist
            for playlist in playlists:
                # Look for existing playlist to update
                playlist_elem = None
                if merge_with_existing:
                    for node in deckdex_folder.findall("NODE"):
                        if node.get("Name") == playlist.name and node.get("Type") == "1":
                            playlist_elem = node
                            # Remove existing tracks
                            for child in list(playlist_elem):
                                playlist_elem.remove(child)
                            break
                
                # Create new playlist if needed
                if playlist_elem is None:
                    playlist_elem = ET.SubElement(deckdex_folder, "NODE", 
                                               Name=playlist.name, 
                                               Type="1", 
                                               KeyType="0")
                
                # Add tracks to playlist
                for item in sorted(playlist.items, key=lambda x: x.position):
                    if item.track_id in track_id_mapping:
                        rb_id = track_id_mapping[item.track_id]
                        ET.SubElement(playlist_elem, "TRACK", Key=rb_id)
            
            # Write the XML file
            tree = ET.ElementTree(root)
            
            # Ensure directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Use pretty printing for better readability
            from xml.dom import minidom
            xml_string = ET.tostring(root, encoding="utf-8")
            pretty_xml = minidom.parseString(xml_string).toprettyxml(indent="  ")
            
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(pretty_xml)
            
            logger.info(f"Successfully wrote Rekordbox XML to {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error generating Rekordbox XML: {e}")
            return False

    async def _get_track_metadata(self, track_id: str) -> Dict[str, Any]:
        """Get track metadata for XML export.
        
        Args:
            track_id: Internal track ID
            
        Returns:
            Dictionary of track attributes following Rekordbox XML specification
        """
        # Default metadata fields
        metadata = {
            "Name": "Unknown Track",
            "Artist": "Unknown Artist",
        }
        
        # If track identifier service is available, get more metadata
        if self.track_identifier_service:
            try:
                # This would need to be implemented in the track identifier service
                track_info = await self.track_identifier_service.get_metadata(track_id)
                if track_info:
                    # Map fields according to Rekordbox XML specification
                    metadata.update({
                        "Name": track_info.get("title", "Unknown Track"),
                        "Artist": track_info.get("artist", "Unknown Artist"),
                    })
                    
                    # Add optional fields if available
                    if track_info.get("album"):
                        metadata["Album"] = track_info["album"]
                    if track_info.get("genre"):
                        metadata["Genre"] = track_info["genre"]
                    if track_info.get("bpm"):
                        metadata["AverageBpm"] = str(track_info["bpm"])
                    if track_info.get("key"):
                        metadata["Tonality"] = track_info["key"]
                    if track_info.get("comment"):
                        metadata["Comments"] = track_info["comment"]
                    if track_info.get("year"):
                        metadata["Year"] = str(track_info["year"])
                    if track_info.get("duration"):
                        # Convert seconds to milliseconds
                        metadata["TotalTime"] = str(int(track_info["duration"] * 1000))
                    
                    # Format file path for Rekordbox with correct URL encoding
                    if track_info.get("file_path"):
                        path_str = str(track_info["file_path"])
                        # Use file://localhost/ format for Rekordbox 7.x
                        if path_str.startswith('/'):
                            # For absolute paths starting with / (Unix/Mac)
                            location = f"file://localhost{quote(path_str)}"
                        else:
                            # For Windows paths or relative paths
                            # Convert to absolute if possible
                            try:
                                abs_path = Path(path_str).resolve()
                                location = f"file://localhost/{quote(str(abs_path))}"
                            except:
                                # Fall back to simple encoding if we can't resolve
                                location = f"file://localhost/{quote(path_str)}"
                        metadata["Location"] = location
            except Exception as e:
                logger.error(f"Error getting metadata for track {track_id}: {e}")
        
        return metadata