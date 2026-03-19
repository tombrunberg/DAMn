#!/usr/bin/env python3
"""
Scan existing files and add them to the database
Use this to index files that were organized before the database existed
"""

import os
import sys
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict

from database import FileDB, init_database

# Try to import PIL for EXIF data
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Try to import subprocess for video metadata
try:
    import subprocess
    import json
    HAS_FFPROBE = True
except ImportError:
    HAS_FFPROBE = False

# Configuration
BASE_DIR = Path(__file__).parent
PHOTO_DIR = BASE_DIR / "photo"
VIDEO_DIR = BASE_DIR / "video"

# Supported file extensions
PHOTO_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.heic', '.raw', '.cr2', '.nef', '.arw', '.dng'}
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.webm', '.m4v', '.mpg', '.mpeg', '.3gp'}

CHUNK_SIZE = 8192


def calculate_file_hash(file_path: Path) -> str:
    """Calculate SHA256 hash of a file."""
    sha256_hash = hashlib.sha256()

    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(CHUNK_SIZE), b""):
            sha256_hash.update(byte_block)

    return sha256_hash.hexdigest()


def get_file_type(file_path: Path) -> Optional[str]:
    """Determine if file is photo or video. Returns 'photo', 'video', or None."""
    ext = file_path.suffix.lower()

    if ext in PHOTO_EXTENSIONS:
        return 'photo'
    elif ext in VIDEO_EXTENSIONS:
        return 'video'
    else:
        return None


def get_exif_data(file_path: Path) -> Dict:
    """Extract EXIF data from image. Returns dict with date, dimensions, camera info."""
    result = {
        'date': None,
        'width': None,
        'height': None,
        'camera_make': None,
        'camera_model': None
    }

    if not HAS_PIL:
        return result

    try:
        image = Image.open(file_path)

        # Get dimensions
        result['width'], result['height'] = image.size

        # Get EXIF data
        exif_data = image._getexif()

        if exif_data:
            # Try different EXIF date tags
            for tag_id in [36867, 36868, 306]:  # DateTimeOriginal, DateTimeDigitized, DateTime
                if tag_id in exif_data and not result['date']:
                    date_str = exif_data[tag_id]
                    try:
                        result['date'] = datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
                    except:
                        pass

            # Camera make (tag 271)
            if 271 in exif_data:
                result['camera_make'] = exif_data[271]

            # Camera model (tag 272)
            if 272 in exif_data:
                result['camera_model'] = exif_data[272]

    except Exception as e:
        pass  # Silently skip errors

    return result


def get_video_metadata(file_path: Path) -> Dict:
    """Extract metadata from video. Returns dict with date, dimensions, duration."""
    result = {
        'date': None,
        'width': None,
        'height': None,
        'duration': None
    }

    if not HAS_FFPROBE:
        return result

    try:
        proc_result = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', str(file_path)],
            capture_output=True,
            text=True,
            timeout=10
        )

        if proc_result.returncode == 0:
            data = json.loads(proc_result.stdout)

            # Get date from format tags
            if 'format' in data and 'tags' in data['format']:
                tags = data['format']['tags']
                for key in ['creation_time', 'date', 'DATE']:
                    if key in tags and not result['date']:
                        date_str = tags[key]
                        try:
                            result['date'] = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                        except:
                            pass

            # Get duration
            if 'format' in data and 'duration' in data['format']:
                try:
                    result['duration'] = float(data['format']['duration'])
                except:
                    pass

            # Get dimensions from video stream
            if 'streams' in data:
                for stream in data['streams']:
                    if stream.get('codec_type') == 'video':
                        result['width'] = stream.get('width')
                        result['height'] = stream.get('height')
                        break

    except Exception as e:
        pass  # Silently skip errors

    return result


