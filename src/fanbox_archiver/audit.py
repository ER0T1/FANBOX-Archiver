from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import uuid
from collections import defaultdict
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .config import AppConfig, StorageConfig
from .indexer import IndexBuilder
from .storage import BackupStorage


Severity = Literal["error", "warning"]
Repairability = Literal["automatic", "manual", "unrecoverable"]


class AuditFinding(BaseModel):
    code: str
    severity: Severity
    subject_type: str
    subject_id: str
    creator_id: str | None = None
    version: int | None = None
    issue: str
    evidence: str
    repairability: Repairability
    suggested_action: str


class AuditRepairAction(BaseModel):
    action_id: str
    finding_code: str
    subject_type: str
    subject_id: str
    description: str
    prerequisites: list[str] = Field(default_factory=list)
    dry_run: bool = True


class AuditReport(BaseModel):
    generated_at: str
    read_only: bool = True
    schema_version: int | None = None
    finding_count: int
    automatic_count: int
    findings: list[AuditFinding]
    repair_plan: list[AuditRepairAction]


class RepairCopyResult(BaseModel):
    applied_actions: int
    remaining_findings: int
    database_backup: str


class ArchiveAuditor:
    """Cross-check archive history without creating or modifying archive data."""

    _VERSION_SPECS = (
        {
            "table": "post_versions", "kind": "post", "id": "post_id",
            "pointer_table": "posts",
            "pointer": "latest_version_id", "row_id": "version_id", "alias": "post.json",
        },
        {
            "table": "creator_profile_versions", "kind": "profile", "id": "creator_id",
            "pointer_table": "creators",
            "pointer": "latest_profile_version_id", "row_id": "profile_version_id",
            "alias": "profile.json",
        },
        {
            "table": "fancard_versions", "kind": "fancard", "id": "creator_id",
            "pointer_table": None,
            "pointer": None, "row_id": "fancard_version_id", "alias": "fancard.json",
        },
    )

    _TIMESTAMP_COLUMNS = {
        "creators": ("last_checked_at",),
        "posts": ("published_at", "updated_at", "last_checked_at"),
        "backup_runs": ("started_at", "finished_at"),
        "creator_sync_state": (
            "last_seen_supporting_at", "last_recent_check_at", "last_success_at",
        ),
        "schema_migrations": ("applied_at",),
        "web_jobs": ("created_at", "started_at", "finished_at", "updated_at"),
        "web_job_events": ("timestamp",),
    }

    def __init__(self, config: AppConfig):
        self.root = config.storage.output_dir.resolve()
        self.database = config.storage.database.resolve()
        self.findings: list[AuditFinding] = []
        self._known_version_dirs: set[Path] = set()

    def run(self) -> AuditReport:
        self.findings = []
        self._known_version_dirs = set()
        schema_version: int | None = None
        if not self.database.is_file():
            self._add(
                code="database_missing", severity="error", subject_type="database",
                subject_id="archive", issue="找不到封存資料庫。", evidence="database: missing",
                repairability="manual", suggested_action="確認設定指向既有封存，且不要建立空白資料庫覆蓋現況。",
            )
            return self._report(schema_version)

        uri = self.database.as_uri() + "?mode=ro"
        try:
            with closing(sqlite3.connect(uri, uri=True)) as db:
                db.row_factory = sqlite3.Row
                db.execute("PRAGMA query_only = ON")
                schema_version = self._schema_version(db)
                for spec in self._VERSION_SPECS:
                    if self._table_exists(db, str(spec["table"])):
                        self._audit_versions(db, spec)
                self._audit_timestamps(db)
        except sqlite3.Error as exc:
            self._add(
                code="database_unreadable", severity="error", subject_type="database",
                subject_id="archive", issue="封存資料庫無法以唯讀模式開啟。",
                evidence=f"sqlite: {type(exc).__name__}", repairability="manual",
                suggested_action="保留原始資料庫並先建立副本，再檢查 SQLite 完整性。",
            )
            return self._report(schema_version)

        self._audit_orphan_directories()
        return self._report(schema_version)

    def _report(self, schema_version: int | None) -> AuditReport:
        actions = [self._repair_action(item) for item in self.findings if item.repairability == "automatic"]
        return AuditReport(
            generated_at=datetime.now(UTC).isoformat(), schema_version=schema_version,
            finding_count=len(self.findings), automatic_count=len(actions),
            findings=self.findings, repair_plan=actions,
        )

    def _schema_version(self, db: sqlite3.Connection) -> int | None:
        if not self._table_exists(db, "schema_migrations"):
            return None
        row = db.execute("SELECT MAX(version) AS version FROM schema_migrations").fetchone()
        return int(row["version"]) if row and row["version"] is not None else None

    def _audit_versions(self, db: sqlite3.Connection, spec: dict[str, object]) -> None:
        table = str(spec["table"])
        kind = str(spec["kind"])
        rows = list(db.execute(f"SELECT * FROM {table} ORDER BY version_number"))
        groups: dict[tuple[str, ...], list[sqlite3.Row]] = defaultdict(list)
        for row in rows:
            key = (str(row["creator_id"]), str(row["target_month"])) if kind == "fancard" else (
                str(row[str(spec["id"])]),
            )
            groups[key].append(row)

        creator_by_post: dict[str, str] = {}
        if kind == "post" and self._table_exists(db, "posts"):
            creator_by_post = {
                str(row["post_id"]): str(row["creator_id"])
                for row in db.execute("SELECT post_id,creator_id FROM posts")
            }

        for key, versions in groups.items():
            subject_id = "/".join(key)
            creator_id = creator_by_post.get(key[0]) if kind == "post" else key[0]
            numbers = [int(row["version_number"]) for row in versions]
            expected = list(range(1, max(numbers) + 1)) if numbers else []
            if numbers != expected:
                self._add(
                    code="version_sequence", severity="error", subject_type=kind,
                    subject_id=subject_id, creator_id=creator_id,
                    issue="版本號不是從 1 開始的連續遞增序列。",
                    evidence=f"versions: {','.join(f'v{value:04d}' for value in numbers)}",
                    repairability="manual",
                    suggested_action="依資料庫、版本目錄與 manifest 證據建立 dry-run 重建對照；不可直接重新編號。",
                )

            previous_time: datetime | None = None
            previous_number: int | None = None
            completed = [row for row in versions if str(row["status"]) == "completed"]
            for row in versions:
                number = int(row["version_number"])
                path = Path(str(row["local_path"])).resolve()
                safe_path = self._safe_path(path)
                if safe_path != "[outside archive]":
                    self._known_version_dirs.add(path)
                expected_dir = f"v{number:04d}"
                if safe_path == "[outside archive]" or path.name != expected_dir:
                    self._add(
                        code="version_path", severity="error", subject_type=kind,
                        subject_id=subject_id, creator_id=creator_id, version=number,
                        issue="資料庫版本路徑與版本號不一致或超出封存根目錄。",
                        evidence=f"path: {safe_path}; expected directory: {expected_dir}",
                        repairability="manual",
                        suggested_action="只依可驗證的 manifest 與版本目錄建立路徑修復預覽。",
                    )
                if safe_path != "[outside archive]":
                    manifest = self._manifest(kind, subject_id, creator_id, number, path)
                    if manifest is not None:
                        self._compare_manifest(
                            kind, subject_id, creator_id, number, row, manifest, safe_path,
                        )

                captured = self._parse_timestamp(
                    row["captured_at"], table, "captured_at", subject_id, creator_id, kind, number,
                )
                if kind == "post" and row["remote_updated_at"] is not None:
                    self._parse_timestamp(
                        row["remote_updated_at"], table, "remote_updated_at",
                        subject_id, creator_id, kind, number,
                    )
                if captured is not None and previous_time is not None and captured < previous_time:
                    self._add(
                        code="capture_order", severity="error", subject_type=kind,
                        subject_id=subject_id, creator_id=creator_id, version=number,
                        issue="較新的版本具有較早的捕捉時間。",
                        evidence=(f"v{previous_number:04d} captured after v{number:04d}"),
                        repairability="unrecoverable",
                        suggested_action="比對原始 manifest 與版本內容；若缺乏可靠證據，保留 unknown，不以檔案 mtime 猜測。",
                    )
                if captured is not None:
                    previous_time, previous_number = captured, number

            if spec["pointer_table"] and completed:
                self._audit_pointer_and_alias(db, spec, key, completed, creator_id)
            elif kind == "fancard" and completed:
                self._audit_alias(kind, subject_id, creator_id, completed[-1], str(spec["alias"]))

    def _audit_pointer_and_alias(
        self, db: sqlite3.Connection, spec: dict[str, object], key: tuple[str, ...],
        completed: list[sqlite3.Row], creator_id: str | None,
    ) -> None:
        kind = str(spec["kind"])
        subject_id = "/".join(key)
        pointer_table = str(spec["pointer_table"])
        id_column = str(spec["id"])
        pointer_column = str(spec["pointer"])
        row_id = str(spec["row_id"])
        owner = db.execute(
            f"SELECT {pointer_column} AS pointer FROM {pointer_table} WHERE {id_column}=?",
            (key[0],),
        ).fetchone()
        pointer = int(owner["pointer"]) if owner and owner["pointer"] is not None else None
        latest = max(completed, key=lambda row: int(row["version_number"]))
        expected = int(latest[row_id])
        if pointer != expected:
            current = next((row for row in completed if int(row[row_id]) == pointer), None)
            current_label = f"v{int(current['version_number']):04d}" if current else "missing/invalid"
            repairable = self._manifest_is_consistent(latest)
            self._add(
                code="latest_pointer", severity="error", subject_type=kind,
                subject_id=subject_id, creator_id=creator_id,
                issue="latest pointer 與最大完成版本不一致。",
                evidence=f"pointer: {current_label}; max completed: v{int(latest['version_number']):04d}",
                repairability="automatic" if repairable else "manual",
                suggested_action=(
                    "在資料庫副本中預覽更新 pointer，並於套用前驗證 canonical manifest 與版本目錄。"
                    if repairable else
                    "canonical manifest 證據不完整；先人工確認，不可自動更新 pointer。"
                ),
            )
        self._audit_alias(kind, subject_id, creator_id, latest, str(spec["alias"]))

    def _audit_alias(
        self, kind: str, subject_id: str, creator_id: str | None,
        canonical: sqlite3.Row, alias_name: str,
    ) -> None:
        version_path = Path(str(canonical["local_path"])).resolve()
        if self._safe_path(version_path) == "[outside archive]":
            return
        root = version_path.parent.parent
        source = version_path / alias_name
        alias = root / alias_name
        number = int(canonical["version_number"])
        if not source.is_file():
            self._add(
                code="canonical_alias_source_missing", severity="error", subject_type=kind,
                subject_id=subject_id, creator_id=creator_id, version=number,
                issue="canonical 完成版本缺少 latest alias 的來源檔案。",
                evidence=f"canonical: v{number:04d}/{alias_name}", repairability="manual",
                suggested_action="先依 manifest 判定檔案是否可恢復，不可建立空白 alias。",
            )
            return
        try:
            alias_matches = alias.is_file() and self._sha256(alias) == self._sha256(source)
        except OSError:
            alias_matches = False
        if not alias_matches:
            repairable = self._manifest_is_consistent(canonical)
            self._add(
                code="latest_alias", severity="error", subject_type=kind,
                subject_id=subject_id, creator_id=creator_id, version=number,
                issue="latest alias 與 canonical 完成版本不一致。",
                evidence=f"alias: {self._safe_path(alias)}; canonical: v{number:04d}/{alias_name}",
                repairability="automatic" if repairable else "manual",
                suggested_action=(
                    "從已驗證的 canonical 版本以 staging 重建 alias，不修改歷史版本。"
                    if repairable else
                    "canonical manifest 證據不完整；先人工確認，不可自動重建 alias。"
                ),
            )

    def _manifest(
        self, kind: str, subject_id: str, creator_id: str | None,
        number: int, version_path: Path,
    ) -> dict[str, object] | None:
        path = version_path / "manifest.json"
        if not path.is_file():
            self._add(
                code="manifest_missing", severity="error", subject_type=kind,
                subject_id=subject_id, creator_id=creator_id, version=number,
                issue="版本缺少 manifest.json。",
                evidence=f"path: {self._safe_path(path)}", repairability="manual",
                suggested_action="比對版本內容與資料庫；無可靠證據時不可合成捕捉時間或 fingerprint。",
            )
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError("manifest root is not an object")
            return value
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self._add(
                code="manifest_invalid", severity="error", subject_type=kind,
                subject_id=subject_id, creator_id=creator_id, version=number,
                issue="manifest.json 無法解析。",
                evidence=f"path: {self._safe_path(path)}; error: {type(exc).__name__}",
                repairability="manual", suggested_action="保留原檔，在副本中比對其他可驗證證據。",
            )
            return None

    def _compare_manifest(
        self, kind: str, subject_id: str, creator_id: str | None, number: int,
        row: sqlite3.Row, manifest: dict[str, object], safe_path: str,
    ) -> None:
        comparisons = (
            ("version", number, "manifest_version"),
            ("content_fingerprint", str(row["content_fingerprint"]), "manifest_fingerprint"),
            ("captured_at", str(row["captured_at"]), "manifest_captured_at"),
        )
        for field, expected, code in comparisons:
            if manifest.get(field) != expected:
                self._add(
                    code=code, severity="error", subject_type=kind,
                    subject_id=subject_id, creator_id=creator_id, version=number,
                    issue=f"manifest.{field} 與資料庫不一致。",
                    evidence=f"version path: {safe_path}; field: {field}",
                    repairability="manual",
                    suggested_action="依版本目錄、manifest 與資料庫三方證據產生修復預覽，不直接覆寫。",
                )
        self._parse_timestamp(
            manifest.get("captured_at"), "manifest", "captured_at",
            subject_id, creator_id, kind, number,
        )
        if kind == "post" and manifest.get("remote_updated_at") is not None:
            self._parse_timestamp(
                manifest.get("remote_updated_at"), "manifest", "remote_updated_at",
                subject_id, creator_id, kind, number,
            )
        identifiers = {"profile": ("creator_id", creator_id), "fancard": ("creator_id", creator_id)}
        if kind in identifiers:
            field, expected = identifiers[kind]
            if manifest.get(field) != expected:
                self._add(
                    code="manifest_identity", severity="error", subject_type=kind,
                    subject_id=subject_id, creator_id=creator_id, version=number,
                    issue=f"manifest.{field} 與版本身分不一致。",
                    evidence=f"version path: {safe_path}; field: {field}", repairability="manual",
                    suggested_action="保留原始檔案並在副本中比對身分證據。",
                )
        if kind == "fancard" and manifest.get("target_month") != subject_id.split("/", 1)[-1]:
            self._add(
                code="manifest_identity", severity="error", subject_type=kind,
                subject_id=subject_id, creator_id=creator_id, version=number,
                issue="manifest.target_month 與版本身分不一致。",
                evidence=f"version path: {safe_path}; field: target_month", repairability="manual",
                suggested_action="保留原始檔案並在副本中比對月份證據。",
            )
        files = manifest.get("files")
        if not isinstance(files, dict):
            self._add(
                code="manifest_files", severity="error", subject_type=kind,
                subject_id=subject_id, creator_id=creator_id, version=number,
                issue="manifest.files 不是物件。", evidence=f"version path: {safe_path}",
                repairability="manual", suggested_action="不要依無效 manifest 自動修復。",
            )
            return
        root = Path(str(row["local_path"])).resolve()
        for relative, expected_hash in files.items():
            candidate = (root / str(relative)).resolve()
            safe_entry = self._safe_entry(relative)
            try:
                candidate.relative_to(root)
            except ValueError:
                self._add(
                    code="manifest_file_path", severity="error", subject_type=kind,
                    subject_id=subject_id, creator_id=creator_id, version=number,
                    issue="manifest 檔案路徑超出版本目錄。", evidence=f"entry: {safe_entry}",
                    repairability="manual", suggested_action="拒絕使用此 manifest 進行自動修復。",
                )
                continue
            if not candidate.is_file():
                self._add(
                    code="manifest_file_missing", severity="error", subject_type=kind,
                    subject_id=subject_id, creator_id=creator_id, version=number,
                    issue="manifest 列出的檔案不存在。", evidence=f"entry: {safe_entry}",
                    repairability="manual", suggested_action="比對其他版本或備份來源，不建立虛構檔案。",
                )
            else:
                try:
                    matches = self._sha256(candidate) == str(expected_hash)
                except OSError:
                    matches = False
                if not matches:
                    self._add(
                        code="manifest_file_hash", severity="error", subject_type=kind,
                        subject_id=subject_id, creator_id=creator_id, version=number,
                        issue="manifest 檔案 SHA-256 不一致或無法讀取。",
                        evidence=f"entry: {safe_entry}", repairability="manual",
                        suggested_action="保留證據並以其他可靠副本復原。",
                    )

    def _audit_timestamps(self, db: sqlite3.Connection) -> None:
        for table, requested in self._TIMESTAMP_COLUMNS.items():
            if not self._table_exists(db, table):
                continue
            columns = {str(row["name"]) for row in db.execute(f"PRAGMA table_info({table})")}
            fields = [field for field in requested if field in columns]
            if not fields:
                continue
            for index, row in enumerate(db.execute(f"SELECT {','.join(fields)} FROM {table}"), start=1):
                for field in fields:
                    self._parse_timestamp(
                        row[field], table, field, f"row-{index}", None, "database", None,
                    )

    def _parse_timestamp(
        self, value: object, table: str, field: str, subject_id: str,
        creator_id: str | None, subject_type: str, version: int | None,
    ) -> datetime | None:
        if value in (None, ""):
            return None
        raw = str(value)
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            self._add(
                code="timestamp_invalid", severity="warning", subject_type=subject_type,
                subject_id=subject_id, creator_id=creator_id, version=version,
                issue="時間欄位不是可解析的 ISO 8601。",
                evidence=f"source: {table}.{field}", repairability="manual",
                suggested_action="確認來源語意後在副本中正規化；不可猜測日期。",
            )
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            self._add(
                code="timestamp_naive", severity="warning", subject_type=subject_type,
                subject_id=subject_id, creator_id=creator_id, version=version,
                issue="時間欄位缺少 UTC offset。",
                evidence=f"source: {table}.{field}", repairability="manual",
                suggested_action="依已知來源規則建立轉換預覽；來源不明時標記 unknown。",
            )
            return None
        normalized = parsed.astimezone(UTC)
        if normalized > datetime.now(UTC) + timedelta(minutes=5):
            self._add(
                code="timestamp_future", severity="warning", subject_type=subject_type,
                subject_id=subject_id, creator_id=creator_id, version=version,
                issue="時間欄位位於不合理的未來。",
                evidence=f"source: {table}.{field}", repairability="manual",
                suggested_action="檢查系統時鐘與來源資料，不自動改寫。",
            )
        return normalized

    def _audit_orphan_directories(self) -> None:
        if not self.root.is_dir():
            return
        patterns = (
            "*/*/versions/v[0-9][0-9][0-9][0-9]",
            "*/profile/versions/v[0-9][0-9][0-9][0-9]",
            "*/fancards/*/versions/v[0-9][0-9][0-9][0-9]",
        )
        scanned: set[Path] = set()
        for pattern in patterns:
            for path in sorted(item.resolve() for item in self.root.glob(pattern) if item.is_dir()):
                if path in scanned:
                    continue
                scanned.add(path)
                if path in self._known_version_dirs:
                    continue
                self._add(
                    code="orphan_version_directory", severity="warning", subject_type="filesystem",
                    subject_id=self._safe_path(path), issue="版本目錄沒有對應的資料庫紀錄。",
                    evidence=f"path: {self._safe_path(path)}", repairability="manual",
                    suggested_action="解析 manifest 並與資料庫副本比對，只有證據完整時才預覽重建資料列。",
                )

    def _repair_action(self, finding: AuditFinding) -> AuditRepairAction:
        if finding.code == "latest_pointer":
            description = "將 latest pointer 預覽為最大且已驗證的完成版本。"
            prerequisites = ["canonical manifest 與資料庫 fingerprint/captured_at 一致", "版本目錄存在"]
        else:
            description = "從 canonical 完成版本以 staging 預覽重建 latest alias。"
            prerequisites = ["canonical 版本檔案存在且通過 SHA-256 驗證"]
        return AuditRepairAction(
            action_id=f"{finding.code}:{finding.subject_type}:{finding.subject_id}",
            finding_code=finding.code, subject_type=finding.subject_type,
            subject_id=finding.subject_id, description=description, prerequisites=prerequisites,
        )

    def _manifest_is_consistent(self, row: sqlite3.Row) -> bool:
        root = Path(str(row["local_path"])).resolve()
        if self._safe_path(root) == "[outside archive]":
            return False
        try:
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return False
        if not isinstance(manifest, dict):
            return False
        metadata_matches = (
            manifest.get("version") == int(row["version_number"])
            and manifest.get("content_fingerprint") == str(row["content_fingerprint"])
            and manifest.get("captured_at") == str(row["captured_at"])
        )
        files = manifest.get("files")
        if not metadata_matches or not isinstance(files, dict):
            return False
        for relative, expected_hash in files.items():
            candidate = (root / str(relative)).resolve()
            try:
                candidate.relative_to(root)
                if not candidate.is_file() or self._sha256(candidate) != str(expected_hash):
                    return False
            except (OSError, ValueError):
                return False
        return True

    def _safe_path(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.root).as_posix()
        except ValueError:
            return "[outside archive]"

    @staticmethod
    def _safe_entry(value: object) -> str:
        path = Path(str(value))
        if path.is_absolute() or ".." in path.parts:
            return "[unsafe path]"
        return path.as_posix()

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _table_exists(db: sqlite3.Connection, table: str) -> bool:
        return db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,),
        ).fetchone() is not None

    def _add(self, **values: object) -> None:
        self.findings.append(AuditFinding.model_validate(values))


