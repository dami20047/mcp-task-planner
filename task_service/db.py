"""
Tiny SQLite-backed storage layer for the task service.

All queries use parameterized statements (the `?` placeholders below) rather
than string-formatted SQL. This is the DB-layer half of our defense against
SQL injection -- the other half (rejecting suspicious input before it ever
gets here) lives in mcp_server/validation.py. Parameterized queries alone
would already stop classic SQL injection; we sanitize earlier too so a bad
payload never reaches the service at all, and so we have a boundary to test
in exploits/test_input_sanitization.py.
"""

import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(__file__).parent / "tasks.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                due_date TEXT NOT NULL,
                priority TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                UNIQUE(title, due_date)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def list_tasks(status: str = "pending") -> list[dict]:
    conn = get_connection()
    try:
        # Parameterized query -- `status` is bound, never string-concatenated.
        rows = conn.execute(
            "SELECT id, title, due_date, priority, status, created_at "
            "FROM tasks WHERE status = ? ORDER BY due_date ASC",
            (status,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def insert_task(title: str, due_date: str, priority: str) -> dict:
    conn = get_connection()
    try:
        created_at = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute(
            "INSERT INTO tasks (title, due_date, priority, status, created_at) "
            "VALUES (?, ?, ?, 'pending', ?)",
            (title, due_date, priority, created_at),
        )
        conn.commit()
        return {
            "id": cursor.lastrowid,
            "title": title,
            "due_date": due_date,
            "priority": priority,
            "status": "pending",
            "created_at": created_at,
        }
    finally:
        conn.close()
