import sqlite3
from pathlib import Path
from rich.console import Console
from rich.table import Table
from typing import List, Dict

console = Console()

class PlexDBExplorer:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        
    def connect(self):
        """Connect to the Plex database"""
        return sqlite3.connect(self.db_path)
    
    def get_table_schema(self, table_name: str) -> List[tuple]:
        """Get schema for a specific table"""
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(f"PRAGMA table_info({table_name})")
            return cursor.fetchall()
    
    def print_table_schema(self, table_name: str):
        """Print schema for a specific table"""
        schema = self.get_table_schema(table_name)
        
        table = Table(title=f"Schema for {table_name}")
        table.add_column("ID")
        table.add_column("Name")
        table.add_column("Type")
        table.add_column("NotNull")
        table.add_column("Default")
        table.add_column("PK")
        
        for col in schema:
            table.add_row(str(col[0]), col[1], col[2], 
                         str(col[3]), str(col[4]), str(col[5]))
        
        console.print(table)
    
    def sample_tracks(self, limit: int = 3):
        """Get sample tracks with metadata"""
        with self.connect() as conn:
            cursor = conn.cursor()
            
            query = """
            SELECT 
                media_parts.file,
                metadata_items.title,
                metadata_items.*
            FROM metadata_items
            JOIN media_items ON metadata_items.id = media_items.metadata_item_id
            JOIN media_parts ON media_items.id = media_parts.media_item_id
            WHERE metadata_items.metadata_type = 10
            LIMIT ?
            """
            
            cursor.execute(query, (limit,))
            columns = [description[0] for description in cursor.description]
            rows = cursor.fetchall()
            
            # Print results in a nicely formatted table
            table = Table(title=f"Sample Tracks")
            for col in columns:
                table.add_column(col)
                
            for row in rows:
                table.add_row(*[str(cell) for cell in row])
            
            console.print(table)
    
    def examine_track_metadata(self, track_path: str):
        """Examine all metadata for a specific track"""
        with self.connect() as conn:
            cursor = conn.cursor()
            
            # Get basic track metadata
            query = """
            SELECT 
                metadata_items.*,
                media_items.duration,
                media_parts.file
            FROM metadata_items
            JOIN media_items ON metadata_items.id = media_items.metadata_item_id
            JOIN media_parts ON media_items.id = media_parts.media_item_id
            WHERE media_parts.file LIKE ?
            """
            
            cursor.execute(query, (f"%{track_path}%",))
            track_data = cursor.fetchone()
            
            if track_data:
                console.print(f"\n[bold]Track found:[/bold] {track_path}")
                columns = [description[0] for description in cursor.description]
                
                table = Table(title="Track Metadata")
                table.add_column("Field")
                table.add_column("Value")
                
                for col, value in zip(columns, track_data):
                    if value is not None:  # Only show non-null values
                        table.add_row(col, str(value))
                
                console.print(table)
                
                # Get tags for this track
                tag_query = """
                SELECT 
                    tags.tag,
                    tags.tag_type,
                    taggings.created_at
                FROM tags
                JOIN taggings ON tags.id = taggings.tag_id
                WHERE taggings.metadata_item_id = ?
                """
                
                cursor.execute(tag_query, (track_data[0],))  # Using metadata_items.id
                tags = cursor.fetchall()
                
                if tags:
                    tag_table = Table(title="Track Tags")
                    tag_table.add_column("Tag")
                    tag_table.add_column("Type")
                    tag_table.add_column("Created")
                    
                    for tag in tags:
                        tag_table.add_row(*[str(t) for t in tag])
                    
                    console.print(tag_table)
            else:
                console.print(f"[red]No track found matching path: {track_path}[/red]")

def main():
    db_path = Path("/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Plug-in Support/Databases/com.plexapp.plugins.library.db")
    explorer = PlexDBExplorer(db_path)
    
    # Print schema for relevant tables
    tables = ['metadata_items', 'media_items', 'media_parts', 'tags', 'taggings']
    for table in tables:
        explorer.print_table_schema(table)
        print("\n")
    
    # Show sample tracks
    console.print("\n[bold]Sample Tracks:[/bold]")
    explorer.sample_tracks(3)
    
    # Ask for a specific track to examine
    track_path = input("\nEnter a track path to examine (or press Enter to skip): ")
    if track_path:
        explorer.examine_track_metadata(track_path)

if __name__ == "__main__":
    main()