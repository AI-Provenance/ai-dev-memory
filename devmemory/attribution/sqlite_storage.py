from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Optional
import sqlite3
from devmemory.core.logging_config import get_logger

log = get_logger(__name__)

ATTRIBUTION_TTL_SECONDS = 365 * 24 * 3600  # 1 year


class SQLiteAttributionStorage:
    """Store and retrieve line-level AI attribution data in SQLite."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        log.debug(f"SQLiteAttributionStorage: initialized with {db_path}")

    def _get_conn(self) -> sqlite3.Connection:
        """Get database connection, creating if needed."""
        if self._conn is None:
            # Ensure directory exists
            db_dir = Path(self.db_path).parent
            db_dir.mkdir(parents=True, exist_ok=True)

            self._conn = sqlite3.connect(self.db_path, timeout=30.0)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._initialize_schema()
        return self._conn

    def _initialize_schema(self) -> None:
        """Create tables if they don't exist."""
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS attributions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                namespace TEXT NOT NULL,
                filepath TEXT NOT NULL,
                commit_sha TEXT NOT NULL,
                author_email TEXT,
                line_start INTEGER NOT NULL,
                line_end INTEGER NOT NULL,
                author TEXT NOT NULL,
                tool TEXT,
                model TEXT,
                prompt_id TEXT,
                confidence REAL DEFAULT 0.95,
                commit_timestamp INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(namespace, filepath, commit_sha, line_start, line_end)
            )
        """)

        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS file_latest (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                namespace TEXT NOT NULL,
                filepath TEXT NOT NULL,
                commit_sha TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(namespace, filepath)
            )
        """)

        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_attributions_lookup 
            ON attributions(namespace, filepath, commit_sha, line_start, line_end)
        """)

        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_attributions_namespace_filepath 
            ON attributions(namespace, filepath)
        """)

        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_attributions_commit_sha 
            ON attributions(commit_sha)
        """)

        self._conn.commit()
        log.debug("SQLite schema initialized")

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def get_attribution_count(self) -> int:
        """Get total number of attributions stored."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM attributions")
        return cursor.fetchone()[0]

    def store_attribution(
        self,
        namespace: str,
        filepath: str,
        commit_sha: str,
        author_email: str,
        line_ranges: dict[str, dict],
        commit_timestamp: Optional[int] = None,
    ) -> None:
        """
        Store line-level attribution for a file.

        Args:
            namespace: Repository namespace (e.g., "acme/payments")
            filepath: Source file path (e.g., "src/auth.js")
            commit_sha: Git commit SHA
            author_email: Committer email
            line_ranges: Dict mapping line ranges to attribution data
                         e.g., {"1-45": {"author": "ai", "tool": "cursor", "prompt_id": "abc"}}
            commit_timestamp: Unix timestamp of commit (for history sorting)
        """
        conn = self._get_conn()

        # Insert or update line ranges
        for range_str, attr in line_ranges.items():
            # Parse range string like "1-45" or "100"
            if "-" in range_str:
                start, end = map(int, range_str.split("-"))
            else:
                start = end = int(range_str)

            # Determine author type
            author = attr.get("author", "human")
            if author == "ai":
                author = "ai"
            else:
                author = "human"

            conn.execute(
                """
                INSERT INTO attributions (
                    namespace, filepath, commit_sha, author_email,
                    line_start, line_end, author, tool, model, prompt_id, confidence,
                    commit_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(namespace, filepath, commit_sha, line_start, line_end) 
                DO UPDATE SET
                    author = excluded.author,
                    tool = excluded.tool,
                    model = excluded.model,
                    prompt_id = excluded.prompt_id,
                    confidence = excluded.confidence
                """,
                (
                    namespace,
                    filepath,
                    commit_sha,
                    author_email,
                    start,
                    end,
                    author,
                    attr.get("tool"),
                    attr.get("model"),
                    attr.get("prompt_id"),
                    attr.get("confidence", 0.95),
                    commit_timestamp,
                ),
            )

        # Update latest pointer
        conn.execute(
            """
            INSERT INTO file_latest (namespace, filepath, commit_sha)
            VALUES (?, ?, ?)
            ON CONFLICT(namespace, filepath) DO UPDATE SET
                commit_sha = excluded.commit_sha,
                updated_at = CURRENT_TIMESTAMP
            """,
            (namespace, filepath, commit_sha),
        )

        conn.commit()
        log.debug(f"Stored attribution for {filepath}@{commit_sha[:8]} ({len(line_ranges)} ranges)")

    def get_attribution(
        self,
        namespace: str,
        filepath: str,
        commit_sha: str,
        lineno: int,
    ) -> Optional[dict]:
        """
        Get attribution for a specific line in a specific commit.

        Returns:
            Attribution dict with keys: author, tool, model, prompt_id, author_email
            Returns {"author": "human"} if no AI attribution found for the line.
        """
        conn = self._get_conn()

        cursor = conn.execute(
            """
            SELECT author, tool, model, prompt_id, author_email, confidence
            FROM attributions
            WHERE namespace = ? AND filepath = ? AND commit_sha = ?
            AND line_start <= ? AND line_end >= ?
            LIMIT 1
            """,
            (namespace, filepath, commit_sha, lineno, lineno),
        )

        row = cursor.fetchone()

        if row:
            return {
                "author": row[0],
                "tool": row[1],
                "model": row[2],
                "prompt_id": row[3],
                "author_email": row[4],
                "confidence": row[5] or 0.95,
                "commit_sha": commit_sha,
            }

        log.debug(f"No AI attribution for {filepath}:{lineno}, defaulting to human")
        return {"author": "human"}

    def get_latest_attribution(
        self,
        namespace: str,
        filepath: str,
        lineno: int,
        fallback_depth: int = 10,
    ) -> Optional[dict]:
        """
        Get the latest attribution for a specific line.

        This is the primary method for Sentry lookups - no commit SHA needed!

        Args:
            namespace: Repository namespace
            filepath: Source file path
            lineno: Line number
            fallback_depth: How many historical commits to check if not in latest (default: 10)

        Returns:
            Attribution dict or None if not found
        """
        conn = self._get_conn()

        # Get latest commit for this file
        cursor = conn.execute(
            """
            SELECT commit_sha FROM file_latest
            WHERE namespace = ? AND filepath = ?
            """,
            (namespace, filepath),
        )
        row = cursor.fetchone()

        if not row:
            return None

        latest_commit = row[0]

        # Try latest commit first
        attr = self.get_attribution(namespace, filepath, latest_commit, lineno)
        if attr and attr.get("author") != "human":
            attr["commit_sha"] = latest_commit
            return attr

        # Fallback: Check recent commits
        cursor = conn.execute(
            """
            SELECT DISTINCT commit_sha FROM attributions
            WHERE namespace = ? AND filepath = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (namespace, filepath, fallback_depth),
        )

        rows = cursor.fetchall()
        for row in rows:
            commit_sha = row[0]
            if commit_sha == latest_commit:
                continue

            attr = self.get_attribution(namespace, filepath, commit_sha, lineno)
            if attr and attr.get("author") != "human":
                log.debug(f"Found attribution in history: {filepath}:{lineno} @ {commit_sha[:8]}")
                attr["commit_sha"] = commit_sha
                return attr

        log.debug(f"No attribution found for {filepath}:{lineno}")
        return None

    def get_file_history(
        self,
        namespace: str,
        filepath: str,
        limit: int = 50,
    ) -> list[dict]:
        """
        Get commit history for a file.

        Returns:
            List of dicts with commit_sha and timestamp, sorted by most recent first
        """
        conn = self._get_conn()

        cursor = conn.execute(
            """
            SELECT DISTINCT commit_sha, commit_timestamp
            FROM attributions
            WHERE namespace = ? AND filepath = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (namespace, filepath, limit),
        )

        rows = cursor.fetchall()
        return [
            {
                "commit_sha": row[0],
                "timestamp": row[1],
            }
            for row in rows
        ]

    def get_file_attribution_summary(
        self,
        namespace: str,
        filepath: str,
        commit_sha: str,
    ) -> Optional[dict]:
        """
        Get summary of AI vs human lines for a file.

        Returns:
            Dict with ai_lines, human_lines, total_lines, ai_percentage
        """
        conn = self._get_conn()

        cursor = conn.execute(
            """
            SELECT 
                SUM(CASE WHEN author = 'ai' THEN line_end - line_start + 1 ELSE 0 END) as ai_lines,
                SUM(CASE WHEN author = 'human' THEN line_end - line_start + 1 ELSE 0 END) as human_lines
            FROM attributions
            WHERE namespace = ? AND filepath = ? AND commit_sha = ?
            GROUP BY commit_sha
            """,
            (namespace, filepath, commit_sha),
        )

        row = cursor.fetchone()

        if not row:
            return None

        ai_lines = row[0] or 0
        human_lines = row[1] or 0
        total = ai_lines + human_lines

        if total == 0:
            return None

        return {
            "ai_lines": ai_lines,
            "human_lines": human_lines,
            "total_lines": total,
            "ai_percentage": round((ai_lines / total) * 100, 1),
        }
