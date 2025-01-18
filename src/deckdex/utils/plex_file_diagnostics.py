import subprocess
from pathlib import Path
import logging
from typing import Dict, List, Optional
import json
import re

class PlexFileChecker:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
    def check_specific_files(self, file_paths: List[str]) -> Dict[str, dict]:
        """Check specific files for potential issues that might cause Plex to hang."""
        results = {}
        
        for file_path in file_paths:
            path = Path(file_path)
            if not path.exists():
                results[file_path] = {
                    "exists": False,
                    "issues": ["File not found"],
                    "severity": "high"
                }
                continue
                
            issues = []
            severity = "low"
            
            # Check filename issues
            filename_issues = self._check_filename(path)
            if filename_issues:
                issues.extend(filename_issues)
                severity = "medium"
            
            # Check file integrity
            integrity_result = self._check_file_integrity(path)
            if integrity_result:
                issues.extend(integrity_result)
                severity = "high"
            
            # Check for duplicate variants
            duplicate_issues = self._check_for_duplicates(path)
            if duplicate_issues:
                issues.extend(duplicate_issues)
                severity = "medium"
            
            # Store results
            results[file_path] = {
                "exists": True,
                "issues": issues,
                "severity": severity,
                "size": path.stat().st_size,
                "last_modified": path.stat().st_mtime
            }
            
        return results
    
    def _check_filename(self, path: Path) -> List[str]:
        """Check filename for potential issues."""
        issues = []
        filename = path.name
        
        # Check for problematic characters
        if re.search(r'[／＼：＊？"＜＞｜]', filename):
            issues.append("Contains full-width special characters")
            
        if '/' in filename or '\\' in filename:
            issues.append("Contains forward or backward slashes")
            
        if re.search(r'[\x00-\x1f\x7f-\x9f]', filename):
            issues.append("Contains control characters")
            
        # Check for leading/trailing spaces
        if filename != filename.strip():
            issues.append("Has leading or trailing spaces")
            
        # Check for double spaces
        if '  ' in filename:
            issues.append("Contains double spaces")
            
        return issues
    
    def _check_file_integrity(self, path: Path) -> List[str]:
        """Check file integrity using ffprobe."""
        issues = []
        
        try:
            # Run basic ffprobe check
            cmd = [
                'ffprobe',
                '-v', 'error',
                '-select_streams', 'a:0',
                '-show_entries', 'stream=codec_name,duration',
                '-of', 'json',
                str(path)
            ]
            
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                issues.append(f"FFprobe error: {result.stderr.strip()}")
                return issues
            
            # Try to decode a small portion
            decode_cmd = [
                'ffmpeg',
                '-v', 'error',
                '-i', str(path),
                '-t', '5',  # Check first 5 seconds
                '-f', 'null',
                '-'
            ]
            
            decode_result = subprocess.run(
                decode_cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if decode_result.returncode != 0:
                issues.append(f"Decoding error: {decode_result.stderr.strip()}")
            
        except subprocess.TimeoutExpired:
            issues.append("File analysis timed out")
        except Exception as e:
            issues.append(f"Analysis error: {str(e)}")
            
        return issues
    
    def _check_for_duplicates(self, path: Path) -> List[str]:
        """Check for similar files that might cause conflicts."""
        issues = []
        stem = path.stem
        parent = path.parent
        
        # Find similar files
        similar_files = list(parent.glob(f"{stem}*.*"))
        if len(similar_files) > 1:
            similar_files.remove(path)  # Remove the current file
            if similar_files:
                issues.append(
                    f"Found similar files: {', '.join(f.name for f in similar_files)}"
                )
                
        return issues

def generate_report(results: Dict[str, dict], output_file: Optional[str] = None):
    """Generate a human-readable report of the results."""
    report_lines = ["Plex File Diagnostic Report", "========================\n"]
    
    # Group by severity
    severity_groups = {
        "high": [],
        "medium": [],
        "low": []
    }
    
    for file_path, result in results.items():
        if result["issues"]:
            severity_groups[result["severity"]].append((file_path, result))
    
    # Add issues to report
    for severity in ["high", "medium", "low"]:
        if severity_groups[severity]:
            report_lines.append(f"{severity.upper()} Severity Issues:")
            report_lines.append("-" * 20)
            
            for file_path, result in severity_groups[severity]:
                report_lines.append(f"\nFile: {file_path}")
                for issue in result["issues"]:
                    report_lines.append(f"- {issue}")
            report_lines.append("")
    
    report_text = "\n".join(report_lines)
    
    if output_file:
        with open(output_file, 'w') as f:
            f.write(report_text)
    
    return report_text

if __name__ == "__main__":
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    if len(sys.argv) < 2:
        print("Usage: script.py file_list.txt [output_report.txt]")
        sys.exit(1)
        
    # Read file list
    with open(sys.argv[1]) as f:
        files = [line.strip() for line in f if line.strip()]
    
    checker = PlexFileChecker()
    results = checker.check_specific_files(files)
    
    # Generate and output report
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    report = generate_report(results, output_file)
    print(report)
