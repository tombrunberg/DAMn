#!/usr/bin/env python3
"""
Tagging CLI for DAMn - Digital Asset Manager
Manage tags for photos and videos
"""

import sys
import argparse
from pathlib import Path
from typing import List
from database import FileDB, TagDB, FileTagDB, init_database

# Configuration
BASE_DIR = Path(__file__).parent


def normalize_path(file_path: str) -> str:
    """Convert relative or absolute path to absolute path string."""
    path = Path(file_path)

    # If it's already absolute, use it
    if path.is_absolute():
        return str(path)

    # Otherwise, make it absolute relative to BASE_DIR
    abs_path = (BASE_DIR / path).resolve()
    return str(abs_path)


def add_tags(file_path: str, tags: List[str]) -> bool:
    """Add tags to a file."""
    # Normalize path
    normalized_path = normalize_path(file_path)

    # Find file in database
    file_record = FileDB.find_by_path(normalized_path)

    if not file_record:
        print(f"Error: File not found in database: {file_path}")
        print("Hint: Make sure the file has been imported first using import.py")
        return False

    file_id = file_record['id']
    added = []
    existing = []

    for tag in tags:
        if FileTagDB.add_tag_to_file(file_id, tag):
            added.append(tag)
        else:
            existing.append(tag)

    if added:
        print(f"✓ Added tags to {file_record['file_name']}: {', '.join(added)}")

    if existing:
        print(f"  Already tagged: {', '.join(existing)}")

    return True


def remove_tags(file_path: str, tags: List[str]) -> bool:
    """Remove tags from a file."""
    normalized_path = normalize_path(file_path)
    file_record = FileDB.find_by_path(normalized_path)

    if not file_record:
        print(f"Error: File not found in database: {file_path}")
        return False

    file_id = file_record['id']
    removed = []
    not_found = []

    for tag in tags:
        if FileTagDB.remove_tag_from_file(file_id, tag):
            removed.append(tag)
        else:
            not_found.append(tag)

    if removed:
        print(f"✓ Removed tags from {file_record['file_name']}: {', '.join(removed)}")

    if not_found:
        print(f"  Not tagged: {', '.join(not_found)}")

    return True


def list_file_tags(file_path: str) -> bool:
    """List all tags for a file."""
    normalized_path = normalize_path(file_path)
    file_record = FileDB.find_by_path(normalized_path)

    if not file_record:
        print(f"Error: File not found in database: {file_path}")
        return False

    tags = FileTagDB.get_file_tags(file_record['id'])

    print(f"\nFile: {file_record['file_name']}")
    print(f"Path: {file_record['file_path']}")

    if tags:
        print(f"Tags: {', '.join(tags)}")
    else:
        print("Tags: (none)")

    return True


def list_all_tags() -> None:
    """List all tags in the database."""
    tags = TagDB.get_all_tags()

    if not tags:
        print("No tags found.")
        return

    print(f"\nAll tags ({len(tags)}):")
    print("-" * 60)

    for tag in tags:
        # Count files with this tag
        files = FileTagDB.get_files_by_tag(tag['name'])
        print(f"  {tag['name']:<30} ({len(files)} files)")


def search_by_tags(tags: List[str], match_all: bool = False) -> None:
    """Search files by tags."""
    files = FileTagDB.search_files_by_tags(tags, match_all=match_all)

    mode = "ALL" if match_all else "ANY"
    print(f"\nSearching for files with {mode} tags: {', '.join(tags)}")
    print(f"Found {len(files)} file(s)")
    print("-" * 60)

    if not files:
        return

    for file_record in files:
        file_tags = FileTagDB.get_file_tags(file_record['id'])
        print(f"\n{file_record['file_name']}")
        print(f"  Path: {file_record['file_path']}")
        print(f"  Type: {file_record['file_type']}")
        print(f"  Date: {file_record['capture_date']}")
        print(f"  Tags: {', '.join(file_tags)}")


