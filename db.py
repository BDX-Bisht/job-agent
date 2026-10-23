"""SQLite storage: dedupe by apply URL, remember when we first saw each job."""
import hashlib
import os
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.getenv("JOBS_DB", os.path.join(os.path.dirname(__file__), "jobs.db"))


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init():
    with _conn() as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                company TEXT, title TEXT, location TEXT,
                url TEXT, apply_url TEXT,
                posted_at TEXT,          -- real posting date if the source gives one (UTC ISO)
                first_seen_at TEXT,      -- when this app first saw the job (UTC ISO)
                description TEXT, source TEXT,
                active INTEGER DEFAULT 1
            )"""
        )


def job_id(job):
    key = job.get("apply_url") or job.get("url") or f"{job['company']}|{job['title']}|{job['location']}"
    return hashlib.sha1(key.encode()).hexdigest()


def upsert(jobs):
    """Insert new jobs, refresh existing ones. Returns number of NEW jobs."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    new = 0
    with _conn() as c:
        for j in jobs:
            jid = job_id(j)
            exists = c.execute("SELECT 1 FROM jobs WHERE id=?", (jid,)).fetchone()
            if exists:
                c.execute(
                    """UPDATE jobs SET title=?, location=?, description=?, posted_at=COALESCE(?, posted_at),
                       active=1 WHERE id=?""",
                    (j["title"], j["location"], j["description"], j["posted_at"], jid),
                )
            else:
                new += 1
                c.execute(
                    """INSERT INTO jobs (id, company, title, location, url, apply_url, posted_at,
                       first_seen_at, description, source, active) VALUES (?,?,?,?,?,?,?,?,?,?,1)""",
                    (jid, j["company"], j["title"], j["location"], j["url"], j["apply_url"],
                     j["posted_at"], now, j["description"], j["source"]),
                )
    return new


def mark_closed(company, seen_jobs):
    """Jobs of `company` that were not in the latest fetch are marked inactive."""
    seen = {job_id(j) for j in seen_jobs}
    with _conn() as c:
        rows = c.execute("SELECT id FROM jobs WHERE company=? AND active=1", (company,)).fetchall()
        for r in rows:
            if r["id"] not in seen:
                c.execute("UPDATE jobs SET active=0 WHERE id=?", (r["id"],))


def list_jobs():
    """Active jobs, newest first (posted_at, falling back to first_seen_at)."""
    with _conn() as c:
        rows = c.execute(
            """SELECT *, COALESCE(posted_at, first_seen_at) AS sort_at,
                      CASE WHEN posted_at IS NULL THEN 'first seen' ELSE 'posted' END AS date_kind
               FROM jobs WHERE active=1 ORDER BY sort_at DESC"""
        ).fetchall()
    return [dict(r) for r in rows]
