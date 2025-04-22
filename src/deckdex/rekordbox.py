"""Rekordbox XML export functionality for playlists.

This module provides specialized export functionality for Rekordbox 7.x,
addressing the specific requirements and formatting needed for proper import.
"""

import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from urllib.parse import quote, unquote
import hashlib

from deckdex.identifier.service import TrackIdentifierService

logger = logging.getLogger(__name__)


class RekordboxExporter:
    """Handles the export of playlists to Rekordbox-compatible XML files."""
    
    def __init__(
        self, 
        db_path: Path, 
        dj_library_path: Path, 
        output_path: Path, 
        track_identifier: Optional[TrackIdentifierService] = None,
        collection_name: str = "Deckdex Export"
    ):
        """Initialize the Rekordbox exporter.
        
        Args:
            db_path: Path to the Deckdex database
            dj_library_path: Path to the DJ library directory
            output_path: Path where the XML file will be saved
            track_identifier: Service for track identification
            collection_name: Name for the collection folder in Rekordbox
        """
        self.db_path = db_path
        self.dj_library_path = dj_library_path
        self.output_path = output_path
        self.track_identifier = track_identifier
        self.collection_name = collection_name
    
    async def export_all_playlists(self) -> Path:
        """Export all playlists to a single XML file.
        
        Returns:
            Path to the generated XML file
        """
        # Fetch all playlists from database
        playlists = await self._fetch_all_playlists()
        
        # Fetch all tracks referenced in these playlists
        tracks = await self._fetch_all_tracks(playlists)
        
        # Generate and save XML
        xml_path = await self._generate_xml(playlists, tracks)
        
        return xml_path
    
    async def export_playlist(self, playlist_id: str) -> Path:
        """Export a single playlist to an XML file.
        
        Args:
            playlist_id: ID of the playlist to export
            
        Returns:
            Path to the generated XML file
        """
        # Fetch the specific playlist
        playlist = await self._fetch_playlist(playlist_id)
        if not playlist:
            logger.error(f"Playlist not found: {playlist_id}")
            raise ValueError(f"Playlist not found: {playlist_id}")
        
        # Fetch tracks for this playlist
        tracks = await self._fetch_playlist_tracks(playlist_id)
        
        # Generate and save XML
        xml_path = await self._generate_xml([playlist], tracks)
        
        return xml_path
    
    async def _generate_xml(self, playlists: List[Dict], tracks: List[Dict]) -> Path:
        """Generate and save Rekordbox XML for the given playlists and tracks.
        
        Args:
            playlists: List of playlist dictionaries
            tracks: List of track dictionaries
            
        Returns:
            Path to the generated XML file
        """
        # Create XML structure
        root = self._create_xml_root()
        
        # Add collection of tracks
        collection_node = self._add_collection_node(root)
        track_mapping = self._add_tracks_to_collection(collection_node, tracks)
        
        # Add playlists
        playlists_node = self._add_playlists_node(root)
        self._add_playlists_to_xml(playlists_node, playlists, track_mapping)
        
        # Save to file with proper XML declaration and formatting
        pretty_xml = self._prettify_xml(root)
        
        # Ensure output directory exists
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.output_path, 'w', encoding='utf-8') as f:
            f.write(pretty_xml)
        
        logger.info(f"Successfully wrote Rekordbox XML to {self.output_path}")
        return self.output_path
    
    def _create_xml_root(self) -> ET.Element:
        """Create root XML structure with proper DJ_PLAYLISTS element.
        
        Returns:
            Root XML element
        """
        root = ET.Element("DJ_PLAYLISTS", Version="1.0.0")
        
        # Add PRODUCT element with software information
        product = ET.SubElement(root, "PRODUCT")
        ET.SubElement(product, "NAME").text = "Deckdex"
        ET.SubElement(product, "VERSION").text = "1.0.0"
        ET.SubElement(product, "COMPANY").text = "Deckdex"
        
        return root
    
    def _add_collection_node(self, root: ET.Element) -> ET.Element:
        """Add COLLECTION node for tracks.
        
        Args:
            root: Root XML element
            
        Returns:
            Collection node element
        """
        collection = ET.SubElement(root, "COLLECTION", Entries="0")
        return collection
    
    def _add_playlists_node(self, root: ET.Element) -> ET.Element:
        """Add PLAYLISTS node with proper ROOT and folder structure.
        
        Args:
            root: Root XML element
            
        Returns:
            Playlists node element
        """
        playlists_node = ET.SubElement(root, "PLAYLISTS")
        
        # Create ROOT node
        root_node = ET.SubElement(playlists_node, "NODE", Type="0", Name="ROOT")
        
        # Create Deckdex folder
        deckdex_folder = ET.SubElement(root_node, "NODE", Type="0", Name=self.collection_name)
        
        return deckdex_folder
    
    async def _fetch_all_playlists(self) -> List[Dict]:
        """Get all playlists from the database.
        
        Returns:
            List of playlist dictionaries
        """
        # This would be implemented to connect to the database
        # For this implementation, we'll simulate with example data
        # In a real implementation, this would query the playlist_service
        
        from deckdex.playlist.service import PlaylistService
        from deckdex.playlist.models import PlaylistSource
        
        playlist_service = PlaylistService(self.db_path, self.track_identifier)
        playlists = await playlist_service.get_playlists_by_source(PlaylistSource.PLEX)
        
        return [playlist.__dict__ for playlist in playlists]
    
    async def _fetch_playlist(self, playlist_id: str) -> Optional[Dict]:
        """Get a specific playlist's details.
        
        Args:
            playlist_id: ID of the playlist
            
        Returns:
            Playlist dictionary if found, None otherwise
        """
        from deckdex.playlist.service import PlaylistService
        
        playlist_service = PlaylistService(self.db_path, self.track_identifier)
        playlist = await playlist_service.get_playlist(playlist_id)
        
        return playlist.__dict__ if playlist else None
    
    async def _fetch_all_tracks(self, playlists: List[Dict]) -> List[Dict]:
        """Get all tracks referenced by the playlists.
        
        Args:
            playlists: List of playlist dictionaries
            
        Returns:
            List of track dictionaries
        """
        # Collect all unique track IDs from all playlists
        track_ids = set()
        for playlist in playlists:
            for item in playlist.get('items', []):
                track_ids.add(item.get('track_id'))
        
        # Fetch track information
        tracks = []
        if self.track_identifier:
            for track_id in track_ids:
                metadata = await self.track_identifier.get_metadata(track_id)
                if metadata:
                    tracks.append(metadata)
        
        return tracks
    
    async def _fetch_playlist_tracks(self, playlist_id: str) -> List[Dict]:
        """Get tracks for a specific playlist.
        
        Args:
            playlist_id: ID of the playlist
            
        Returns:
            List of track dictionaries
        """
        from deckdex.playlist.service import PlaylistService
        
        playlist_service = PlaylistService(self.db_path, self.track_identifier)
        playlist = await playlist_service.get_playlist(playlist_id)
        
        if not playlist:
            return []
        
        # Get track IDs from playlist
        track_ids = [item.track_id for item in playlist.items]
        
        # Fetch track information
        tracks = []
        if self.track_identifier:
            for track_id in track_ids:
                metadata = await self.track_identifier.get_metadata(track_id)
                if metadata:
                    tracks.append(metadata)
        
        return tracks
    
    def _add_tracks_to_collection(self, collection_node: ET.Element, tracks: List[Dict]) -> Dict:
        """Add tracks to collection and return ID mapping.
        
        Args:
            collection_node: Collection XML node
            tracks: List of track dictionaries
            
        Returns:
            Dictionary mapping track IDs to Rekordbox IDs
        """
        track_mapping = {}
        for i, track in enumerate(tracks):
            # Generate a unique ID for Rekordbox
            track_id = track.get('id', track.get('track_id'))
            if not track_id:
                continue
                
            # Use hash for stable IDs across exports
            rb_id = f"DPDX{hashlib.md5(track_id.encode()).hexdigest()[:8]}"
            
            # Create track element
            track_elem = ET.SubElement(collection_node, "TRACK", TrackID=rb_id)
            
            # Add basic metadata
            self._add_track_element(track_elem, "Name", track.get('title', 'Unknown Track'))
            self._add_track_element(track_elem, "Artist", track.get('artist', 'Unknown Artist'))
            
            # Add optional metadata if available
            if 'album' in track:
                self._add_track_element(track_elem, "Album", track['album'])
            if 'genre' in track:
                self._add_track_element(track_elem, "Genre", track['genre'])
            if 'bpm' in track:
                self._add_track_element(track_elem, "AverageBpm", str(track['bpm']))
            if 'key' in track:
                self._add_track_element(track_elem, "Tonality", track['key'])
            if 'comment' in track:
                self._add_track_element(track_elem, "Comments", track['comment'])
            if 'year' in track:
                self._add_track_element(track_elem, "Year", str(track['year']))
            if 'duration' in track:
                # Convert seconds to milliseconds for Rekordbox
                ms = int(float(track['duration']) * 1000)
                self._add_track_element(track_elem, "TotalTime", str(ms))
            
            # Add file path with proper URL formatting
            if 'file_path' in track:
                location = self._path_to_uri(track['file_path'])
                self._add_track_element(track_elem, "Location", location)
            
            # Store mapping for playlist references
            track_mapping[track_id] = rb_id
        
        # Update collection entries count
        collection_node.set("Entries", str(len(tracks)))
        
        return track_mapping
    
    def _add_playlists_to_xml(
        self, 
        playlists_node: ET.Element, 
        playlists: List[Dict], 
        track_mapping: Dict
    ) -> None:
        """Add all playlists to the XML.
        
        Args:
            playlists_node: Playlists XML node
            playlists: List of playlist dictionaries
            track_mapping: Dictionary mapping track IDs to Rekordbox IDs
        """
        for playlist in playlists:
            self._add_playlist_to_xml(playlists_node, playlist, track_mapping)
    
    def _add_playlist_to_xml(
        self, 
        playlists_node: ET.Element, 
        playlist: Dict, 
        track_mapping: Dict
    ) -> None:
        """Add a single playlist to the XML.
        
        Args:
            playlists_node: Playlists XML node
            playlist: Playlist dictionary
            track_mapping: Dictionary mapping track IDs to Rekordbox IDs
        """
        # Create playlist node
        name = playlist.get('name', 'Unnamed Playlist')
        
        # Get playlist items
        items = playlist.get('items', [])
        
        # Sort items by position
        items = sorted(items, key=lambda x: x.get('position', 0))
        
        # Create playlist with track count
        playlist_node = ET.SubElement(playlists_node, "NODE", 
                                 Type="1", 
                                 Name=name,
                                 Entries=str(len(items)))
        
        # Add tracks to playlist
        for item in items:
            track_id = item.get('track_id')
            if track_id and track_id in track_mapping:
                rb_id = track_mapping[track_id]
                ET.SubElement(playlist_node, "TRACK", Key=rb_id)
    
    def _add_track_element(self, parent: ET.Element, name: str, value: Any) -> None:
        """Helper to add properly formatted elements.
        
        Args:
            parent: Parent XML element
            name: Element name
            value: Element value
        """
        if value is not None:
            if isinstance(value, (int, float)):
                value = str(value)
            parent.set(name, value)
    
    def _path_to_uri(self, path: str) -> str:
        """Convert file paths to Rekordbox URI format.
        
        Args:
            path: File path
            
        Returns:
            Properly formatted URI
        """
        path_str = str(path)
        
        # For Rekordbox 7.x, use file://localhost/ format for all paths
        # This is the format that Rekordbox 7.x expects
        if path_str.startswith('/'):
            # For absolute paths starting with / (Unix/Mac)
            return f"file://localhost{quote(path_str)}"
        else:
            # For Windows paths or relative paths
            # Convert to absolute if possible
            try:
                abs_path = Path(path_str).resolve()
                return f"file://localhost/{quote(str(abs_path))}"
            except:
                # Fall back to simple encoding if we can't resolve
                return f"file://localhost/{quote(path_str)}"
    
    def _uri_encode_path_segment(self, segment: str) -> str:
        """Handle special character encoding in paths.
        
        Args:
            segment: Path segment to encode
            
        Returns:
            Encoded segment
        """
        # Ensure proper URI encoding for special characters
        return quote(segment)
    
    def _prettify_xml(self, elem: ET.Element) -> str:
        """Format XML for readability and add declaration.
        
        Args:
            elem: XML element to format
            
        Returns:
            Formatted XML string
        """
        from xml.dom import minidom
        
        # Convert to string
        rough_string = ET.tostring(elem, 'utf-8')
        
        # Parse with minidom for pretty printing
        reparsed = minidom.parseString(rough_string)
        pretty_xml = reparsed.toprettyxml(indent="  ")
        
        # Ensure proper XML declaration
        if not pretty_xml.startswith('<?xml'):
            pretty_xml = '<?xml version="1.0" encoding="UTF-8"?>\n' + pretty_xml
            
        return pretty_xml