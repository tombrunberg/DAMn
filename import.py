#!/usr/bin/env python3
"""
Media Import Script
Organizes photos and videos from incoming folder into date-based structure.
"""

import os
import sys
import hashlib
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, Dict
import mimetypes

# Import database module
from database import FileDB, FileTagDB, init_database
import re

# Try to import PIL for EXIF data
try:
    from PIL import Image
    from PIL.ExifTags import TAGS
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("Warning: PIL/Pillow not installed. Install with 'pip install Pillow' for EXIF support.")

# Try to import video metadata library
try:
    import subprocess
    HAS_FFPROBE = True
except ImportError:
    HAS_FFPROBE = False

# Configuration
BASE_DIR = Path(__file__).parent
INCOMING_DIR = BASE_DIR / "incoming"
PHOTO_DIR = BASE_DIR / "photo"
VIDEO_DIR = BASE_DIR / "video"

# Supported file extensions
PHOTO_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.heic', '.raw', '.cr2', '.nef', '.arw', '.dng'}
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.webm', '.m4v', '.mpg', '.mpeg', '.3gp'}

CHUNK_SIZE = 8192  # For hash calculation


def calculate_file_hash(file_path: Path) -> str:
    """Calculate SHA256 hash of a file."""
    sha256_hash = hashlib.sha256()

    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(CHUNK_SIZE), b""):
            sha256_hash.update(byte_block)

    return sha256_hash.hexdigest()


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
                    # EXIF date format: "2023:12:25 14:30:45"
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
        print(f"  Warning: Could not read EXIF from {file_path.name}: {e}")

    return result


def get_video_metadata(file_path: Path) -> Dict:
    """Extract metadata from video. Returns dict with date, dimensions, duration."""
    result = {
        'date': None,
        'width': None,
        'height': None,
        'duration': None
    }

    try:
        proc_result = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', str(file_path)],
            capture_output=True,
            text=True,
            timeout=10
        )

        if proc_result.returncode == 0:
            import json
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
        print(f"  Warning: Could not read video metadata from {file_path.name}: {e}")

    return result


def get_file_metadata(file_path: Path, is_photo: bool) -> Dict:
    """
    Get metadata from file.
    Returns dict with date, dimensions, duration, camera info.
    """
    if is_photo:
        metadata = get_exif_data(file_path)
    else:
        metadata = get_video_metadata(file_path)

    # If no date found, use file modification time
    if not metadata['date']:
        mtime = os.path.getmtime(file_path)
        metadata['date'] = datetime.fromtimestamp(mtime)

    return metadata


def get_target_path(file_path: Path, file_date: datetime, is_photo: bool) -> Path:
    """
    Generate target path based on date: BASE/YYYY/YYYY-MM/YYYY-MM-DD/filename
    """
    base = PHOTO_DIR if is_photo else VIDEO_DIR

    year = file_date.strftime("%Y")
    year_month = file_date.strftime("%Y-%m")
    year_month_day = file_date.strftime("%Y-%m-%d")

    target_dir = base / year / year_month / year_month_day
    target_path = target_dir / file_path.name

    return target_path


def find_duplicate_in_db(file_hash: str) -> Optional[Dict]:
    """
    Search for a file with the same hash in the database.
    Returns file record if found, None otherwise.
    """
    return FileDB.find_by_hash(file_hash)


def get_file_type(file_path: Path) -> Optional[str]:
    """Determine if file is photo or video. Returns 'photo', 'video', or None."""
    ext = file_path.suffix.lower()

    if ext in PHOTO_EXTENSIONS:
        return 'photo'
    elif ext in VIDEO_EXTENSIONS:
        return 'video'
    else:
        return None


def normalize_tag_name(name: str) -> str:
    """
    Normalize a tag name to lowercase kebab-case.
    - Convert to lowercase
    - Replace spaces and underscores with hyphens
    - Remove special characters (keep only letters, numbers, hyphens)
    """
    # Convert to lowercase
    name = name.lower()

    # Replace spaces and underscores with hyphens
    name = name.replace(' ', '-').replace('_', '-')

    # Remove all characters except letters, numbers, and hyphens
    name = re.sub(r'[^a-z0-9-]', '', name)

    # Remove multiple consecutive hyphens
    name = re.sub(r'-+', '-', name)

    # Remove leading/trailing hyphens
    name = name.strip('-')

    return name


