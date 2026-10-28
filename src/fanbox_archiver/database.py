from __future__ import annotations

import json
import sqlite3
import shutil
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

from .models import Asset, AssetStatus, Post, PostStatus
from .client import PostSummary


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS creators (
  creator_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  url TEXT,
  last_checked_at TEXT,
  icon_url TEXT,
  icon_path TEXT,
  icon_sha256 TEXT
);
CREATE TABLE IF NOT EXISTS posts (
  post_id TEXT PRIMARY KEY,
  creator_id TEXT NOT NULL REFERENCES creators(creator_id),
  title TEXT NOT NULL,
  published_at TEXT,
  updated_at TEXT,
  status TEXT NOT NULL,
  local_path TEXT,
  content_fingerprint TEXT,
  is_pinned INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  last_checked_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  asset_id TEXT NOT NULL,
  post_id TEXT NOT NULL REFERENCES posts(post_id) ON DELETE CASCADE,
  type TEXT NOT NULL,
  source_url TEXT NOT NULL,
  original_name TEXT,
  local_path TEXT,
  size INTEGER,
  sha256 TEXT,
  etag TEXT,
  last_modified TEXT,
  status TEXT NOT NULL,
  error TEXT,
  UNIQUE(post_id, asset_id, source_url)
);
CREATE TABLE IF NOT EXISTS backup_runs (
  run_id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  scope TEXT NOT NULL,
  success_count INTEGER NOT NULL DEFAULT 0,
  failure_count INTEGER NOT NULL DEFAULT 0,
  dry_run INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS creator_sync_state (
  creator_id TEXT PRIMARY KEY REFERENCES creators(creator_id),
  is_supporting INTEGER NOT NULL DEFAULT 0,
  last_seen_supporting_at TEXT,
  last_recent_check_at TEXT,
  backfill_cursor TEXT,
  backfill_completed INTEGER NOT NULL DEFAULT 0,
  last_success_at TEXT,
  last_error TEXT
);
CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS post_versions (
  version_id INTEGER PRIMARY KEY AUTOINCREMENT,
  post_id TEXT NOT NULL REFERENCES posts(post_id) ON DELETE CASCADE,
  version_number INTEGER NOT NULL,
  remote_updated_at TEXT,
  captured_at TEXT,
  content_fingerprint TEXT NOT NULL,
  status TEXT NOT NULL,
  local_path TEXT NOT NULL,
  markdown_path TEXT,
  json_path TEXT,
  last_error TEXT,
  UNIQUE(post_id, version_number),
  UNIQUE(post_id, content_fingerprint)
);
CREATE TABLE IF NOT EXISTS fancard_versions (
  fancard_version_id INTEGER PRIMARY KEY AUTOINCREMENT,
  creator_id TEXT NOT NULL REFERENCES creators(creator_id),
  target_month TEXT NOT NULL,
  version_number INTEGER NOT NULL,
  captured_at TEXT NOT NULL,
  content_fingerprint TEXT NOT NULL,
  status TEXT NOT NULL,
  local_path TEXT NOT NULL,
  image_path TEXT,
  image_sha256 TEXT,
  last_error TEXT,
  UNIQUE(creator_id,target_month,version_number),
  UNIQUE(creator_id,target_month,content_fingerprint)
);
CREATE TABLE IF NOT EXISTS creator_profile_versions (
  profile_version_id INTEGER PRIMARY KEY AUTOINCREMENT,
  creator_id TEXT NOT NULL REFERENCES creators(creator_id),
  version_number INTEGER NOT NULL,
  captured_at TEXT NOT NULL,
  content_fingerprint TEXT NOT NULL,
  status TEXT NOT NULL,
  local_path TEXT NOT NULL,
  json_path TEXT NOT NULL,
  cover_path TEXT,
  cover_sha256 TEXT,
  last_error TEXT,
  UNIQUE(creator_id,version_number),
  UNIQUE(creator_id,content_fingerprint)
);
CREATE TABLE IF NOT EXISTS web_jobs (
  job_id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  status TEXT NOT NULL,
  request_json TEXT NOT NULL,
  result_json TEXT,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  updated_at TEXT NOT NULL,
  error TEXT
);
CREATE TABLE IF NOT EXISTS web_job_events (
  event_id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT NOT NULL REFERENCES web_jobs(job_id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  timestamp TEXT NOT NULL,
  data_json TEXT NOT NULL,
  coalesce_key TEXT
);
CREATE INDEX IF NOT EXISTS idx_posts_creator ON posts(creator_id);
CREATE INDEX IF NOT EXISTS idx_assets_status ON assets(status);
CREATE INDEX IF NOT EXISTS idx_post_versions_post ON post_versions(post_id,version_number);
CREATE INDEX IF NOT EXISTS idx_fancard_versions_creator ON fancard_versions(creator_id,target_month,version_number);
CREATE INDEX IF NOT EXISTS idx_profile_versions_creator ON creator_profile_versions(creator_id,version_number);
CREATE INDEX IF NOT EXISTS idx_web_jobs_updated ON web_jobs(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_web_job_events_job ON web_job_events(job_id,event_id);
"""

SCHEMA_VERSION = 8


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class Database:
    def __init__(self, path: Path):
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._backup_before_migration()
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            self._migrate(connection)

    def _backup_before_migration(self) -> None:
        if not self.path.exists() or self.path.stat().st_size == 0:
            return
        with sqlite3.connect(self.path) as db:
            exists = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
            ).fetchone()
            version = db.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] if exists else 0
        if int(version or 0) >= SCHEMA_VERSION:
            return
        backup = self.path.with_name(f"{self.path.name}.pre-v{SCHEMA_VERSION}.bak")
        if not backup.exists():
            shutil.copy2(self.path, backup)

    @staticmethod
    def _migrate(db: sqlite3.Connection) -> None:
        columns = {row["name"] for row in db.execute("PRAGMA table_info(backup_runs)")}
        for name in ("discovered_count", "new_count", "updated_count", "skipped_count", "retried_count"):
            if name not in columns:
                db.execute(f"ALTER TABLE backup_runs ADD COLUMN {name} INTEGER NOT NULL DEFAULT 0")
        if "dry_run" not in columns:
            db.execute("ALTER TABLE backup_runs ADD COLUMN dry_run INTEGER NOT NULL DEFAULT 0")
            db.execute(
                "UPDATE backup_runs SET dry_run=1 WHERE success_count=0 AND failure_count=0 "
                "AND (discovered_count>0 OR new_count>0 OR updated_count>0 OR retried_count>0)"
            )
        post_columns = {row["name"] for row in db.execute("PRAGMA table_info(posts)")}
        if "latest_version_id" not in post_columns:
            db.execute("ALTER TABLE posts ADD COLUMN latest_version_id INTEGER")
        if "is_pinned" not in post_columns:
            db.execute("ALTER TABLE posts ADD COLUMN is_pinned INTEGER NOT NULL DEFAULT 0")
            Database._backfill_post_pins(db)
        creator_columns = {row["name"] for row in db.execute("PRAGMA table_info(creators)")}
        for name in ("icon_url", "icon_path", "icon_sha256"):
            if name not in creator_columns:
                db.execute(f"ALTER TABLE creators ADD COLUMN {name} TEXT")
        if "latest_profile_version_id" not in creator_columns:
            db.execute("ALTER TABLE creators ADD COLUMN latest_profile_version_id INTEGER")
        db.execute(
            "INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES(?,?)",
            (SCHEMA_VERSION, now_iso()),
        )

    @staticmethod
    def _backfill_post_pins(db: sqlite3.Connection) -> None:
        rows = db.execute(
            "SELECT p.post_id,v.json_path,v.local_path FROM posts p "
            "LEFT JOIN post_versions v ON v.version_id=("
            "SELECT candidate.version_id FROM post_versions candidate "
            "WHERE candidate.post_id=p.post_id AND candidate.status='completed' "
            "ORDER BY candidate.version_number DESC LIMIT 1)"
        )
        for row in rows:
            candidates = []
            if row["json_path"]:
                candidates.append(Path(str(row["json_path"])))
            if row["local_path"]:
                candidates.append(Path(str(row["local_path"])) / "post.json")
            for path in candidates:
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError, TypeError):
                    continue
                raw = payload.get("raw") if isinstance(payload, dict) else None
                is_pinned = bool(raw.get("isPinned", False)) if isinstance(raw, dict) else False
                db.execute(
                    "UPDATE posts SET is_pinned=? WHERE post_id=?",
                    (int(is_pinned), row["post_id"]),
                )
                break

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def upsert_post(self, post: Post, local_path: str, status: PostStatus = PostStatus.PENDING) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO creators(creator_id,name,url,last_checked_at,icon_url) VALUES(?,?,?,?,?) "
                "ON CONFLICT(creator_id) DO UPDATE SET name=excluded.name,last_checked_at=excluded.last_checked_at,"
                "icon_url=COALESCE(excluded.icon_url,creators.icon_url)",
                (post.creator_id, post.creator_name, f"https://www.fanbox.cc/@{post.creator_id}", now_iso(),
                 post.creator_icon_url),
            )
            db.execute(
                "INSERT INTO posts(post_id,creator_id,title,published_at,updated_at,status,local_path,content_fingerprint,is_pinned,last_checked_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(post_id) DO UPDATE SET title=excluded.title,"
                "updated_at=excluded.updated_at,status=excluded.status,local_path=excluded.local_path,"
                "content_fingerprint=excluded.content_fingerprint,is_pinned=excluded.is_pinned,"
                "last_checked_at=excluded.last_checked_at",
                (post.post_id, post.creator_id, post.title,
                 post.published_at.isoformat() if post.published_at else None,
                 post.updated_at.isoformat() if post.updated_at else None,
                 status.value, local_path, post.content_fingerprint,
                 int(bool(post.raw.get("isPinned", False))), now_iso()),
            )
            for asset in [*post.assets, *([post.cover] if post.cover else [])]:
                db.execute(
                    "INSERT INTO assets(asset_id,post_id,type,source_url,original_name,local_path,size,sha256,etag,last_modified,status,error) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(post_id,asset_id,source_url) DO UPDATE SET "
                    "local_path=excluded.local_path,size=excluded.size,sha256=excluded.sha256,etag=excluded.etag,"
                    "last_modified=excluded.last_modified,status=excluded.status,error=excluded.error",
                    (asset.asset_id, post.post_id, asset.type, asset.url, asset.original_name, asset.local_path,
                     asset.size, asset.sha256, asset.etag, asset.last_modified, asset.status.value, asset.error),
                )

    def post_row(self, post_id: str) -> sqlite3.Row | None:
        with self.connect() as db:
            return db.execute("SELECT * FROM posts WHERE post_id=?", (post_id,)).fetchone()

    def set_post_pinned(self, post_id: str, is_pinned: bool) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE posts SET is_pinned=? WHERE post_id=?",
                (int(is_pinned), post_id),
            )

    def post_local_paths(self) -> list[str]:
        with self.connect() as db:
            return [str(row["local_path"]) for row in db.execute(
                "SELECT DISTINCT local_path FROM posts WHERE local_path IS NOT NULL"
            )]

    def clear_post_records(self) -> int:
        with self.connect() as db:
            count = int(db.execute("SELECT COUNT(*) FROM posts").fetchone()[0])
            db.execute("DELETE FROM posts")
            db.execute("DELETE FROM backup_runs")
            db.execute(
                "UPDATE creator_sync_state SET last_recent_check_at=NULL,backfill_cursor=NULL,"
                "backfill_completed=0,last_success_at=NULL,last_error=NULL"
            )
            return count

    def creator_row(self, creator_id: str) -> sqlite3.Row | None:
        with self.connect() as db:
            return db.execute("SELECT * FROM creators WHERE creator_id=?", (creator_id,)).fetchone()

    def set_creator_icon(self, creator_id: str, url: str, path: str, sha256: str) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE creators SET icon_url=?,icon_path=?,icon_sha256=? WHERE creator_id=?",
                (url, path, sha256, creator_id),
            )

    def record_post_access_issue(
        self, creator_id: str, summary: PostSummary, status: PostStatus, error: str,
    ) -> None:
        if status not in {PostStatus.RESTRICTED, PostStatus.UNAVAILABLE}:
            raise ValueError("只允許記錄 restricted 或 unavailable")
        with self.connect() as db:
            db.execute(
                "INSERT INTO posts(post_id,creator_id,title,updated_at,status,last_error,last_checked_at) "
                "VALUES(?,?,?,?,?,?,?) ON CONFLICT(post_id) DO UPDATE SET "
                "title=excluded.title,updated_at=excluded.updated_at,status=excluded.status,"
                "last_error=excluded.last_error,last_checked_at=excluded.last_checked_at",
                (summary.post_id, creator_id, summary.title or f"Post {summary.post_id}",
                 summary.updated_at, status.value, error, now_iso()),
            )

    def version_rows(self, post_id: str) -> list[sqlite3.Row]:
        with self.connect() as db:
            return list(db.execute(
                "SELECT * FROM post_versions WHERE post_id=? ORDER BY version_number", (post_id,)
            ))

    def latest_version(self, post_id: str, *, completed_only: bool = False) -> sqlite3.Row | None:
        query = "SELECT * FROM post_versions WHERE post_id=?"
        params: list[object] = [post_id]
        if completed_only:
            query += " AND status='completed'"
        query += " ORDER BY version_number DESC LIMIT 1"
        with self.connect() as db:
            return db.execute(query, params).fetchone()

    def begin_version(self, post: Post, version_number: int, local_path: str) -> int:
        with self.connect() as db:
            db.execute(
                "INSERT INTO post_versions(post_id,version_number,remote_updated_at,content_fingerprint,status,local_path) "
                "VALUES(?,?,?,?,?,?) ON CONFLICT(post_id,content_fingerprint) DO UPDATE SET "
                "status='downloading',last_error=NULL,local_path=excluded.local_path",
                (post.post_id, version_number,
                 post.updated_at.isoformat() if post.updated_at else None,
                 post.content_fingerprint or "", "downloading", local_path),
            )
            row = db.execute(
                "SELECT version_id FROM post_versions WHERE post_id=? AND content_fingerprint=?",
                (post.post_id, post.content_fingerprint or ""),
            ).fetchone()
            return int(row["version_id"])

    def version_by_fingerprint(self, post_id: str, fingerprint: str) -> sqlite3.Row | None:
        with self.connect() as db:
            return db.execute(
                "SELECT * FROM post_versions WHERE post_id=? AND content_fingerprint=?",
                (post_id, fingerprint),
            ).fetchone()

    def finish_version(
        self, version_id: int, *, status: PostStatus, markdown_path: str,
        json_path: str, error: str | None = None, make_latest: bool = False,
    ) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE post_versions SET captured_at=?,status=?,markdown_path=?,json_path=?,last_error=? WHERE version_id=?",
                (now_iso(), status.value, markdown_path, json_path, error, version_id),
            )
            if make_latest:
                row = db.execute("SELECT post_id FROM post_versions WHERE version_id=?", (version_id,)).fetchone()
                if row:
                    db.execute("UPDATE posts SET latest_version_id=? WHERE post_id=?", (version_id, row["post_id"]))

    def register_legacy_version(
        self, post_id: str, fingerprint: str, local_path: str,
        markdown_path: str, json_path: str, remote_updated_at: str | None,
    ) -> None:
        with self.connect() as db:
            cursor = db.execute(
                "INSERT OR IGNORE INTO post_versions(post_id,version_number,remote_updated_at,captured_at,"
                "content_fingerprint,status,local_path,markdown_path,json_path) VALUES(?,1,?,?,?,?,?,?,?)",
                (post_id, remote_updated_at, now_iso(), fingerprint, PostStatus.COMPLETED.value,
                 local_path, markdown_path, json_path),
            )
            row = db.execute(
                "SELECT version_id FROM post_versions WHERE post_id=? AND version_number=1", (post_id,)
            ).fetchone()
            if row:
                db.execute("UPDATE posts SET latest_version_id=? WHERE post_id=?", (row["version_id"], post_id))

    def completed_posts_without_versions(self) -> list[sqlite3.Row]:
        with self.connect() as db:
            return list(db.execute(
                "SELECT p.* FROM posts p WHERE p.status='completed' AND NOT EXISTS "
                "(SELECT 1 FROM post_versions v WHERE v.post_id=p.post_id)"
            ))

    def latest_fancard_version(self, creator_id: str, target_month: str) -> sqlite3.Row | None:
        with self.connect() as db:
            return db.execute(
                "SELECT * FROM fancard_versions WHERE creator_id=? AND target_month=? "
                "ORDER BY version_number DESC LIMIT 1",
                (creator_id, target_month),
            ).fetchone()

    def profile_versions(self, creator_id: str) -> list[sqlite3.Row]:
        with self.connect() as db:
            return list(db.execute(
                "SELECT * FROM creator_profile_versions WHERE creator_id=? "
                "ORDER BY version_number", (creator_id,)
            ))

    def latest_profile_version(self, creator_id: str) -> sqlite3.Row | None:
        with self.connect() as db:
            return db.execute(
                "SELECT * FROM creator_profile_versions WHERE creator_id=? "
                "AND status='completed' ORDER BY version_number DESC LIMIT 1",
                (creator_id,),
            ).fetchone()

    def register_profile_version(
        self, creator_id: str, name: str, version_number: int, fingerprint: str,
        local_path: str, json_path: str, cover_path: str | None, cover_sha256: str | None,
    ) -> int:
        with self.connect() as db:
            db.execute(
                "INSERT INTO creators(creator_id,name,url,last_checked_at) VALUES(?,?,?,?) "
                "ON CONFLICT(creator_id) DO UPDATE SET name=excluded.name,url=excluded.url,"
                "last_checked_at=excluded.last_checked_at",
                (creator_id, name, f"https://www.fanbox.cc/@{creator_id}", now_iso()),
            )
            db.execute(
                "INSERT INTO creator_profile_versions(creator_id,version_number,captured_at,"
                "content_fingerprint,status,local_path,json_path,cover_path,cover_sha256) "
                "VALUES(?,?,?,?, 'completed',?,?,?,?) "
                "ON CONFLICT(creator_id,content_fingerprint) DO UPDATE SET "
                "captured_at=excluded.captured_at,status='completed',local_path=excluded.local_path,"
                "json_path=excluded.json_path,cover_path=excluded.cover_path,"
                "cover_sha256=excluded.cover_sha256,last_error=NULL",
                (creator_id, version_number, now_iso(), fingerprint, local_path, json_path,
                 cover_path, cover_sha256),
            )
            row = db.execute(
                "SELECT profile_version_id FROM creator_profile_versions "
                "WHERE creator_id=? AND content_fingerprint=?", (creator_id, fingerprint),
            ).fetchone()
            version_id = int(row["profile_version_id"])
            db.execute(
                "UPDATE creators SET latest_profile_version_id=? WHERE creator_id=?",
                (version_id, creator_id),
            )
            return version_id

    def register_fancard_version(
        self, creator_id: str, target_month: str, version_number: int,
        fingerprint: str, local_path: str, image_path: str, image_sha256: str,
    ) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO fancard_versions(creator_id,target_month,version_number,captured_at,"
                "content_fingerprint,status,local_path,image_path,image_sha256) "
                "VALUES(?,?,?,?,?,'completed',?,?,?)",
                (creator_id, target_month, version_number, now_iso(), fingerprint,
                 local_path, image_path, image_sha256),
            )

    def incomplete_versions(self) -> list[sqlite3.Row]:
        with self.connect() as db:
            return list(db.execute(
                "SELECT * FROM post_versions WHERE status!='completed' ORDER BY post_id,version_number"
            ))

    def record_supporting_creators(self, creators: list[tuple[str, str]]) -> None:
        timestamp = now_iso()
        with self.connect() as db:
            db.execute("UPDATE creator_sync_state SET is_supporting=0")
            for creator_id, name in creators:
                db.execute(
                    "INSERT INTO creators(creator_id,name,url,last_checked_at) VALUES(?,?,?,?) "
                    "ON CONFLICT(creator_id) DO UPDATE SET name=excluded.name,url=excluded.url,last_checked_at=excluded.last_checked_at",
                    (creator_id, name, f"https://www.fanbox.cc/@{creator_id}", timestamp),
                )
                db.execute(
                    "INSERT INTO creator_sync_state(creator_id,is_supporting,last_seen_supporting_at) VALUES(?,1,?) "
                    "ON CONFLICT(creator_id) DO UPDATE SET is_supporting=1,last_seen_supporting_at=excluded.last_seen_supporting_at",
                    (creator_id, timestamp),
                )

    def creator_state(self, creator_id: str) -> sqlite3.Row | None:
        with self.connect() as db:
            return db.execute("SELECT * FROM creator_sync_state WHERE creator_id=?", (creator_id,)).fetchone()

    def creator_listing(self, *, supporting_only: bool = True) -> list[dict[str, object]]:
        where = "WHERE COALESCE(s.is_supporting,0)=1" if supporting_only else ""
        with self.connect() as db:
            rows = db.execute(f"""
                SELECT c.creator_id,c.name,c.url,c.last_checked_at,c.icon_url,c.icon_path,c.icon_sha256,
                       COALESCE(s.is_supporting,0) AS is_supporting,
                       s.last_recent_check_at,s.backfill_completed,s.last_success_at,s.last_error,
                       COUNT(DISTINCT pv.profile_version_id) AS profile_version_count,
                       MAX(pv.captured_at) AS latest_profile_captured_at,
                       COUNT(DISTINCT p.post_id) AS post_count,
                       COUNT(DISTINCT CASE WHEN p.status='completed' THEN p.post_id END) AS completed_count
                FROM creators c
                LEFT JOIN creator_sync_state s ON s.creator_id=c.creator_id
                LEFT JOIN posts p ON p.creator_id=c.creator_id
                LEFT JOIN creator_profile_versions pv ON pv.creator_id=c.creator_id AND pv.status='completed'
                {where}
                GROUP BY c.creator_id
                ORDER BY c.name COLLATE NOCASE,c.creator_id COLLATE NOCASE
            """).fetchall()
        result: list[dict[str, object]] = []
        for row in rows:
            post_count = int(row["post_count"] or 0)
            if row["last_error"]:
                status = "部分失敗"
            elif post_count == 0:
                status = "尚未備份"
            elif row["backfill_completed"] and row["last_success_at"]:
                status = "同步完成"
            elif row["last_success_at"]:
                status = "歷史回補中"
            else:
                status = "已有本機資料"
            result.append({
                "creator_id": str(row["creator_id"]),
                "name": str(row["name"]),
                "url": str(row["url"] or f"https://www.fanbox.cc/@{row['creator_id']}"),
                "icon_url": row["icon_url"],
                "icon_path": row["icon_path"],
                "icon_sha256": row["icon_sha256"],
                "post_count": post_count,
                "completed_count": int(row["completed_count"] or 0),
                "last_sync": row["last_success_at"] or row["last_recent_check_at"],
                "status": status,
                "is_supporting": bool(row["is_supporting"]),
                "profile_version_count": int(row["profile_version_count"] or 0),
                "latest_profile_captured_at": row["latest_profile_captured_at"],
            })
        return result

    def ordered_creator_ids(self, creator_ids: list[str], rotate: bool = True) -> list[str]:
        if not rotate or len(creator_ids) < 2:
            return creator_ids
        with self.connect() as db:
            states = {
                str(row["creator_id"]): row["last_success_at"]
                for row in db.execute("SELECT creator_id,last_success_at FROM creator_sync_state")
            }
        positions = {creator_id: index for index, creator_id in enumerate(creator_ids)}
        return sorted(creator_ids, key=lambda value: (states.get(value) is not None, states.get(value) or "", positions[value]))

    def update_creator_sync(
        self, creator_id: str, *, recent_checked: bool = False,
        backfill_cursor: str | None = None, backfill_completed: bool | None = None,
        success: bool = False, error: str | None = None,
    ) -> None:
        timestamp = now_iso()
        with self.connect() as db:
            db.execute(
                "INSERT INTO creator_sync_state(creator_id) VALUES(?) ON CONFLICT(creator_id) DO NOTHING",
                (creator_id,),
            )
            assignments = ["last_error=?"]
            values: list[object] = [error]
            if recent_checked:
                assignments.append("last_recent_check_at=?")
                values.append(timestamp)
            if backfill_cursor is not None:
                assignments.append("backfill_cursor=?")
                values.append(backfill_cursor)
            if backfill_completed is not None:
                assignments.append("backfill_completed=?")
                values.append(int(backfill_completed))
                if backfill_completed:
                    assignments.append("backfill_cursor=NULL")
            if success:
                assignments.append("last_success_at=?")
                values.append(timestamp)
            values.append(creator_id)
            db.execute(f"UPDATE creator_sync_state SET {','.join(assignments)} WHERE creator_id=?", values)

    def set_post_status(self, post_id: str, status: PostStatus, error: str | None = None) -> None:
        with self.connect() as db:
            db.execute("UPDATE posts SET status=?,last_error=?,last_checked_at=? WHERE post_id=?",
                       (status.value, error, now_iso(), post_id))

    def set_asset(self, post_id: str, asset: Asset) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE assets SET local_path=?,size=?,sha256=?,etag=?,last_modified=?,status=?,error=? "
                "WHERE post_id=? AND asset_id=? AND source_url=?",
                (asset.local_path, asset.size, asset.sha256, asset.etag, asset.last_modified,
                 asset.status.value, asset.error, post_id, asset.asset_id, asset.url),
            )

    def create_web_job(
        self, job_id: str, request_json: str, created_at: str, updated_at: str,
        *, kind: str = "backup",
    ) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO web_jobs(job_id,kind,status,request_json,created_at,updated_at) "
                "VALUES(?,?,'queued',?,?,?)",
                (job_id, kind, request_json, created_at, updated_at),
            )

    def update_web_job(
        self, job_id: str, *, status: str, updated_at: str,
        started_at: str | None, finished_at: str | None,
        error: str | None, result_json: str | None,
    ) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE web_jobs SET status=?,updated_at=?,started_at=?,finished_at=?,"
                "error=?,result_json=? WHERE job_id=?",
                (status, updated_at, started_at, finished_at, error, result_json, job_id),
            )

    def record_web_job_event(
        self, job_id: str, kind: str, timestamp: str, data_json: str,
        *, coalesce_key: str | None = None,
    ) -> None:
        with self.connect() as db:
            previous = db.execute(
                "SELECT event_id,kind,coalesce_key FROM web_job_events "
                "WHERE job_id=? ORDER BY event_id DESC LIMIT 1", (job_id,),
            ).fetchone()
            if (
                coalesce_key is not None and previous is not None
                and previous["kind"] == kind and previous["coalesce_key"] == coalesce_key
            ):
                db.execute(
                    "UPDATE web_job_events SET timestamp=?,data_json=? WHERE event_id=?",
                    (timestamp, data_json, previous["event_id"]),
                )
            else:
                db.execute(
                    "INSERT INTO web_job_events(job_id,kind,timestamp,data_json,coalesce_key) "
                    "VALUES(?,?,?,?,?)",
                    (job_id, kind, timestamp, data_json, coalesce_key),
                )
                db.execute(
                    "DELETE FROM web_job_events WHERE job_id=? AND event_id NOT IN "
                    "(SELECT event_id FROM web_job_events WHERE job_id=? "
                    "ORDER BY event_id DESC LIMIT 1000)",
                    (job_id, job_id),
                )

    def recover_interrupted_web_jobs(self, timestamp: str) -> list[str]:
        with self.connect() as db:
            rows = list(db.execute(
                "SELECT job_id FROM web_jobs WHERE status IN ('queued','running','cancelling')"
            ))
            for row in rows:
                job_id = str(row["job_id"])
                message = "伺服器重新啟動，先前工作已中斷；不會自動重新執行。"
                db.execute(
                    "UPDATE web_jobs SET status='interrupted',updated_at=?,finished_at=?,error=? "
                    "WHERE job_id=?",
                    (timestamp, timestamp, message, job_id),
                )
                db.execute(
                    "INSERT INTO web_job_events(job_id,kind,timestamp,data_json) "
                    "VALUES(?,'job_interrupted',?,?)",
                    (job_id, timestamp, '{"reason":"server_restart"}'),
                )
            return [str(row["job_id"]) for row in rows]

    def web_job_rows(self, limit: int = 100) -> list[sqlite3.Row]:
        with self.connect() as db:
            return list(db.execute(
                "SELECT * FROM web_jobs ORDER BY created_at DESC,job_id DESC LIMIT ?", (limit,)
            ))

    def web_job_event_rows(self, job_id: str) -> list[sqlite3.Row]:
        with self.connect() as db:
            return list(db.execute(
                "SELECT * FROM web_job_events WHERE job_id=? ORDER BY event_id", (job_id,)
            ))

    def asset_row(self, post_id: str, asset_id: str, source_url: str) -> sqlite3.Row | None:
        with self.connect() as db:
            return db.execute(
                "SELECT * FROM assets WHERE post_id=? AND asset_id=? AND source_url=?",
                (post_id, asset_id, source_url),
            ).fetchone()

    def failed_assets(self) -> list[sqlite3.Row]:
        with self.connect() as db:
            return list(db.execute("SELECT * FROM assets WHERE status IN ('failed','missing','corrupt') ORDER BY post_id,id"))

    def retryable_versions(self) -> list[sqlite3.Row]:
        """Return the exact archived version metadata that should be retried."""
        with self.connect() as db:
            return list(db.execute("""
                SELECT v.* FROM post_versions v
                WHERE v.status IN ('pending','partial','failed')
                   OR v.version_id IN (
                       SELECT COALESCE(p.latest_version_id,
                           (SELECT MAX(v2.version_id) FROM post_versions v2 WHERE v2.post_id=p.post_id))
                       FROM posts p
                       WHERE EXISTS (
                           SELECT 1 FROM assets a
                           WHERE a.post_id=p.post_id AND a.status IN ('failed','missing','corrupt')
                       )
                         AND NOT EXISTS (
                            SELECT 1 FROM post_versions iv
                            WHERE iv.post_id=p.post_id AND iv.status IN ('pending','partial','failed')
                        )
                   )
                ORDER BY v.post_id,v.version_number
            """))

    def statistics(self) -> dict[str, int]:
        with self.connect() as db:
            result: dict[str, int] = {}
            for row in db.execute("SELECT status,COUNT(*) count FROM posts GROUP BY status"):
                result[f"posts_{row['status']}"] = int(row["count"])
            for row in db.execute("SELECT status,COUNT(*) count FROM assets GROUP BY status"):
                result[f"assets_{row['status']}"] = int(row["count"])
            for row in db.execute("SELECT status,COUNT(*) count FROM fancard_versions GROUP BY status"):
                result[f"fancards_{row['status']}"] = int(row["count"])
            return result

    def latest_run(self) -> sqlite3.Row | None:
        with self.connect() as db:
            return db.execute(
                "SELECT * FROM backup_runs ORDER BY run_id DESC LIMIT 1"
            ).fetchone()

    def latest_successful_run(self) -> sqlite3.Row | None:
        with self.connect() as db:
            return db.execute(
                "SELECT * FROM backup_runs WHERE finished_at IS NOT NULL AND failure_count=0 AND dry_run=0 "
                "AND (success_count>0 OR skipped_count>0) "
                "ORDER BY run_id DESC LIMIT 1"
            ).fetchone()

    def recent_failures(self, limit: int = 10) -> list[sqlite3.Row]:
        with self.connect() as db:
            return list(db.execute(
                "SELECT post_id,creator_id,title,status,last_error,last_checked_at FROM posts "
                "WHERE status IN ('failed','partial','restricted','unavailable') "
                "ORDER BY last_checked_at DESC LIMIT ?", (limit,)
            ))

    def incomplete_creator_rows(self) -> list[sqlite3.Row]:
        with self.connect() as db:
            return list(db.execute(
                "SELECT c.creator_id,c.name,s.backfill_cursor,s.last_recent_check_at,s.last_error "
                "FROM creator_sync_state s JOIN creators c ON c.creator_id=s.creator_id "
                "WHERE s.is_supporting=1 AND (s.backfill_completed=0 OR s.last_error IS NOT NULL) "
                "ORDER BY c.name COLLATE NOCASE"
            ))

    def begin_run(self, scope: str, *, dry_run: bool = False) -> int:
        with self.connect() as db:
            cursor = db.execute(
                "INSERT INTO backup_runs(started_at,scope,dry_run) VALUES(?,?,?)",
                (now_iso(), scope, int(dry_run)),
            )
            return int(cursor.lastrowid)

    def finish_run(self, run_id: int, success: int, failure: int, **counts: int) -> None:
        with self.connect() as db:
            allowed = {"discovered", "new", "updated", "skipped", "retried"}
            selected = {key: value for key, value in counts.items() if key in allowed}
            assignments = ["finished_at=?", "success_count=?", "failure_count=?"]
            values: list[object] = [now_iso(), success, failure]
            for key, value in selected.items():
                assignments.append(f"{key}_count=?")
                values.append(value)
            values.append(run_id)
            db.execute(f"UPDATE backup_runs SET {','.join(assignments)} WHERE run_id=?", values)
