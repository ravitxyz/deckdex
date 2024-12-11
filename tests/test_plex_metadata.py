import sqlite3
from pathlib import Path
from rich.console import Console
from rich.table import Table

console = Console()

def format_rating(rating_value):
    """Convert 10-point rating to display format with both scales"""
    if rating_value is None:
        return 'None'
    
    decimal_rating = float(rating_value)
    stars = decimal_rating / 2  # Convert to 5-star scale
    return f"{stars:.1f}★ ({decimal_rating:.1f})"

def test_plex_query():
    db_path = Path("/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Plug-in Support/Databases/com.plexapp.plugins.library.db")
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        query = """
        SELECT DISTINCT
            mp.file as file_path,
            mi.metadata_item_id,
            m.title,
            m.rating,
            GROUP_CONCAT(t.tag) as genres,
            mi.duration,
            mi.bitrate,
            mi.audio_codec,
            mi.container,
            m.added_at,
            mis.rating
        FROM media_parts mp
        JOIN media_items mi ON mp.media_item_id = mi.id
        JOIN metadata_items m ON mi.metadata_item_id = m.id
        LEFT JOIN taggings tg ON m.id = tg.metadata_item_id
        LEFT JOIN tags t ON tg.tag_id = t.id AND t.tag_type = 1
        LEFT JOIN metadata_item_settings mis ON m.guid = mis.guid
        WHERE mp.file LIKE '%Oho%'
        GROUP BY mp.file
        ORDER BY mp.file
        LIMIT 5
        """
        
        cursor.execute(query)
        rows = cursor.fetchall()
        
        table = Table(title="Tracks in Complete Folder")
        table.add_column("File Name")
        table.add_column("Title")
        table.add_column("Genres")
        table.add_column("Duration")
        table.add_column("Format")
        table.add_column("Added")
        table.add_column("Rating (Stars | 10pt)")
        
        for row in rows:
            file_path, metadata_id, title, rating, genres, duration, bitrate, audio_codec, container, added_at, plex_rating = row
            
            # Convert duration from milliseconds to minutes:seconds
            duration_mins = int(duration / 1000 / 60) if duration else 0
            duration_secs = int((duration / 1000) % 60) if duration else 0
            duration_str = f"{duration_mins}:{duration_secs:02d}"
            
            # Format added_at timestamp
            from datetime import datetime
            added_date = datetime.fromtimestamp(added_at).strftime('%Y-%m-%d') if added_at else 'Unknown'
            
            # Use Plex rating if available, fall back to metadata rating
            rating_value = plex_rating if plex_rating is not None else rating
            rating_display = format_rating(rating_value)
            
            table.add_row(
                Path(file_path).name,
                title or 'Unknown',
                genres or 'None',
                duration_str,
                container or 'Unknown',
                added_date,
                rating_display,
            )
        
        console.print(table)
        
        # Print summary stats
        console.print("\n[bold]Summary:[/bold]")
        console.print(f"Total tracks found: {len(rows)}")
        formats = set(row[8] for row in rows)
        console.print(f"Formats present: {', '.join(formats)}")
        
        # Print rating distribution
        console.print("\n[bold]Rating Distribution:[/bold]")
        ratings = [(row[3], row[10]) for row in rows]
        for metadata_rating, plex_rating in ratings:
            if plex_rating is not None:
                console.print(f"★ {format_rating(plex_rating)}")
            elif metadata_rating is not None:
                console.print(f"★ {format_rating(metadata_rating)}")
            else:
                console.print("★ No rating")

if __name__ == "__main__":
    test_plex_query()