def is_date_folder(folder_name: str) -> bool:
    """
    Check if a folder name looks like a date pattern.
    Returns True for: YYYY, YYYY-MM, YYYY-MM-DD, YYYY_MM_DD
    """
    # Year: 4 digits
    if re.match(r'^\d{4}$', folder_name):
        return True

    # YYYY-MM or YYYY_MM
    if re.match(r'^\d{4}[-_]\d{2}$', folder_name):
        return True

    # YYYY-MM-DD or YYYY_MM_DD
    if re.match(r'^\d{4}[-_]\d{2}[-_]\d{2}$', folder_name):
        return True

    return False


def extract_tags_from_path(file_path: Path, incoming_dir: Path) -> list[str]:
    """
    Extract folder names from path as tags.
    Skip the incoming directory itself and any date-pattern folders.

    Example: incoming/vacation/Beach Photos/img.jpg
    Returns: ['vacation', 'beach-photos']
    """
    tags = []

    try:
        # Get the relative path from incoming directory
        relative = file_path.relative_to(incoming_dir)

        # Get all parent folders (excluding the file itself)
        folders = relative.parts[:-1]  # Exclude filename

        for folder in folders:
            # Skip date-like folders
            if is_date_folder(folder):
                continue

            # Normalize and add as tag
            tag = normalize_tag_name(folder)
            if tag:  # Only add non-empty tags
                tags.append(tag)

    except ValueError:
        # File is not relative to incoming_dir
        pass

    return tags


def import_file(file_path: Path, dry_run: bool = False, tags: list[str] = None) -> bool:
    """
    Import a single file from incoming directory.

    Args:
        file_path: Path to file to import
        dry_run: If True, don't actually move files or modify database
        tags: Optional list of tags to apply to the file after import

    Returns True if file was imported, False otherwise.
    """
    if tags is None:
        tags = []

    print(f"\nProcessing: {file_path.name}")
    if tags:
        print(f"  Tags: {', '.join(tags)}")

    # Determine file type
    file_type = get_file_type(file_path)
    if file_type is None:
        print(f"  Skipped: Unknown file type")
        return False

    is_photo = (file_type == 'photo')
    print(f"  Type: {file_type}")

    # Calculate hash
    print(f"  Calculating hash...")
    file_hash = calculate_file_hash(file_path)
    print(f"  Hash: {file_hash[:16]}...")

    # Check for duplicates in database
    duplicate = find_duplicate_in_db(file_hash)

    if duplicate:
        # Compare file modification times - keep the older one
        incoming_mtime = os.path.getmtime(file_path)
        existing_mtime = datetime.fromisoformat(duplicate['file_mtime']).timestamp()

        if incoming_mtime < existing_mtime:
            print(f"  Duplicate found: {duplicate['file_path']}")
            print(f"  Incoming file is older - replacing existing file")

            if not dry_run:
                # Remove newer file from filesystem and database
                existing_path = Path(duplicate['file_path'])
                if existing_path.exists():
                    existing_path.unlink()
                FileDB.delete_file(duplicate['id'])
            else:
                print(f"  [DRY RUN] Would replace {duplicate['file_path']}")
        else:
            print(f"  Duplicate found: {duplicate['file_path']}")
            print(f"  Existing file is older - skipping import")

            if not dry_run:
                # Remove the incoming file
                file_path.unlink()
            else:
                print(f"  [DRY RUN] Would remove {file_path}")

            return False

    # Get file metadata
    metadata = get_file_metadata(file_path, is_photo)
    file_date = metadata['date']
    print(f"  Date: {file_date.strftime('%Y-%m-%d %H:%M:%S')}")

    target_path = get_target_path(file_path, file_date, is_photo)
    print(f"  Target: {target_path.relative_to(BASE_DIR)}")

    # Handle filename conflicts (different files with same name)
    if target_path.exists():
        # Add counter to filename
        counter = 1
        while target_path.exists():
            stem = file_path.stem
            suffix = file_path.suffix
            new_name = f"{stem}_{counter}{suffix}"
            target_path = target_path.parent / new_name
            counter += 1
        print(f"  Renamed to avoid conflict: {target_path.name}")

    # Create target directory and move file
    if not dry_run:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(file_path), str(target_path))

        # Add to database
        file_size = target_path.stat().st_size
        file_mtime = datetime.fromtimestamp(os.path.getmtime(target_path))

        file_id = FileDB.add_file(
            hash=file_hash,
            file_path=str(target_path),
            file_name=target_path.name,
            file_type=file_type,
            file_size=file_size,
            file_extension=target_path.suffix.lower(),
            file_mtime=file_mtime,
            capture_date=file_date,
            width=metadata.get('width'),
            height=metadata.get('height'),
            duration=metadata.get('duration'),
            camera_make=metadata.get('camera_make'),
            camera_model=metadata.get('camera_model')
        )

        if file_id:
            print(f"  ✓ Imported successfully (DB ID: {file_id})")

            # Apply tags if provided
            if tags:
                for tag in tags:
                    FileTagDB.add_tag_to_file(file_id, tag)
                print(f"  ✓ Tagged with: {', '.join(tags)}")
        else:
            print(f"  ✓ File moved (warning: already in database)")
    else:
        print(f"  [DRY RUN] Would move to {target_path}")
        if tags:
            print(f"  [DRY RUN] Would tag with: {', '.join(tags)}")

    return True


