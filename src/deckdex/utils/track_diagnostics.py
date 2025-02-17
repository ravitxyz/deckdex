import sqlite3
from pathlib import Path
import logging
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def diagnose_track(source_path: str, dj_lib_path: str, plex_db_path: str):
    """Diagnose why a track might be missing from the DJ library."""
    
    source = Path(source_path)
    dj_lib = Path(dj_lib_path)
    
    logger.info(f"🔍 Diagnosing track: {source.name}")
    
    # 1. Check if source file exists
    if not source.exists():
        logger.error("❌ Source file not found!")
        return
    logger.info("✅ Source file exists")
    
    # 2. Check Plex rating
    try:
        with sqlite3.connect(plex_db_path) as conn:
            cursor = conn.cursor()
            query = """
            SELECT mis.rating
            FROM media_parts mp
            JOIN media_items mi ON mp.media_item_id = mi.id
            JOIN metadata_items m ON mi.metadata_item_id = m.id
            JOIN metadata_item_settings mis ON m.guid = mis.guid
            WHERE mp.file = ?
            """
            cursor.execute(query, (str(source),))
            result = cursor.fetchone()
            
            if not result:
                logger.error("❌ Track not found in Plex database!")
                return
                
            rating = result[0]
            logger.info(f"📊 Plex rating: {rating}/10")
            
            if rating < 6.0:
                logger.error("❌ Rating below threshold (needs 6.0+/10 or 3+ stars)")
                return
            logger.info("✅ Rating meets threshold")
            
    except Exception as e:
        logger.error(f"❌ Error checking Plex rating: {e}")
        return
    
    # 3. Check expected DJ library path
    expected_dj_path = dj_lib / source.relative_to(Path("/home/ravit/drives/tracks"))
    logger.info(f"🎯 Expected DJ library path: {expected_dj_path}")
    
    if not expected_dj_path.exists():
        logger.error("❌ File not found in DJ library!")
        # Check if parent directory exists
        if not expected_dj_path.parent.exists():
            logger.error("❌ Parent directory doesn't exist in DJ library!")
    else:
        logger.info("✅ File exists in DJ library")
        
    # 4. Check file permissions at destination
    parent_dir = expected_dj_path.parent
    while not parent_dir.exists() and parent_dir != dj_lib:
        parent_dir = parent_dir.parent
    
    if parent_dir.exists():
        try:
            logger.info(f"📁 Checking permissions for: {parent_dir}")
            logger.info(f"   Owner: {parent_dir.owner()}")
            logger.info(f"   Group: {parent_dir.group()}")
            logger.info(f"   Mode: {oct(parent_dir.stat().st_mode)[-3:]}")
        except Exception as e:
            logger.error(f"❌ Error checking permissions: {e}")

if __name__ == "__main__":
    track_path = "/home/ravit/drives/tracks/Playa Baghdad - Música Hecha en Casa Vol. 2/Playa Baghdad - Música Hecha en Casa Vol. 2 - 01 Yoshimitsu Dub.aiff"
    dj_lib_path = "/home/ravit/music/dj"
    plex_db_path = "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Plug-in Support/Databases/com.plexapp.plugins.library.db"
    
    diagnose_track(track_path, dj_lib_path, plex_db_path)
