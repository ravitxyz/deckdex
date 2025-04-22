import os
from pathlib import Path
import subprocess
import logging
from rich.console import Console
from rich.progress import Progress
import shutil
import hashlib
from mutagen import File as MutagenFile
from datetime import datetime
from typing import Optional, Tuple

console = Console()

def setup_logging():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(f'flac_conversion_test_{timestamp}.log'),
            logging.StreamHandler()
        ]
    )

def find_flac_files(source_dir: Path, limit: int = 3) -> list[Path]:
    """Find FLAC files in the source directory, limited to specified number."""
    flac_files = []
    for root, _, files in os.walk(source_dir):
        for file in files:
            # Skip hidden files and macOS metadata files
            if file.startswith('.') or '/.' in root:
                continue
                
            if file.lower().endswith('.flac'):
                flac_files.append(Path(root) / file)
                if len(flac_files) >= limit:
                    return flac_files
    return flac_files
def verify_audio_file(file_path: Path) -> dict:
    """Verify audio file and return its properties."""
    try:
        audio = MutagenFile(file_path)
        if audio is None:
            return {"valid": False, "error": "Could not read audio file"}
        
        return {
            "valid": True,
            "duration": audio.info.length if hasattr(audio.info, 'length') else None,
            "sample_rate": audio.info.sample_rate if hasattr(audio.info, 'sample_rate') else None,
            "channels": audio.info.channels if hasattr(audio.info, 'channels') else None
        }
    except Exception as e:
        return {"valid": False, "error": str(e)}

def find_cover_art(audio_file_path: Path) -> Optional[Path]:
    """Find cover art in the directory of the audio file."""
    directory = audio_file_path.parent
    cover_names = ['cover', 'folder', 'album', 'front', 'artwork', 'art']
    extensions = ['.jpg', '.jpeg', '.png']
    
    # Look for standard cover art filenames
    for name in cover_names:
        for ext in extensions:
            cover_path = directory / f"{name}{ext}"
            if cover_path.exists():
                logging.debug(f"Found cover art: {cover_path}")
                return cover_path
    
    # If no standard filename found, look for any image file
    for ext in extensions:
        for img_path in directory.glob(f"*{ext}"):
            logging.debug(f"Found potential cover art: {img_path}")
            return img_path
            
    return None

def convert_flac_to_aiff(source_file: Path, dest_dir: Path) -> tuple[bool, str]:
    """Convert FLAC to AIFF using ffmpeg while preserving artwork."""
    try:
        dest_file = dest_dir / f"{source_file.stem}.aiff"
        
        # Ensure destination directory exists
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        # First, check if source file has embedded artwork
        check_cmd = ['ffprobe', '-i', str(source_file), '-show_streams', 
                     '-select_streams', 'v', '-v', 'error']
        check_result = subprocess.run(check_cmd, capture_output=True, text=True)
        has_embedded_artwork = len(check_result.stdout.strip()) > 0
        
        if has_embedded_artwork:
            logging.info(f"Using embedded artwork from {source_file}")
            # Use embedded artwork from FLAC
            cmd = [
                'ffmpeg', '-i', str(source_file),
                '-map', '0',  # Map all streams from input
                '-c:a', 'pcm_s16be',  # Audio codec
                '-c:v', 'copy',  # Copy artwork without re-encoding
                '-disposition:v', 'attached_pic',  # Mark as cover art
                '-f', 'aiff',
                str(dest_file),
                '-y'  # Overwrite if exists
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                return False, f"FFmpeg error: {result.stderr}"
            return True, str(dest_file)
        
        # If no embedded artwork, look for cover art file in the directory
        cover_art_path = find_cover_art(source_file)
        
        if cover_art_path:
            logging.info(f"Using external cover art: {cover_art_path}")
            # Convert audio and add external artwork
            cmd = [
                'ffmpeg',
                '-i', str(source_file),  # Audio input
                '-i', str(cover_art_path),  # Image input
                '-map', '0:a',  # Map audio from first input
                '-map', '1:v',  # Map video from second input
                '-c:a', 'pcm_s16be',  # Audio codec
                '-c:v', 'copy',  # Copy artwork without re-encoding
                '-disposition:v', 'attached_pic',  # Mark as cover art
                '-f', 'aiff',
                str(dest_file),
                '-y'  # Overwrite if exists
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                return False, f"FFmpeg error: {result.stderr}"
            return True, str(dest_file)
        
        # If no artwork found, just convert the audio
        logging.warning(f"No artwork found for {source_file}")
        basic_cmd = [
            'ffmpeg', '-i', str(source_file),
            '-c:a', 'pcm_s16be',
            '-f', 'aiff',
            str(dest_file),
            '-y'
        ]
        result = subprocess.run(basic_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return False, f"FFmpeg error: {result.stderr}"
        
        return True, str(dest_file)
    except Exception as e:
        return False, str(e)

def test_conversions():
    setup_logging()
    logger = logging.getLogger(__name__)
    
    # Setup paths
    source_dir = Path('/home/ravit/drives/tracks')
    dest_dir = Path('./converted_tracks/test')
    
    logger.info(f"Starting FLAC conversion test")
    logger.info(f"Source directory: {source_dir}")
    logger.info(f"Destination directory: {dest_dir}")
    
    # Find FLAC files
    with console.status("[bold blue]Finding FLAC files...") as status:
        flac_files = find_flac_files(source_dir)
        console.print(f"Found {len(flac_files)} FLAC files to test")
    
    if not flac_files:
        logger.error("No FLAC files found!")
        return
    
    results = []
    
    with Progress() as progress:
        task = progress.add_task("[cyan]Converting files...", total=len(flac_files))
        
        for flac_file in flac_files:
            logger.info(f"\nTesting conversion of: {flac_file}")
            
            # Check source file
            source_props = verify_audio_file(flac_file)
            if not source_props["valid"]:
                logger.error(f"Source file invalid: {source_props['error']}")
                continue
            
            # Convert file
            success, result = convert_flac_to_aiff(flac_file, dest_dir)
            
            if not success:
                logger.error(f"Conversion failed: {result}")
                results.append({
                    "file": flac_file,
                    "success": False,
                    "error": result
                })
                continue
            
            # Verify converted file
            aiff_file = Path(result)
            converted_props = verify_audio_file(aiff_file)
            
            if not converted_props["valid"]:
                logger.error(f"Converted file invalid: {converted_props['error']}")
                results.append({
                    "file": flac_file,
                    "success": False,
                    "error": f"Invalid converted file: {converted_props['error']}"
                })
                continue
            
            # Compare properties
            conversion_ok = (
                abs(source_props["duration"] - converted_props["duration"]) < 1 and
                source_props["channels"] == converted_props["channels"]
            )
            
            results.append({
                "file": flac_file,
                "success": conversion_ok,
                "source_props": source_props,
                "converted_props": converted_props,
                "converted_path": str(aiff_file)
            })
            
            logger.info(f"Conversion {'successful' if conversion_ok else 'failed'}")
            logger.info(f"Original duration: {source_props['duration']:.2f}s, channels: {source_props['channels']}")
            logger.info(f"Converted duration: {converted_props['duration']:.2f}s, channels: {converted_props['channels']}")
            
            progress.advance(task)
    
    # Print summary
    console.print("\n[bold]Conversion Test Results:[/bold]")
    for result in results:
        if result["success"]:
            console.print(f"✅ {result['file'].name} -> {Path(result['converted_path']).name}")
        else:
            console.print(f"❌ {result['file'].name}: {result.get('error', 'Unknown error')}")

if __name__ == "__main__":
    test_conversions()