#!/usr/bin/env python3
"""
app.py - FastAPI web UI for DAMn Digital Asset Management
"""

import os
from pathlib import Path
from typing import Optional, List
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import sqlite3

from database import FileDB, TagDB, FileTagDB

# Configuration
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "damn.db"

# Initialize FastAPI
app = FastAPI(title="DAMn - Digital Asset Manager")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Mount static directories for serving images and videos
app.mount("/static/photo", StaticFiles(directory=str(BASE_DIR / "photo")), name="photos")
app.mount("/static/video", StaticFiles(directory=str(BASE_DIR / "video")), name="videos")

# Database classes (used as static classes, no instantiation needed)
file_db = FileDB
tag_db = TagDB
file_tag_db = FileTagDB


# Pydantic models for API requests
class TagOperationRequest(BaseModel):
    file_ids: List[int]
    tags: List[str]


class DeleteFilesRequest(BaseModel):
    file_ids: List[int]


# Routes
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main page"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/stats")
async def get_stats():
    """Get database statistics"""
    stats = file_db.get_stats()
    return JSONResponse(stats)


@app.get("/api/files")
async def get_files(
    file_type: Optional[str] = None,
    tag: Optional[str] = None,
    folder: Optional[str] = None,
    page: int = 1,
    per_page: int = 50
):
    """
    Get files with optional filtering and pagination

    Args:
        file_type: Filter by 'photo' or 'video'
        tag: Filter by tag name
        folder: Filter by folder path (e.g., 'photo/2024/2024-03')
        page: Page number (1-indexed)
        per_page: Items per page
    """
    offset = (page - 1) * per_page

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Build query with filters
    query = """
        SELECT DISTINCT f.id, f.file_name, f.file_path, f.file_type,
               f.file_size, f.capture_date, f.width, f.height,
               f.camera_make, f.camera_model, f.duration
        FROM files f
    """

    where_clauses = []
    params = []

    if tag:
        query += """
            JOIN file_tags ft ON f.id = ft.file_id
            JOIN tags t ON ft.tag_id = t.id
        """
        where_clauses.append("t.name = ?")
        params.append(tag)

    if file_type:
        where_clauses.append("f.file_type = ?")
        params.append(file_type)

    if folder:
        where_clauses.append("f.file_path LIKE ?")
        params.append(f'%{folder}%')

    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)

    query += " ORDER BY f.capture_date DESC, f.file_name"

    # Get total count
    count_query = query.replace(
        "SELECT DISTINCT f.id, f.file_name, f.file_path, f.file_type, f.file_size, f.capture_date, f.width, f.height, f.camera_make, f.camera_model, f.duration",
        "SELECT COUNT(DISTINCT f.id)"
    )
    cursor.execute(count_query, params)
    total = cursor.fetchone()[0]

    # Get paginated results
    query += f" LIMIT ? OFFSET ?"
    params.extend([per_page, offset])

    cursor.execute(query, params)
    files = []

    for row in cursor.fetchall():
        file_data = dict(row)

        # Get tags for this file
        file_tags = file_tag_db.get_file_tags(file_data['id'])
        file_data['tags'] = file_tags  # Already returns list of tag names

        # Convert file path to relative web path for serving
        # Example: /opt/homebrew/var/www/DAMn/photo/2024/... -> /static/photo/2024/...
        file_path = Path(file_data['file_path'])
        path_parts = file_path.parts

        # Find where 'photo' or 'video' starts
        base_idx = -1
        for i, part in enumerate(path_parts):
            if part in ('photo', 'video'):
                base_idx = i
                break

        if base_idx >= 0:
            relative_path = '/'.join(path_parts[base_idx:])
            file_data['web_path'] = f'/static/{relative_path}'
        else:
            file_data['web_path'] = None

        files.append(file_data)

    conn.close()

    return {
        "files": files,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page
    }


@app.get("/api/tags")
async def get_tags():
    """Get all tags with file counts"""
    tags = tag_db.get_all_tags()
    return {"tags": tags}


@app.get("/api/folders")
async def get_folders():
    """Get all unique folder paths with file counts"""
    folders = file_db.get_folders()
    return {"folders": folders}


@app.get("/api/files/folder/select-all")
async def get_folder_file_ids(folder: Optional[str] = None):
    """
    Get all file IDs in a folder for select-all functionality

    Args:
        folder: Folder path to get all IDs from (e.g., 'photo/2024/2024-03')
    """
    if folder:
        file_ids = file_db.get_files_in_folder(folder)
    else:
        # No folder specified - get all files
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM files")
        file_ids = [row[0] for row in cursor.fetchall()]
        conn.close()

    return {"file_ids": file_ids, "count": len(file_ids)}


@app.post("/api/tags/add")
async def add_tags(request: TagOperationRequest):
    """Add tags to multiple files"""
    added_count = 0

    for file_id in request.file_ids:
        for tag_name in request.tags:
            tag_name = tag_name.strip()
            if tag_name:
                try:
                    file_tag_db.add_tag_to_file(file_id, tag_name)
                    added_count += 1
                except Exception as e:
                    # Tag might already exist on file, continue
                    pass

    return {
        "success": True,
        "message": f"Added tags to {len(request.file_ids)} file(s)",
        "tags_added": added_count
    }


@app.post("/api/tags/remove")
async def remove_tags(request: TagOperationRequest):
    """Remove tags from multiple files"""
    removed_count = 0

    for file_id in request.file_ids:
        for tag_name in request.tags:
            tag_name = tag_name.strip()
            if tag_name:
                try:
                    file_tag_db.remove_tag_from_file(file_id, tag_name)
                    removed_count += 1
                except Exception as e:
                    # Tag might not exist on file, continue
                    pass

    return {
        "success": True,
        "message": f"Removed tags from {len(request.file_ids)} file(s)",
        "tags_removed": removed_count
    }


@app.post("/api/files/delete")
async def delete_files(request: DeleteFilesRequest):
    """Delete files from disk and database"""
    deleted_count = 0
    errors = []

    for file_id in request.file_ids:
        try:
            # Get file info
            file_info = file_db.find_by_id(file_id)
            if not file_info:
                errors.append(f"File ID {file_id} not found in database")
                continue

            file_path = file_info['file_path']

            # Delete from filesystem
            if os.path.exists(file_path):
                os.remove(file_path)

            # Delete from database
            file_db.delete_file(file_id)
            deleted_count += 1

        except Exception as e:
            errors.append(f"Error deleting file ID {file_id}: {str(e)}")

    return {
        "success": deleted_count > 0,
        "message": f"Deleted {deleted_count} file(s)",
        "deleted_count": deleted_count,
        "errors": errors if errors else None
    }


if __name__ == "__main__":
    import uvicorn
    print("Starting DAMn Web UI...")
    print("Open http://localhost:8000 in your browser")
    uvicorn.run(app, host="0.0.0.0", port=8000)
