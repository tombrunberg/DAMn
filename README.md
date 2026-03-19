# DAMn - Digital Asset Manager

A simple photo and video organizer that sorts files by date, prevents duplicates, and supports tagging.

## Directory Structure

```
DAMn/
├── incoming/          # Drop files here
├── photo/            # Organized photos
│   └── YYYY/
│       └── YYYY-MM/
│           └── YYYY-MM-DD/
├── video/            # Organized videos
│   └── YYYY/
│       └── YYYY-MM/
│           └── YYYY-MM-DD/
├── damn.db           # SQLite database (auto-created)
├── import.py         # Import script
├── scan.py           # Scan existing files into database
├── tag.py            # Tagging CLI
└── database.py       # Database module
```

## Features

### Organization
- **Recursive import**: Processes files at unlimited depth in incoming folder
- **Automatic file type detection**: Supports common photo and video formats
- **Date-based organization**: Files organized as `YYYY/YYYY-MM/YYYY-MM-DD`
- **Smart date extraction**:
  - Photos: Reads EXIF metadata (DateTimeOriginal, DateTimeDigitized, DateTime)
  - Videos: Reads creation_time from metadata (requires ffprobe)
  - Fallback: Uses file modification time
- **Filename conflict handling**: Adds counter suffix if different files have same name
- **Automatic cleanup**: Removes imported files and empty folders from incoming

### Duplicate Detection
- **Hash-based detection**: Uses SHA256 hash of actual image data
- **Database-accelerated**: Fast duplicate lookup without scanning all files
- **Keeps older files**: When duplicates found, keeps the file with older modification time
- **Won't match resized images**: Hash only matches byte-for-byte identical files
- **Works across copies**: Even if file EXIF/creation date is wrong (from copying), hash will match

### Tagging & Database
- **SQLite database**: Tracks all files with metadata
- **Auto-tagging from folders**: Folder names automatically become tags (normalized to kebab-case)
- **Multi-tag support**: Add unlimited tags to any file
- **Fast search**: Search by tags with AND/OR logic
- **Metadata storage**: Stores hash, dimensions, camera info, dates
- **Tag management**: Add, remove, search, and list tags via CLI
- **Smart tag normalization**: Converts to lowercase, replaces spaces with hyphens, skips date patterns

## Installation

### Required
```bash
python3 -m pip install Pillow
```

### Optional (for video metadata)
```bash
# Install ffmpeg (includes ffprobe)
# macOS:
brew install ffmpeg

# Ubuntu/Debian:
sudo apt-get install ffmpeg
```

## Usage

### Importing Files

```bash
# Basic import
./import.py

# Dry run (preview without changes)
./import.py --dry-run
```

### Scanning Existing Files

If you have files that were organized before the database existed, use `scan.py` to add them:

```bash
# Scan all photo and video directories
./scan.py

# Scan only photos
./scan.py --photos

# Scan specific directory
./scan.py --path photo/2024

# Preview without adding to database
./scan.py --dry-run
```

### Tagging Files

```bash
# Add tags to a file
./tag.py add photo/2024/2024-03/2024-03-15/IMG_1234.jpg vacation beach sunset

# Remove tags from a file
./tag.py remove photo/2024/2024-03/2024-03-15/IMG_1234.jpg beach

# List tags on a file
./tag.py list photo/2024/2024-03/2024-03-15/IMG_1234.jpg

# Show detailed file information
./tag.py info photo/2024/2024-03/2024-03-15/IMG_1234.jpg
```

### Searching and Browsing

```bash
# List all tags in database
./tag.py tags

# Search files with ANY of these tags
./tag.py search vacation beach

# Search files with ALL of these tags
./tag.py search --all vacation beach sunset

# List recent files
./tag.py files --limit 50

# List only photos or videos
./tag.py files --type photo --limit 10
./tag.py files --type video
```

## Workflow

### Basic Workflow
1. Drop photos/videos into `incoming/` folder (can be nested in subfolders!)
2. Run `./import.py`
3. Files are automatically:
   - Recursively discovered (unlimited depth)
   - Hashed and checked for duplicates in database
   - Metadata extracted (EXIF, dimensions, camera info)
   - Auto-tagged from folder names
   - Organized by date into folder structure
   - Added to database with all metadata
   - Cleaned up from incoming (empty folders removed)
