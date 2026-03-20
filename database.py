#!/usr/bin/env python3
"""
Database module for DAMn - Digital Asset Manager
Manages SQLite database for file tracking and tagging
"""

import sqlite3
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Tuple, Dict
from contextlib import contextmanager

# Database location
DB_PATH = Path(__file__).parent / "damn.db"


@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Enable column access by name
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_database():
    """Initialize the database schema."""
    with get_db() as conn:
        cursor = conn.cursor()

        # Files table - stores metadata about each imported file
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hash TEXT UNIQUE NOT NULL,
                file_path TEXT UNIQUE NOT NULL,
                file_name TEXT NOT NULL,
                file_type TEXT NOT NULL,  -- 'photo' or 'video'
                file_size INTEGER NOT NULL,
                file_extension TEXT NOT NULL,

                -- Dates
                capture_date TIMESTAMP,  -- From EXIF/metadata
                file_mtime TIMESTAMP NOT NULL,  -- File modification time
                import_date TIMESTAMP NOT NULL,  -- When imported into DAMn

                -- Dimensions (for photos/videos)
                width INTEGER,
                height INTEGER,
                duration REAL,  -- Video duration in seconds

                -- Metadata
                camera_make TEXT,
                camera_model TEXT,

                -- Index
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Tags table - stores unique tags
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                color TEXT,  -- Optional color code for UI
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # File-Tag relationship table (many-to-many)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS file_tags (
                file_id INTEGER NOT NULL,
                tag_id INTEGER NOT NULL,
                tagged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (file_id, tag_id),
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
                FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
            )
        """)

        # Create indices for better performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_hash ON files(hash)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_type ON files(file_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_capture_date ON files(capture_date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_path ON files(file_path)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_file_tags_file ON file_tags(file_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_file_tags_tag ON file_tags(tag_id)")

        print(f"Database initialized at {DB_PATH}")


class FileDB:
    """Database operations for files."""

    @staticmethod
    def add_file(
        hash: str,
        file_path: str,
        file_name: str,
        file_type: str,
        file_size: int,
        file_extension: str,
        file_mtime: datetime,
        capture_date: Optional[datetime] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        duration: Optional[float] = None,
        camera_make: Optional[str] = None,
        camera_model: Optional[str] = None,
    ) -> Optional[int]:
        """
        Add a file to the database.
        Returns file_id if successful, None if file already exists.
        """
        with get_db() as conn:
            cursor = conn.cursor()

            try:
                cursor.execute("""
                    INSERT INTO files (
                        hash, file_path, file_name, file_type, file_size, file_extension,
                        capture_date, file_mtime, import_date,
                        width, height, duration, camera_make, camera_model
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    hash, file_path, file_name, file_type, file_size, file_extension,
                    capture_date, file_mtime, datetime.now(),
                    width, height, duration, camera_make, camera_model
                ))

                return cursor.lastrowid

            except sqlite3.IntegrityError:
                # File with this hash or path already exists
                return None

    @staticmethod
    def find_by_hash(hash: str) -> Optional[Dict]:
        """Find a file by its hash. Returns file record or None."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM files WHERE hash = ?", (hash,))
            row = cursor.fetchone()

            if row:
                return dict(row)
            return None

    @staticmethod
    def find_by_path(file_path: str) -> Optional[Dict]:
        """Find a file by its path. Returns file record or None."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM files WHERE file_path = ?", (file_path,))
            row = cursor.fetchone()

            if row:
                return dict(row)
            return None

    @staticmethod
    def find_by_id(file_id: int) -> Optional[Dict]:
        """Find a file by its ID. Returns file record or None."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM files WHERE id = ?", (file_id,))
            row = cursor.fetchone()

            if row:
                return dict(row)
            return None

    @staticmethod
    def update_file_path(hash: str, new_path: str) -> bool:
        """Update the file path for a file (when moved). Returns success status."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE files
                SET file_path = ?, updated_at = CURRENT_TIMESTAMP
                WHERE hash = ?
            """, (new_path, hash))

            return cursor.rowcount > 0

    @staticmethod
    def delete_file(file_id: int) -> bool:
        """Delete a file from database. Returns success status."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM files WHERE id = ?", (file_id,))
            return cursor.rowcount > 0

    @staticmethod
    def get_all_files(file_type: Optional[str] = None, limit: Optional[int] = None) -> List[Dict]:
        """
        Get all files, optionally filtered by type.
        Returns list of file records.
        """
        with get_db() as conn:
            cursor = conn.cursor()

            if file_type:
                query = "SELECT * FROM files WHERE file_type = ? ORDER BY capture_date DESC"
                params = (file_type,)
            else:
                query = "SELECT * FROM files ORDER BY capture_date DESC"
                params = ()

            if limit:
                query += f" LIMIT {limit}"

            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def get_stats() -> Dict:
        """Get database statistics."""
        with get_db() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) as total FROM files")
            total = cursor.fetchone()['total']

            cursor.execute("SELECT COUNT(*) as count FROM files WHERE file_type = 'photo'")
            photos = cursor.fetchone()['count']

            cursor.execute("SELECT COUNT(*) as count FROM files WHERE file_type = 'video'")
            videos = cursor.fetchone()['count']

            cursor.execute("SELECT COUNT(*) as count FROM tags")
            tags = cursor.fetchone()['count']

            return {
                'total_files': total,
                'total_photos': photos,
                'total_videos': videos,
                'total_tags': tags
            }

    @staticmethod
    def get_folders() -> List[Dict]:
        """
        Extract unique folder paths from file_path.
        Returns list of {path: str, count: int, type: str}.
        """
        with get_db() as conn:
            cursor = conn.cursor()

            # Get all file paths and extract folder structure
            cursor.execute("SELECT file_path, file_type FROM files")
            rows = cursor.fetchall()

            folder_counts = {}

            for row in rows:
                file_path = row['file_path']
                file_type = row['file_type']

                # Extract folder path (everything before the filename)
                # Example: /opt/homebrew/var/www/DAMn/photo/2024/2024-03/2024-03-15/file.jpg
                # -> photo/2024/2024-03/2024-03-15
                path_parts = Path(file_path).parts

                # Find where 'photo' or 'video' starts and take everything after that
                base_idx = -1
                for i, part in enumerate(path_parts):
                    if part in ('photo', 'video'):
                        base_idx = i
                        break

                if base_idx >= 0:
                    # Get folder path relative to base (photo/2024/2024-03/2024-03-15)
                    folder_parts = path_parts[base_idx:-1]  # Exclude filename
                    folder_path = '/'.join(folder_parts) if folder_parts else ''

                    if folder_path:
                        key = (folder_path, file_type)
                        folder_counts[key] = folder_counts.get(key, 0) + 1

            # Convert to list of dicts
            result = []
            for (path, ftype), count in sorted(folder_counts.items()):
                result.append({
                    'path': path,
                    'count': count,
                    'type': ftype
                })

            return result

    @staticmethod
    def get_files_in_folder(folder_path: str) -> List[int]:
        """
        Get all file IDs in a specific folder.
        folder_path should be relative (e.g., 'photo/2024/2024-03/2024-03-15').
        Returns list of file IDs.
        """
        with get_db() as conn:
            cursor = conn.cursor()

            # Use LIKE to match folder path
            cursor.execute("""
                SELECT id FROM files
                WHERE file_path LIKE ?
            """, (f'%{folder_path}%',))

            return [row['id'] for row in cursor.fetchall()]