def show_file_info(file_path: str) -> bool:
    """Show detailed information about a file."""
    normalized_path = normalize_path(file_path)
    file_record = FileDB.find_by_path(normalized_path)

    if not file_record:
        print(f"Error: File not found in database: {file_path}")
        return False

    tags = FileTagDB.get_file_tags(file_record['id'])

    print("\nFile Information:")
    print("-" * 60)
    print(f"Name:          {file_record['file_name']}")
    print(f"Path:          {file_record['file_path']}")
    print(f"Type:          {file_record['file_type']}")
    print(f"Size:          {file_record['file_size']:,} bytes")
    print(f"Hash:          {file_record['hash'][:32]}...")
    print(f"Capture Date:  {file_record['capture_date']}")
    print(f"Import Date:   {file_record['import_date']}")

    if file_record['width'] and file_record['height']:
        print(f"Dimensions:    {file_record['width']} x {file_record['height']}")

    if file_record['duration']:
        mins = int(file_record['duration'] // 60)
        secs = int(file_record['duration'] % 60)
        print(f"Duration:      {mins}:{secs:02d}")

    if file_record['camera_make'] or file_record['camera_model']:
        camera = f"{file_record['camera_make'] or ''} {file_record['camera_model'] or ''}".strip()
        print(f"Camera:        {camera}")

    if tags:
        print(f"Tags:          {', '.join(tags)}")
    else:
        print("Tags:          (none)")

    return True


def list_files(file_type: str = None, limit: int = 20) -> None:
    """List files from database."""
    files = FileDB.get_all_files(file_type=file_type, limit=limit)

    type_str = file_type or "all"
    print(f"\nListing {type_str} files (limit: {limit}):")
    print("-" * 60)

    if not files:
        print("No files found.")
        return

    for file_record in files:
        tags = FileTagDB.get_file_tags(file_record['id'])
        tag_str = f"[{', '.join(tags)}]" if tags else ""

        print(f"{file_record['file_name']:<40} {file_record['capture_date']:<20} {tag_str}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Tag management for DAMn",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Add tags to a file
  %(prog)s add photo/2024/2024-03/2024-03-15/IMG_1234.jpg vacation beach sunset

  # Remove tags from a file
  %(prog)s remove photo/2024/2024-03/2024-03-15/IMG_1234.jpg beach

  # List tags on a file
  %(prog)s list photo/2024/2024-03/2024-03-15/IMG_1234.jpg

  # Show file information
  %(prog)s info photo/2024/2024-03/2024-03-15/IMG_1234.jpg

  # List all tags
  %(prog)s tags

  # Search files with ANY of these tags
  %(prog)s search vacation beach

  # Search files with ALL of these tags
  %(prog)s search --all vacation beach sunset

  # List recent files
  %(prog)s files --limit 50
  %(prog)s files --type photo --limit 10
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # Add command
    add_parser = subparsers.add_parser('add', help='Add tags to a file')
    add_parser.add_argument('file', help='File path')
    add_parser.add_argument('tags', nargs='+', help='Tags to add')

    # Remove command
    remove_parser = subparsers.add_parser('remove', help='Remove tags from a file')
    remove_parser.add_argument('file', help='File path')
    remove_parser.add_argument('tags', nargs='+', help='Tags to remove')

    # List command (list tags on a file)
    list_parser = subparsers.add_parser('list', help='List tags on a file')
    list_parser.add_argument('file', help='File path')

    # Info command
    info_parser = subparsers.add_parser('info', help='Show file information')
    info_parser.add_argument('file', help='File path')

    # Tags command (list all tags)
    subparsers.add_parser('tags', help='List all tags')

    # Search command
    search_parser = subparsers.add_parser('search', help='Search files by tags')
    search_parser.add_argument('tags', nargs='+', help='Tags to search for')
    search_parser.add_argument('--all', action='store_true', help='Match all tags (AND) instead of any (OR)')

    # Files command (list files)
    files_parser = subparsers.add_parser('files', help='List files')
    files_parser.add_argument('--type', choices=['photo', 'video'], help='Filter by file type')
    files_parser.add_argument('--limit', type=int, default=20, help='Limit number of results (default: 20)')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Initialize database
    init_database()

    # Route to appropriate function
    if args.command == 'add':
        add_tags(args.file, args.tags)

    elif args.command == 'remove':
        remove_tags(args.file, args.tags)

    elif args.command == 'list':
        list_file_tags(args.file)

    elif args.command == 'info':
        show_file_info(args.file)

    elif args.command == 'tags':
        list_all_tags()

    elif args.command == 'search':
        search_by_tags(args.tags, match_all=args.all)

    elif args.command == 'files':
        list_files(file_type=args.type, limit=args.limit)


if __name__ == "__main__":
    main()
