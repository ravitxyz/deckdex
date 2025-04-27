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
    - "Track Name - 01.aiff"
    - "Track Name (1).aiff"
    - "Track Name [01].aiff"
    """
    # Get file extension and stem
    name_parts = filename.rsplit('.', 1)
    name = name_parts[0]
    extension = name_parts[1] if len(name_parts) > 1 else ""
    
    # Remove leading track numbers (01, 01., 01 -, etc.)
    # This handles formats like "1. Track Name"
    name = re.sub(r'^(\d+)[.\s\-_]+', '', name)
    
    # Remove track numbers with brackets ([01], (01), etc.) at beginning
    name = re.sub(r'^\[(\d+)\][\s.\-_]*', '', name)
    name = re.sub(r'^\((\d+)\)[\s.\-_]*', '', name)
    
    # Remove track numbers at the end of filenames
    name = re.sub(r'[\s.\-_]+(\d+)$', '', name)
    name = re.sub(r'[\s.\-_]*\[(\d+)\]$', '', name)
    name = re.sub(r'[\s.\-_]*\((\d+)\)$', '', name)
    
    # Handle embedded track numbers like "Track 01 - Name"
    name = re.sub(r'Track\s+\d+[\s.\-_]+', '', name, flags=re.IGNORECASE)
    
    # Remove any duplicate spaces that might have been created
    name = re.sub(r'\s+', ' ', name)
    
    # Cleanup any leftover spaces, dashes, dots at start or end
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
        
        # To better detect patterns like "1. Song Name", log some examples
        if original_name != normalized_name and re.match(r'^\d+\.', original_name):
            logger.info(f"Number prefix removed: {original_name} -> {normalized_name}")
        
        # Skip if already normalized and not a case-only difference
        if original_name == normalized_name:
            return {'status': 'skipped', 'path': str(file_path), 'reason': 'already normalized'}
        
        # Create the new path with the normalized name
        new_path = file_path.parent / normalized_name
        
        # Find any potential case-insensitive matches in the same directory
        # This helps with "Humming Bird" vs "Humming bird", etc.
        case_insensitive_matches = []
        for existing_file in file_path.parent.iterdir():
            if existing_file.is_file() and existing_file.name.lower() == normalized_name.lower() and existing_file != file_path:
                case_insensitive_matches.append(existing_file)
        
        # Check if the normalized file already exists (exact path match) or case-insensitive matches
        if new_path.exists() or case_insensitive_matches:
            # Determine which file to keep
            existing_files = [new_path] if new_path.exists() else []
            existing_files.extend(case_insensitive_matches)
            
            # Find the newest file (including the current one)
            newest_file = file_path
            newest_mtime = os.path.getmtime(file_path)
            
            for ef in existing_files:
                if os.path.exists(ef):  # Double-check existence
                    ef_mtime = os.path.getmtime(ef)
                    if ef_mtime > newest_mtime:
                        newest_file = ef
                        newest_mtime = ef_mtime
            
            # Keep the newest file and standardize its name
            if newest_file == file_path:
                # Current file is newest, remove others and rename this one
                if not dry_run:
                    for ef in existing_files:
                        if os.path.exists(ef):
                            try:
                                os.remove(ef)
                                logger.info(f"Removed duplicate: {ef}")
                            except Exception as e:
                                logger.error(f"Failed to remove {ef}: {str(e)}")
                    
                    # Make sure the path uses correct case
                    # Use a unique temp name to avoid conflicts
                    import uuid
                    temp_name = f"temp_{uuid.uuid4().hex}_{normalized_name}"
                    temp_path = file_path.parent / temp_name
                    
                    # Two-step move to ensure case changes are respected
                    try:
                        shutil.move(file_path, temp_path)
                        shutil.move(temp_path, new_path)
                    except Exception as e:
                        logger.error(f"Failed during rename: {str(e)}")
                        # Try to restore original if possible
                        if temp_path.exists() and not file_path.exists():
                            shutil.move(temp_path, file_path)
                            return {'status': 'error', 'path': str(file_path), 'error': str(e)}
                
                return {'status': 'replaced', 'path': str(file_path), 'new_path': str(new_path)}
            else:
                # Another file is newer, remove this one
                if not dry_run:
                    os.remove(file_path)
                    logger.info(f"Removed older file: {file_path}")
                    
                    # Rename the newest file to ensure correct case
                    if str(newest_file).lower() != str(new_path).lower():
                        import uuid
                        temp_name = f"temp_{uuid.uuid4().hex}_{normalized_name}"
                        temp_path = file_path.parent / temp_name
                        
                        try:
                            shutil.move(newest_file, temp_path)
                            shutil.move(temp_path, new_path)
                            logger.info(f"Standardized case: {newest_file} -> {new_path}")
                        except Exception as e:
                            logger.error(f"Failed during case standardization: {str(e)}")
                
                return {'status': 'removed', 'path': str(file_path), 'reason': f'duplicate of {normalized_name}'}
        else:
            # Just rename the file since no duplicates exist
            if not dry_run:
                try:
                    shutil.move(file_path, new_path)
                except Exception as e:
                    logger.error(f"Failed to rename {file_path} to {new_path}: {str(e)}")
                    return {'status': 'error', 'path': str(file_path), 'error': str(e)}
            
            return {'status': 'renamed', 'path': str(file_path), 'new_path': str(new_path)}
    
    except Exception as e:
        logger.error(f"Error processing {file_path}: {str(e)}")
        return {'status': 'error', 'path': str(file_path), 'error': str(e)}

def run_cleanup(dj_library_path, dry_run=False, workers=4):
    """Run the cleanup process on the DJ library."""
    # Validate paths
    dj_path = Path(dj_library_path)
    if not dj_path.exists() or not dj_path.is_dir():
        console.print(f"ERROR: The path {dj_library_path} does not exist or is not a directory", style="bold red")
        return
    
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
        
        # Process in batches to avoid memory issues with very large libraries
        batch_size = 500
        for i in range(0, len(audio_files), batch_size):
            batch = audio_files[i:i+batch_size]
            
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = []
                for file_path in batch:
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
    
    # Second pass to handle any case-insensitive duplicates that remain
    if not dry_run:
        console.print("Running second pass to catch any remaining duplicates...", style="bold cyan")
        # Create dictionary to track normalized filenames (case insensitive)
        seen_files = {}
        duplicate_count = 0
        
        # Get all audio files again (after first pass changes)
        audio_files = get_audio_files(dj_library_path)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            console=Console(force_terminal=True)
        ) as progress:
            task = progress.add_task("Checking for remaining duplicates...", total=len(audio_files))
            
            for file_path in audio_files:
                norm_name = file_path.name.lower()
                if norm_name in seen_files:
                    # We have a duplicate, keep the newer one
                    existing_path = seen_files[norm_name]
                    if os.path.getmtime(file_path) > os.path.getmtime(existing_path):
                        # Current file is newer
                        os.remove(existing_path)
                        seen_files[norm_name] = file_path
                        logger.info(f"Second pass: Removed older duplicate: {existing_path}")
                    else:
                        # Existing file is newer
                        os.remove(file_path)
                        logger.info(f"Second pass: Removed older duplicate: {file_path}")
                    duplicate_count += 1
                else:
                    seen_files[norm_name] = file_path
                
                progress.advance(task)
        
        if duplicate_count > 0:
            console.print(f"Second pass removed {duplicate_count} additional duplicates", style="bold yellow")
    
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