4. Optionally add more tags: `./tag.py add <path> <tags>`
5. Search and browse using `./tag.py search` or `./tag.py files`

### Auto-Tagging from Folders

Files are automatically tagged based on their folder path in `incoming/`:

```
incoming/vacation/beach/photo.jpg     → tags: vacation, beach
incoming/family/2024/reunion.jpg      → tags: family (skips "2024")
incoming/Work Stuff/screenshot.png    → tags: work-stuff (normalized)
```

**Tag normalization rules:**
- Converted to lowercase
- Spaces and underscores → hyphens (kebab-case)
- Special characters removed
- Date folders (YYYY, YYYY-MM, YYYY-MM-DD) are skipped

### Bulk Import with rsync

```bash
# On source machine, organize files in folders
source/
├── vacation/
│   ├── beach/
│   └── city/
└── work/

# rsync to incoming (preserves timestamps)
rsync -av --progress source/ server:/path/to/DAMn/incoming/

# On server, run import
./import.py

# Result: All files auto-tagged by folder structure!
```

## Supported Formats

### Photos
.jpg, .jpeg, .png, .gif, .bmp, .tiff, .tif, .heic, .raw, .cr2, .nef, .arw, .dng

### Videos
.mp4, .mov, .avi, .mkv, .wmv, .flv, .webm, .m4v, .mpg, .mpeg, .3gp

## Example Output

### Import
```
Processing: IMG_1234.jpg
  Type: photo
  Calculating hash...
  Hash: a3b5c8d9e1f2g4h6...
  Date: 2024-03-15 14:30:45
  Target: photo/2024/2024-03/2024-03-15/IMG_1234.jpg
  ✓ Imported successfully (DB ID: 42)

Processing: VID_5678.mp4
  Type: video
  Calculating hash...
  Hash: b4c6d8e2f3g5h7i9...
  Duplicate found: video/2024/2024-03/2024-03-15/VID_5678.mp4
  Existing file is older - skipping import
```

### Tagging
```
$ ./tag.py add photo/2024/2024-03/2024-03-15/IMG_1234.jpg vacation sunset
✓ Added tags to IMG_1234.jpg: vacation, sunset

$ ./tag.py info photo/2024/2024-03/2024-03-15/IMG_1234.jpg

File Information:
------------------------------------------------------------
Name:          IMG_1234.jpg
Path:          photo/2024/2024-03/2024-03-15/IMG_1234.jpg
Type:          photo
Size:          2,458,921 bytes
Hash:          a3b5c8d9e1f2g4h6...
Capture Date:  2024-03-15 14:30:45
Dimensions:    4032 x 3024
Camera:        Apple iPhone 13
Tags:          vacation, sunset

$ ./tag.py search vacation

Searching for files with ANY tags: vacation
Found 12 file(s)
------------------------------------------------------------

IMG_1234.jpg
  Path: photo/2024/2024-03/2024-03-15/IMG_1234.jpg
  Type: photo
  Date: 2024-03-15 14:30:45
  Tags: vacation, sunset
...
```

## Database Schema

The SQLite database (`damn.db`) stores:

**Files Table**
- Hash, file path, name, type, size, extension
- Capture date, file mtime, import date
- Dimensions (width x height)
- Duration (for videos)
- Camera make and model

**Tags Table**
- Tag name, description, color

**File-Tags Table** (many-to-many relationship)
- Links files to tags
- Supports multiple tags per file
- Supports multiple files per tag

## Technical Details

### Hash-Based Duplicate Detection

The hash is calculated from the actual file bytes, not metadata:
- Files with identical content = identical hash (even if EXIF differs)
- Resized/edited images = different hash
- Fast database lookup instead of filesystem scanning
- Works even when file dates are wrong from copying

### Date Priority

When extracting dates, the system uses this priority:
1. EXIF DateTimeOriginal (photos)
2. EXIF DateTimeDigitized (photos)
3. EXIF DateTime (photos)
4. Video metadata creation_time (videos)
5. File modification time (fallback)

## Future Enhancements

Potential features to add:
- Camera import (USB/SD card auto-detect)
- Cloud sync (Google Photos, iCloud, etc.)
- Watch folder for automatic import
- Web UI for browsing and tagging
- Thumbnail generation
- Face detection and recognition
- GPS/location tagging
- Export to albums/collections
