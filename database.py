import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import DB_PATH


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id      INTEGER PRIMARY KEY,
    username     TEXT,
    first_name   TEXT,
    last_name    TEXT,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS attempts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL,
    subject       TEXT NOT NULL,
    total         INTEGER NOT NULL DEFAULT 0,
    correct       INTEGER NOT NULL DEFAULT 0,
    skipped       INTEGER NOT NULL DEFAULT 0,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS answers (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id    INTEGER NOT NULL,
    q_number      INTEGER NOT NULL,
    chosen        TEXT,
    correct       TEXT NOT NULL,
    is_correct    INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (attempt_id) REFERENCES attempts(id)
);

CREATE INDEX IF NOT EXISTS idx_attempts_user ON attempts(user_id);
CREATE INDEX IF NOT EXISTS idx_attempts_subject ON attempts(subject);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def upsert_user(user_id: int, username: str, first_name: str, last_name: str) -> None:
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT user_id FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE users SET username = ?, first_name = ?, last_name = ?
                   WHERE user_id = ?""",
                (username, first_name, last_name, user_id),
            )
        else:
            conn.execute(
                """INSERT INTO users (user_id, username, first_name, last_name, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, username, first_name, last_name, datetime.utcnow().isoformat()),
            )


def start_attempt(user_id: int, subject: str, total: int) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO attempts (user_id, subject, total, started_at)
               VALUES (?, ?, ?, ?)""",
            (user_id, subject, total, datetime.utcnow().isoformat()),
        )
        return cur.lastrowid


def record_answer(
    attempt_id: int,
    q_number: int,
    chosen: Optional[str],
    correct: str,
) -> bool:
    is_correct = 1 if chosen and chosen.upper() == correct.upper() else 0
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO answers (attempt_id, q_number, chosen, correct, is_correct)
               VALUES (?, ?, ?, ?, ?)""",
            (attempt_id, q_number, chosen, correct, is_correct),
        )
        if chosen is None:
            conn.execute(
                "UPDATE attempts SET skipped = skipped + 1 WHERE id = ?", (attempt_id,)
            )
        if is_correct:
            conn.execute(
                "UPDATE attempts SET correct = correct + 1 WHERE id = ?", (attempt_id,)
            )
    return bool(is_correct)


def finish_attempt(attempt_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE attempts SET finished_at = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), attempt_id),
        )


def get_attempt(attempt_id: int) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM attempts WHERE id = ?", (attempt_id,)
        ).fetchone()


def get_user_attempts(user_id: int, limit: int = 10) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """SELECT * FROM attempts WHERE user_id = ?
               ORDER BY started_at DESC LIMIT ?""",
            (user_id, limit),
        ).fetchall()


def stats_overview() -> dict:
    with get_conn() as conn:
        users = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        attempts = conn.execute(
            "SELECT COUNT(*) AS c FROM attempts WHERE finished_at IS NOT NULL"
        ).fetchone()["c"]
        avg = conn.execute(
            """SELECT AVG(CAST(correct AS REAL) / NULLIF(total, 0)) AS a
               FROM attempts WHERE finished_at IS NOT NULL"""
        ).fetchone()["a"]
        per_subject = conn.execute(
            """SELECT subject, COUNT(*) AS c FROM attempts
               WHERE finished_at IS NOT NULL GROUP BY subject"""
        ).fetchall()
    return {
        "users": users,
        "attempts": attempts,
        "avg_score": avg or 0.0,
        "per_subject": [(r["subject"], r["c"]) for r in per_subject],
    }


def list_users(limit: int = 50) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """SELECT u.*,
                      (SELECT COUNT(*) FROM attempts a WHERE a.user_id = u.user_id) AS attempts_count
               FROM users u ORDER BY u.created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()


def top_results(subject: Optional[str] = None, limit: int = 10) -> list[sqlite3.Row]:
    """Return one row per user — their most recent finished attempt.

    The leaderboard reflects each user's CURRENT standing (their latest
    attempt's score), then ordered by that score so the strongest is on
    top. Retaking the test changes your rank — for better or worse.
    """
    with get_conn() as conn:
        if subject:
            return conn.execute(
                """
                SELECT * FROM (
                    SELECT a.*, u.first_name, u.username,
                           ROW_NUMBER() OVER (
                               PARTITION BY a.user_id
                               ORDER BY a.finished_at DESC
                           ) AS rn
                    FROM attempts a
                    JOIN users u ON u.user_id = a.user_id
                    WHERE a.finished_at IS NOT NULL AND a.subject = ?
                ) WHERE rn = 1
                ORDER BY CAST(correct AS REAL)/NULLIF(total,0) DESC, finished_at ASC
                LIMIT ?
                """,
                (subject, limit),
            ).fetchall()
        return conn.execute(
            """
            SELECT * FROM (
                SELECT a.*, u.first_name, u.username,
                       ROW_NUMBER() OVER (
                           PARTITION BY a.user_id
                           ORDER BY a.finished_at DESC
                       ) AS rn
                FROM attempts a
                JOIN users u ON u.user_id = a.user_id
                WHERE a.finished_at IS NOT NULL
            ) WHERE rn = 1
            ORDER BY CAST(correct AS REAL)/NULLIF(total,0) DESC, finished_at ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def best_attempt(user_id: int, subject: Optional[str] = None) -> Optional[sqlite3.Row]:
    """Return the user's best finished attempt (for showing 'personal best')."""
    with get_conn() as conn:
        if subject:
            return conn.execute(
                """SELECT * FROM attempts
                   WHERE user_id = ? AND finished_at IS NOT NULL AND subject = ?
                   ORDER BY CAST(correct AS REAL)/NULLIF(total,0) DESC,
                            finished_at ASC LIMIT 1""",
                (user_id, subject),
            ).fetchone()
        return conn.execute(
            """SELECT * FROM attempts
               WHERE user_id = ? AND finished_at IS NOT NULL
               ORDER BY CAST(correct AS REAL)/NULLIF(total,0) DESC,
                        finished_at ASC LIMIT 1""",
            (user_id,),
        ).fetchone()


def all_user_ids() -> list[int]:
    with get_conn() as conn:
        rows = conn.execute("SELECT user_id FROM users").fetchall()
    return [r["user_id"] for r in rows]