class TagDB:
    """Database operations for tags."""

    @staticmethod
    def create_tag(name: str, description: Optional[str] = None, color: Optional[str] = None) -> Optional[int]:
        """
        Create a new tag.
        Returns tag_id if successful, None if tag already exists.
        """
        with get_db() as conn:
            cursor = conn.cursor()

            try:
                cursor.execute("""
                    INSERT INTO tags (name, description, color)
                    VALUES (?, ?, ?)
                """, (name.lower(), description, color))

                return cursor.lastrowid

            except sqlite3.IntegrityError:
                # Tag already exists
                return None

    @staticmethod
    def get_tag(name: str) -> Optional[Dict]:
        """Get a tag by name. Returns tag record or None."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tags WHERE name = ?", (name.lower(),))
            row = cursor.fetchone()

            if row:
                return dict(row)
            return None

    @staticmethod
    def get_or_create_tag(name: str) -> int:
        """Get existing tag or create new one. Returns tag_id."""
        tag = TagDB.get_tag(name)

        if tag:
            return tag['id']
        else:
            tag_id = TagDB.create_tag(name)
            return tag_id

    @staticmethod
    def get_all_tags() -> List[Dict]:
        """Get all tags. Returns list of tag records."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tags ORDER BY name")
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def delete_tag(tag_id: int) -> bool:
        """Delete a tag (and all associations). Returns success status."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
            return cursor.rowcount > 0

    @staticmethod
    def rename_tag(old_name: str, new_name: str) -> bool:
        """Rename a tag. Returns success status."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE tags
                SET name = ?, updated_at = CURRENT_TIMESTAMP
                WHERE name = ?
            """, (new_name.lower(), old_name.lower()))

            return cursor.rowcount > 0


class FileTagDB:
    """Database operations for file-tag relationships."""

    @staticmethod
    def add_tag_to_file(file_id: int, tag_name: str) -> bool:
        """
        Add a tag to a file. Creates tag if it doesn't exist.
        Returns success status.
        """
        tag_id = TagDB.get_or_create_tag(tag_name)

        with get_db() as conn:
            cursor = conn.cursor()

            try:
                cursor.execute("""
                    INSERT INTO file_tags (file_id, tag_id)
                    VALUES (?, ?)
                """, (file_id, tag_id))

                return True

            except sqlite3.IntegrityError:
                # Tag already associated with this file
                return False

    @staticmethod
    def remove_tag_from_file(file_id: int, tag_name: str) -> bool:
        """Remove a tag from a file. Returns success status."""
        tag = TagDB.get_tag(tag_name)

        if not tag:
            return False

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM file_tags
                WHERE file_id = ? AND tag_id = ?
            """, (file_id, tag['id']))

            return cursor.rowcount > 0

    @staticmethod
    def get_file_tags(file_id: int) -> List[str]:
        """Get all tags for a file. Returns list of tag names."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT t.name
                FROM tags t
                JOIN file_tags ft ON t.id = ft.tag_id
                WHERE ft.file_id = ?
                ORDER BY t.name
            """, (file_id,))

            return [row['name'] for row in cursor.fetchall()]

    @staticmethod
    def get_files_by_tag(tag_name: str) -> List[Dict]:
        """Get all files with a specific tag. Returns list of file records."""
        tag = TagDB.get_tag(tag_name)

        if not tag:
            return []

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT f.*
                FROM files f
                JOIN file_tags ft ON f.id = ft.file_id
                WHERE ft.tag_id = ?
                ORDER BY f.capture_date DESC
            """, (tag['id'],))

            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def search_files_by_tags(tag_names: List[str], match_all: bool = False) -> List[Dict]:
        """
        Search files by multiple tags.

        Args:
            tag_names: List of tag names to search for
            match_all: If True, returns files with ALL tags. If False, returns files with ANY tag.

        Returns:
            List of file records
        """
        if not tag_names:
            return []

        with get_db() as conn:
            cursor = conn.cursor()

            if match_all:
                # Files must have ALL tags
                placeholders = ','.join(['?' for _ in tag_names])
                query = f"""
                    SELECT f.*
                    FROM files f
                    JOIN file_tags ft ON f.id = ft.file_id
                    JOIN tags t ON ft.tag_id = t.id
                    WHERE t.name IN ({placeholders})
                    GROUP BY f.id
                    HAVING COUNT(DISTINCT t.id) = ?
                    ORDER BY f.capture_date DESC
                """
                params = [name.lower() for name in tag_names] + [len(tag_names)]

            else:
                # Files can have ANY tag
                placeholders = ','.join(['?' for _ in tag_names])
                query = f"""
                    SELECT DISTINCT f.*
                    FROM files f
                    JOIN file_tags ft ON f.id = ft.file_id
                    JOIN tags t ON ft.tag_id = t.id
                    WHERE t.name IN ({placeholders})
                    ORDER BY f.capture_date DESC
                """
                params = [name.lower() for name in tag_names]

            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]


if __name__ == "__main__":
    # Initialize database if run directly
    init_database()
    print("Database schema created successfully!")

    stats = FileDB.get_stats()
    print(f"\nCurrent stats:")
    print(f"  Files: {stats['total_files']}")
    print(f"  Photos: {stats['photos']}")
    print(f"  Videos: {stats['videos']}")
    print(f"  Tags: {stats['tags']}")
