#!/usr/bin/env python3
"""
cleanup.py - Remove database entries for files that no longer exist on disk
"""

import sqlite3
import os

DB_PATH = 'dam.db'

def cleanup_deleted_files():
    """Remove DB entries for files that no longer exist"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("Scanning database for deleted files...")
    cursor.execute("SELECT id, path FROM files")
    files = cursor.fetchall()

    total_files = len(files)
    deleted_count = 0

    for file_id, path in files:
        if not os.path.exists(path):
            cursor.execute("DELETE FROM files WHERE id = ?", (file_id,))
            deleted_count += 1
            print(f"Removed: {path}")

    conn.commit()
    conn.close()

    print(f"\nScanned {total_files} files")
    print(f"Cleaned up {deleted_count} deleted files from database")

    if deleted_count == 0:
        print("Database is in sync - no orphaned entries found")

if __name__ == "__main__":
    cleanup_deleted_files()
