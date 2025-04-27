#!/usr/bin/env python3
"""
Normalize DJ Library Filenames

This script cleans up the DJ library by removing track numbers from filenames 
and removing duplicate files. It helps ensure Rekordbox doesn't see multiple
versions of the same track due to different filename patterns.
"""

import os
import re
import shutil
from pathlib import Path
import argparse
import logging
from concurrent.futures import ThreadPoolExecutor
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.console import Console

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='normalize-dj-library.log'
)
logger = logging.getLogger(__name__)
console = Console()

def normalize_filename(filename):
    """Remove track numbers and standardize filenames.
    
    Handles patterns like:
    - "01 - Track Name.aiff"
    - "01. Track Name.aiff"
    - "01 Track Name.aiff"
    - "Track 01 - Name.aiff"
    """
    # Get file extension and stem
    name_parts = filename.rsplit('.', 1)
    name = name_parts[0]
    extension = name_parts[1] if len(name_parts) > 1 else ""
    
    # Remove leading track numbers (01, 01., 01 -, etc.)
    name = re.sub(r'^(\d+)[\s.\-_]+', '', name)
    
    # Remove track numbers with brackets ([01], (01), etc.)
    name = re.sub(r'^\[(\d+)\][\s.\-_]*', '', name)
    name = re.sub(r'^\((\d+)\)[\s.\-_]*', '', name)
    
    # Cleanup any leftover spaces, dashes, dots at start
    name = name.strip('.-_ ')
    
    # Add extension back if it exists
    if extension:
        return f"{name}.{extension}"
    return name

def get_audio_files(directory):
    """Get all audio files in the directory recursively."""
    audio_extensions = ['.mp3', '.aiff', '.wav', '.flac', '.m4a']
    files = []
    
    for ext in audio_extensions:
        files.extend(Path(directory).rglob(f"*{ext}"))
    
    return files

def process_file(file_path, dry_run=False):
    """Process a single file, normalizing its filename."""
    try:
        # Get the normalized filename
        original_name = file_path.name
        normalized_name = normalize_filename(original_name)
        
        # Skip if already normalized
        if original_name == normalized_name:
            return {'status': 'skipped', 'path': str(file_path), 'reason': 'already normalized'}
        
        # Create the new path
        new_path = file_path.parent / normalized_name
        
        # Check if the normalized file already exists
        if new_path.exists():
            # If both files exist, keep the newer one
            if os.path.getmtime(new_path) > os.path.getmtime(file_path):
                # New path is newer, remove the old one
                if not dry_run:
                    os.remove(file_path)
                return {'status': 'removed', 'path': str(file_path), 'reason': f'duplicate of {normalized_name}'}
            else:
                # Old path is newer, remove the new one and then rename
                if not dry_run:
                    os.remove(new_path)
                    shutil.move(file_path, new_path)
                return {'status': 'replaced', 'path': str(file_path), 'new_path': str(new_path)}
        else:
            # Just rename the file
            if not dry_run:
                shutil.move(file_path, new_path)
            return {'status': 'renamed', 'path': str(file_path), 'new_path': str(new_path)}
    
    except Exception as e:
        return {'status': 'error', 'path': str(file_path), 'error': str(e)}

def run_cleanup(dj_library_path, dry_run=False, workers=4):
    """Run the cleanup process on the DJ library."""
    # Get all audio files
    console.print(f"Scanning {dj_library_path} for audio files...", style="bold cyan")
    audio_files = get_audio_files(dj_library_path)
    console.print(f"Found {len(audio_files)} audio files.", style="bold green")
    
    if dry_run:
        console.print("DRY RUN: No files will be changed", style="bold yellow")
    
    # Statistics counters
    stats = {
        'renamed': 0,
        'removed': 0,
        'replaced': 0,
        'skipped': 0,
        'error': 0
    }
    
    # Process files with progress tracking
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("({task.completed}/{task.total})"),
        console=Console(force_terminal=True)
    ) as progress:
        task = progress.add_task("Normalizing files...", total=len(audio_files))
        
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = []
            for file_path in audio_files:
                futures.append(executor.submit(process_file, file_path, dry_run))
            
            # Process results as they complete
            for future in futures:
                result = future.result()
                status = result.get('status')
                stats[status] += 1
                
                # Log the result
                if status == 'renamed':
                    logger.info(f"Renamed: {result['path']} -> {result['new_path']}")
                elif status == 'removed':
                    logger.info(f"Removed duplicate: {result['path']} ({result['reason']})")
                elif status == 'replaced':
                    logger.info(f"Replaced duplicate: {result['path']} -> {result['new_path']}")
                elif status == 'error':
                    logger.error(f"Error processing {result['path']}: {result['error']}")
                
                progress.advance(task)
    
    # Print summary
    console.print("\nCleanup Complete!", style="bold green")
    console.print(f"Renamed: {stats['renamed']} files", style="cyan")
    console.print(f"Removed: {stats['removed']} duplicate files", style="yellow")
    console.print(f"Replaced: {stats['replaced']} files with newer versions", style="magenta")
    console.print(f"Skipped: {stats['skipped']} files (already normalized)", style="blue")
    if stats['error'] > 0:
        console.print(f"Errors: {stats['error']} files (see log for details)", style="bold red")
    
    if dry_run:
        console.print("\nThis was a dry run. Run again without --dry-run to apply changes.", style="bold yellow")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Normalize DJ library filenames by removing track numbers")
    parser.add_argument("--path", type=str, default="/Volumes/dj-library", 
                        help="Path to the DJ library (default: /Volumes/dj-library)")
    parser.add_argument("--dry-run", action="store_true", 
                        help="Show what would be done without making changes")
    parser.add_argument("--workers", type=int, default=4, 
                        help="Number of worker threads (default: 4)")
    
    args = parser.parse_args()
    
    run_cleanup(args.path, args.dry_run, args.workers)