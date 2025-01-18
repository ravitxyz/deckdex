from pathlib import Path
import logging
import subprocess
import json
from typing import Optional, Dict, Tuple

logger = logging.getlogger(__name__)

def generate_fingerprint(file_path: Path) -> Optional[Tuple[str, float]]:
    """Generates a Chromaprint fingerprint for an audio file.
    Args:
        file_path (Path): Path to the audio file.
    Returns:
        Optional[Tuplep[str, float]]: Tuple of (fingerprint, duration) if successful, None if failed.
    """

    try:
        cmd = [
            'fpcalc',
            '-json',
            'str(file_path)'
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            check=True
        )
        data = json.loads(result.stdout)

        return data['fingerprint'], float(data['duration'])

    except subprocess.CalledProcessError as e:
        logger.error(f"Fingerprint generation failed for {file_path}: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse fingerprint data for {file_path}: {e}")
        return None
    except KeyError as e:
        logger.error(f"Missing expected data in fingerprint output for {file_path}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error generating fingerprint for {file_path}: {e}")
        return None

def compare_fingerprints(fp1: str, fp2: str) -> float:
    """
    Compare two Chromaprint fingerprints and return similarity score.

    Args:
        fl1(str): First fingerprint
        fl2(str): Second fingerprint

    Returns:
        float: Similarity score between 0.0 and 1.0
    """

    try:
        # Run fpcalc with comparison mode
        cmd = [
            'fpcalc',
            '-compare',
            fp1,
            fp2
        ]
        
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            check=True
        )
        similarity = float(result.stdout.strip())
        
        return min(max(similarity, 0.0), 1.0)  # Clamp between 0 and 1

    except (subprocess.CalledProcessError, ValueError) as e:
        logger.error(f"Fingerprint comparison failed: {e}")
        return 0.0

def verify_chromaprint_installation() -> bool:
    """
    Verify that Chromaprint (fpcalc) is installed and accessible.
    
    Returns:
        bool: True if Chromaprint is installed and working, False otherwise
    """
    try:
        result = subprocess.run(
            ['fpcalc', '--version'], 
            capture_output=True, 
            text=True, 
            check=True
        )
        logger.info(f"Found Chromaprint: {result.stdout.strip()}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Error verifying Chromaprint installation: {e}")
        return False
    except FileNotFoundError:
        logger.error("Chromaprint (fpcalc) not found. Please install chromaprint-tools")
        return False

def batch_generate_fingerprints(
        file_paths: list[Path],
        max_workers: int = 4
) -> Dict[Path, Optional[Tuple[str, float]]]:
    """
    Generate fingerprints for multiple files in parallel.
    
    Args:
        file_paths (list[Path]): List of paths to audio files
        max_workers (int): Maximum number of parallel processes
        
    Returns:
        Dict[Path, Optional[Tuple[str, float]]]: Dictionary mapping file paths to their fingerprints
    """    
    from concurrent.futures import ProcessPoolExecutor

    results = {}
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        future_to_path = {
            executor.submit(generate_fingerprint, path): path
            for path in file_paths
        }

        for future in future_to_path:
            path = future_to_path[future]
            try:
                results[path] = future.result()
            except Exception as e:
                logger.error(f"Failed to process {path}: {e}")
                results[path] = None

    return results