def cleanup_incoming_directory(imported_files: list[Path]):
    """
    Clean up the incoming directory after successful import.
    Removes empty directories bottom-up.

    Args:
        imported_files: List of file paths that were successfully imported (and moved)
    """
    print(f"\nCleaning up incoming directory...")

    # Get all unique parent directories from imported files
    directories = set()
    for file_path in imported_files:
        # Get all parent directories between the file and INCOMING_DIR
        current = file_path.parent
        while current != INCOMING_DIR and current.is_relative_to(INCOMING_DIR):
            directories.add(current)
            current = current.parent

    # Sort directories by depth (deepest first) for bottom-up removal
    sorted_dirs = sorted(directories, key=lambda d: len(d.parts), reverse=True)

    removed_count = 0
    for directory in sorted_dirs:
        try:
            # Only remove if directory is empty
            if directory.exists() and not any(directory.iterdir()):
                directory.rmdir()
                print(f"  Removed empty directory: {directory.relative_to(INCOMING_DIR)}")
                removed_count += 1
        except Exception as e:
            # Directory not empty or other error - skip silently
            pass

    if removed_count > 0:
        print(f"✓ Cleaned up {removed_count} empty directories")
    else:
        print(f"  No empty directories to remove")


def import_all(dry_run: bool = False):
    """Import all files from incoming directory recursively."""
    if not INCOMING_DIR.exists():
        print(f"Error: Incoming directory does not exist: {INCOMING_DIR}")
        return

    # Recursively find all files in incoming directory
    files = [f for f in INCOMING_DIR.rglob('*') if f.is_file()]

    if not files:
        print("No files to import in incoming directory.")
        return

    print(f"Found {len(files)} file(s) to import")
    if dry_run:
        print("\n*** DRY RUN MODE - No files will be moved ***\n")

    imported = 0
    skipped = 0
    imported_files = []  # Track successfully imported files for cleanup

    for file_path in files:
        # Extract tags from folder structure
        tags = extract_tags_from_path(file_path, INCOMING_DIR)

        # Import file with auto-tags
        if import_file(file_path, dry_run, tags):
            imported += 1
            if not dry_run:
                imported_files.append(file_path)
        else:
            skipped += 1

    print(f"\n{'='*60}")
    print(f"Import complete!")
    print(f"  Imported: {imported}")
    print(f"  Skipped: {skipped}")
    print(f"  Total: {len(files)}")

    # Clean up imported files and empty directories
    if not dry_run and imported_files:
        cleanup_incoming_directory(imported_files)
    elif dry_run and imported_files:
        print(f"\n[DRY RUN] Would clean up {len(imported_files)} imported files and empty directories")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Import photos and videos from incoming directory")
    parser.add_argument('--dry-run', action='store_true', help='Preview actions without making changes')

    args = parser.parse_args()

    # Initialize database if needed
    init_database()

    print("\nMedia Import Script")
    print(f"Base directory: {BASE_DIR}")
    print(f"Incoming: {INCOMING_DIR}")
    print(f"Photos: {PHOTO_DIR}")
    print(f"Videos: {VIDEO_DIR}")
    print()

    # Show database stats
    stats = FileDB.get_stats()
    print(f"Database: {stats['total_files']} files ({stats['photos']} photos, {stats['videos']} videos, {stats['tags']} tags)")
    print()

    import_all(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