class ArchiveRepairer:
    """Apply deterministic audit repairs to a new archive copy only."""

    _PATH_COLUMNS = {
        "creators": ("icon_path",),
        "posts": ("local_path",),
        "assets": ("local_path",),
        "post_versions": ("local_path", "markdown_path", "json_path"),
        "creator_profile_versions": ("local_path", "json_path", "cover_path"),
        "fancard_versions": ("local_path", "image_path"),
    }

    def __init__(self, config: AppConfig):
        self.config = config
        self.root = config.storage.output_dir.resolve()
        self.database = config.storage.database.resolve()

    def repair_copy(self, destination: Path) -> RepairCopyResult:
        destination = destination.resolve()
        try:
            database_relative = self.database.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("資料庫必須位於封存根目錄內，才能建立可修復副本。") from exc
        if destination.exists():
            raise ValueError("修復副本目的地已存在。")
        try:
            destination.relative_to(self.root)
        except ValueError:
            pass
        else:
            raise ValueError("修復副本目的地不可位於原始封存內。")
        if not self.root.is_dir() or not self.database.is_file():
            raise ValueError("原始封存或資料庫不存在。")
        if not ArchiveAuditor(self.config).run().repair_plan:
            raise ValueError("稽核沒有可確定性套用的修復，不建立副本。")

        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.repair.tmp")
        try:
            shutil.copytree(self.root, staging, copy_function=shutil.copy2)
            copied_database = staging / database_relative
            self._snapshot_database(copied_database)
            self._remap_paths(copied_database, self.root, staging)
            copied_config = self.config.model_copy(deep=True)
            copied_config.storage = StorageConfig(output_dir=staging, database=copied_database)

            report = ArchiveAuditor(copied_config).run()
            actions = report.repair_plan
            database_backup = copied_database.with_name(f"{copied_database.name}.pre-repair.bak")
            shutil.copy2(copied_database, database_backup)
            self._apply(copied_config, actions)
            indexer = IndexBuilder(copied_config)
            indexer.build(force=True)
            index_issues = indexer.check()
            if index_issues:
                raise RuntimeError(f"修復副本的靜態索引驗證失敗：{len(index_issues)} 項。")
            remaining = ArchiveAuditor(copied_config).run()
            if any(item.repairability == "automatic" for item in remaining.findings):
                raise RuntimeError("確定性修復後仍存在可自動修復問題。")

            self._remap_paths(copied_database, staging, destination)
            self._remap_paths(database_backup, staging, destination)
            BackupStorage._replace_with_retry(staging, destination)
            return RepairCopyResult(
                applied_actions=len(actions),
                remaining_findings=remaining.finding_count,
                database_backup=database_backup.relative_to(staging).as_posix(),
            )
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    def _snapshot_database(self, copied_database: Path) -> None:
        copied_database.unlink(missing_ok=True)
        copied_database.with_name(f"{copied_database.name}-wal").unlink(missing_ok=True)
        copied_database.with_name(f"{copied_database.name}-shm").unlink(missing_ok=True)
        with closing(sqlite3.connect(self.database.as_uri() + "?mode=ro", uri=True)) as source:
            with closing(sqlite3.connect(copied_database)) as target:
                source.backup(target)

    def _remap_paths(self, database: Path, old_root: Path, new_root: Path) -> None:
        with closing(sqlite3.connect(database)) as db:
            with db:
                for table, columns in self._PATH_COLUMNS.items():
                    if not ArchiveAuditor._table_exists(db, table):
                        continue
                    available = {str(row[1]) for row in db.execute(f"PRAGMA table_info({table})")}
                    for column in columns:
                        if column not in available:
                            continue
                        for rowid, value in db.execute(
                            f"SELECT rowid,{column} FROM {table} WHERE {column} IS NOT NULL"
                        ):
                            path = Path(str(value))
                            if not path.is_absolute():
                                continue
                            try:
                                relative = path.resolve().relative_to(old_root)
                            except ValueError:
                                continue
                            db.execute(
                                f"UPDATE {table} SET {column}=? WHERE rowid=?",
                                (str(new_root / relative), rowid),
                            )

    def _apply(self, config: AppConfig, actions: list[AuditRepairAction]) -> None:
        with closing(sqlite3.connect(config.storage.database)) as db, db:
            db.row_factory = sqlite3.Row
            for action in actions:
                row = self._canonical_row(db, action)
                if row is None or not ArchiveAuditor(config)._manifest_is_consistent(row):
                    raise RuntimeError(f"修復前 canonical 證據已改變：{action.action_id}")
                if action.finding_code == "latest_pointer":
                    if action.subject_type == "post":
                        db.execute(
                            "UPDATE posts SET latest_version_id=? WHERE post_id=?",
                            (row["version_id"], action.subject_id),
                        )
                    elif action.subject_type == "profile":
                        db.execute(
                            "UPDATE creators SET latest_profile_version_id=? WHERE creator_id=?",
                            (row["profile_version_id"], action.subject_id),
                        )
                elif action.finding_code == "latest_alias":
                    alias_name = {
                        "post": "post.json", "profile": "profile.json", "fancard": "fancard.json",
                    }[action.subject_type]
                    source = Path(str(row["local_path"])) / alias_name
                    target = Path(str(row["local_path"])).parent.parent / alias_name
                    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
                    shutil.copy2(source, temporary)
                    os.replace(temporary, target)

    @staticmethod
    def _canonical_row(
        db: sqlite3.Connection, action: AuditRepairAction,
    ) -> sqlite3.Row | None:
        if action.subject_type == "post":
            return db.execute(
                "SELECT * FROM post_versions WHERE post_id=? AND status='completed' "
                "ORDER BY version_number DESC LIMIT 1", (action.subject_id,),
            ).fetchone()
        if action.subject_type == "profile":
            return db.execute(
                "SELECT * FROM creator_profile_versions WHERE creator_id=? AND status='completed' "
                "ORDER BY version_number DESC LIMIT 1", (action.subject_id,),
            ).fetchone()
        if action.subject_type == "fancard":
            creator_id, target_month = action.subject_id.rsplit("/", 1)
            return db.execute(
                "SELECT * FROM fancard_versions WHERE creator_id=? AND target_month=? "
                "AND status='completed' ORDER BY version_number DESC LIMIT 1",
                (creator_id, target_month),
            ).fetchone()
        return None