def scan_and_add_file(file_path: Path, dry_run: bool = False) -> bool:
    """
    Scan a file and add it to the database if not already present.
    Returns True if added, False if skipped.
    """
    # Check if already in database
    existing = FileDB.find_by_path(str(file_path))
    if existing:
        return False

    # Determine file type
    file_type = get_file_type(file_path)
    if not file_type:
        print(f"  Skipped: {file_path.name} (unknown type)")
        return False

    is_photo = (file_type == 'photo')

    # Calculate hash
    try:
        file_hash = calculate_file_hash(file_path)
    except Exception as e:
        print(f"  Error reading {file_path.name}: {e}")
        return False

    # Check if hash already exists (duplicate)
    existing_hash = FileDB.find_by_hash(file_hash)
    if existing_hash:
        print(f"  Duplicate: {file_path.name}")
        print(f"    Already in DB: {existing_hash['file_path']}")
        return False

    # Get metadata
    if is_photo:
        metadata = get_exif_data(file_path)
    else:
        metadata = get_video_metadata(file_path)

    # Get file stats
    stat_info = file_path.stat()
    file_size = stat_info.st_size
    file_mtime = datetime.fromtimestamp(stat_info.st_mtime)

    # Use metadata date or file mtime
    capture_date = metadata.get('date') or file_mtime

    if not dry_run:
        # Add to database
        file_id = FileDB.add_file(
            hash=file_hash,
            file_path=str(file_path),
            file_name=file_path.name,
            file_type=file_type,
            file_size=file_size,
            file_extension=file_path.suffix.lower(),
            file_mtime=file_mtime,
            capture_date=capture_date,
            width=metadata.get('width'),
            height=metadata.get('height'),
            duration=metadata.get('duration'),
            camera_make=metadata.get('camera_make'),
            camera_model=metadata.get('camera_model')
        )

        if file_id:
            print(f"  ✓ Added: {file_path.name} (ID: {file_id})")
            return True
        else:
            print(f"  Failed: {file_path.name}")
            return False
    else:
        print(f"  [DRY RUN] Would add: {file_path.name}")
        print(f"    Hash: {file_hash[:16]}...")
        print(f"    Date: {capture_date}")
        return True


def scan_directory(directory: Path, dry_run: bool = False) -> tuple:
    """
    Recursively scan a directory and add files to database.
    Returns (added, skipped) counts.
    """
    added = 0
    skipped = 0

    print(f"\nScanning: {directory.relative_to(BASE_DIR)}")
    print("-" * 60)

    # Walk through directory
    for file_path in directory.rglob('*'):
        if file_path.is_file():
            if scan_and_add_file(file_path, dry_run):
                added += 1
            else:
                skipped += 1

    return added, skipped


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Scan existing files and add to database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scan all photo and video directories
  %(prog)s

  # Scan only photos
  %(prog)s --photos

  # Scan only videos
  %(prog)s --videos

  # Preview without adding to database
  %(prog)s --dry-run

  # Scan specific directory
  %(prog)s --path photo/2024
        """
    )

    parser.add_argument('--dry-run', action='store_true', help='Preview without adding to database')
    parser.add_argument('--photos', action='store_true', help='Scan only photo directory')
    parser.add_argument('--videos', action='store_true', help='Scan only video directory')
    parser.add_argument('--path', type=str, help='Scan specific path (relative to base directory)')

    args = parser.parse_args()

    # Initialize database
    init_database()

    print("\nFile Scanner")
    print(f"Base directory: {BASE_DIR}")
    print()

    # Show current stats
    stats = FileDB.get_stats()
    print(f"Current database: {stats['total_files']} files ({stats['photos']} photos, {stats['videos']} videos)")

    if args.dry_run:
        print("\n*** DRY RUN MODE - No files will be added to database ***")

    total_added = 0
    total_skipped = 0

    # Scan specific path
    if args.path:
        path = BASE_DIR / args.path
        if not path.exists():
            print(f"\nError: Path does not exist: {path}")
            return

        added, skipped = scan_directory(path, args.dry_run)
        total_added += added
        total_skipped += skipped

    else:
        # Scan photo directory
        if not args.videos:  # Default to scanning photos unless --videos specified
            if PHOTO_DIR.exists():
                added, skipped = scan_directory(PHOTO_DIR, args.dry_run)
                total_added += added
                total_skipped += skipped

        # Scan video directory
        if not args.photos:  # Default to scanning videos unless --photos specified
            if VIDEO_DIR.exists():
                added, skipped = scan_directory(VIDEO_DIR, args.dry_run)
                total_added += added
                total_skipped += skipped

    # Show summary
    print(f"\n{'='*60}")
    print(f"Scan complete!")
    print(f"  Added:   {total_added}")
    print(f"  Skipped: {total_skipped}")
    print(f"  Total:   {total_added + total_skipped}")

    # Show updated stats
    if not args.dry_run:
        stats = FileDB.get_stats()
        print(f"\nUpdated database: {stats['total_files']} files ({stats['photos']} photos, {stats['videos']} videos)")


if __name__ == "__main__":
    main()
