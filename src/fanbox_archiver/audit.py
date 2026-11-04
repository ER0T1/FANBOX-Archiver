from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import uuid
from collections import defaultdict
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .config import AppConfig, StorageConfig
from .database import Database, SCHEMA_VERSION
from .indexer import IndexBuilder
from .storage import BackupStorage
from .timestamps import fanbox_month, parse_instant


Severity = Literal["error", "warning", "info"]
Repairability = Literal["automatic", "manual", "unrecoverable", "not_needed"]
# Before v1.3.25 the manifest and the database row read the clock separately; the
# database row is finished after the manifest is written, so it is always a little later.
CAPTURE_DRIFT_TOLERANCE = timedelta(seconds=60)


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
    blocking_count: int = 0
    automatic_count: int
    findings: list[AuditFinding]
    repair_plan: list[AuditRepairAction]


class RepairCopyResult(BaseModel):
    applied_actions: int
    remaining_findings: int
    database_backup: str
    report: str = "repair-report.json"
    unrecoverable_findings: int = 0
    verify_issue_count: int = 0


@dataclass(slots=True)
class RebuildEntry:
    number: int
    path: Path
    manifest: dict[str, object]
    row_id: int | None


@dataclass(slots=True)
class RebuildPlan:
    kind: str
    table: str
    row_id_column: str
    owner_id: str  # post_id for posts, creator_id for profiles and Fan Cards
    target_month: str | None
    entries: list[RebuildEntry]


@dataclass(slots=True)
class FancardMonthEntry:
    row_id: int
    source_month: str
    number: int
    path: Path
    captured: datetime


@dataclass(slots=True)
class FancardMonthPlan:
    """Move Fan Card versions captured in a later JST month into that month, renumbered by capture."""

    creator_id: str
    target_month: str
    fancards_dir: Path
    entries: list[FancardMonthEntry]  # final order: entries[i] becomes v{i+1}
    source_months: list[str]


def capture_drift(manifest_value: object, database_value: object) -> Literal["exact", "drift"] | None:
    """Classify manifest vs database captured_at: identical, tolerated legacy drift, or mismatch."""
    if manifest_value == database_value:
        return "exact"
    manifest_time, database_time = parse_instant(manifest_value), parse_instant(database_value)
    if manifest_time is None or database_time is None:
        return None
    delta = database_time - manifest_time
    return "drift" if timedelta(0) < delta <= CAPTURE_DRIFT_TOLERANCE else None


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
        self.rebuild_plans: dict[str, RebuildPlan | FancardMonthPlan] = {}

    def run(self) -> AuditReport:
        self.findings = []
        self._known_version_dirs = set()
        self.rebuild_plans = {}
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
                if self._table_exists(db, "fancard_versions"):
                    self._audit_fancard_months(db)
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
            finding_count=len(self.findings),
            blocking_count=sum(item.severity != "info" for item in self.findings),
            automatic_count=len(actions),
            findings=self.findings, repair_plan=actions,
        )

    def _read_schema_version(self) -> int | None:
        with closing(sqlite3.connect(self.database.as_uri() + "?mode=ro", uri=True)) as db:
            db.row_factory = sqlite3.Row
            return self._schema_version(db)

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
            plan = self._rebuild_plan(spec, key, versions)
            if plan is not None:
                self._add_rebuild(plan, subject_id, creator_id, versions)
                continue
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
        )
        drift = capture_drift(manifest.get("captured_at"), row["captured_at"])
        if drift == "drift":
            self._add(
                code="manifest_captured_at_drift", severity="info", subject_type=kind,
                subject_id=subject_id, creator_id=creator_id, version=number,
                issue="manifest 與資料庫的 captured_at 有舊版取時造成的秒級差距。",
                evidence=f"version path: {safe_path}; field: captured_at; database later by ≤ 60s",
                repairability="not_needed",
                suggested_action="兩者為同一次捕捉；保留兩側原值，不改寫。",
            )
        elif drift is None:
            comparisons += (("captured_at", str(row["captured_at"]), "manifest_captured_at"),)
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

    def _audit_fancard_months(self, db: sqlite3.Connection) -> None:
        """Flag versions filed under an earlier month because the captured month's payment was not there yet."""
        by_month: dict[tuple[str, str], list[sqlite3.Row]] = defaultdict(list)
        for row in db.execute(
            "SELECT * FROM fancard_versions WHERE status='completed' "
            "ORDER BY creator_id,target_month,version_number"
        ):
            by_month[(str(row["creator_id"]), str(row["target_month"]))].append(row)
        misfiled: dict[tuple[str, str], list[sqlite3.Row]] = defaultdict(list)
        for (creator_id, month), versions in by_month.items():
            for row in versions:
                captured_month = fanbox_month(row["captured_at"])
                if captured_month is None or captured_month <= month:
                    continue
                paid = self._fancard_paid_months(Path(str(row["local_path"])))
                if paid is None or captured_month not in paid:
                    misfiled[(creator_id, captured_month)].append(row)
        for (creator_id, target_month), moved in misfiled.items():
            subject_id = f"{creator_id}/{target_month}"
            plan = self._fancard_month_plan(creator_id, target_month, moved, by_month)
            if plan is not None:
                self.rebuild_plans[f"fancard_month:fancard:{subject_id}"] = plan
            labels = ", ".join(f"{row['target_month']}/v{int(row['version_number']):04d}" for row in moved)
            self._add(
                code="fancard_month", severity="warning", subject_type="fancard",
                subject_id=subject_id, creator_id=creator_id,
                issue="Fan Card 版本的擷取月份（日本時間）晚於歸屬月份，且當時的付款紀錄沒有擷取月份；疑似月初換卡面時被存到上個月。",
                evidence=f"versions: {labels}; captured month (JST): {target_month}; payment for captured month: absent",
                repairability="automatic" if plan is not None else "manual",
                suggested_action=(
                    f"以 repair-copy 在副本中把這些版本移到 {target_month}，依擷取時間重新編號；保留 captured_at、卡面與 fancard.json。"
                    if plan is not None else
                    "版本證據不完整或仍有其他錯誤；先處理其他稽核問題，再人工確認月份。"
                ),
            )

    @staticmethod
    def _fancard_paid_months(version_path: Path) -> set[str] | None:
        try:
            payload = json.loads((version_path / "fancard.json").read_text(encoding="utf-8"))
            transactions = payload["body"].get("supportTransactions") or []
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return None
        return {str(item.get("targetMonth")) for item in transactions if isinstance(item, dict)}

    def _fancard_month_plan(
        self, creator_id: str, target_month: str, moved: list[sqlite3.Row],
        by_month: dict[tuple[str, str], list[sqlite3.Row]],
    ) -> FancardMonthPlan | None:
        moved_ids = {int(row["fancard_version_id"]) for row in moved}
        sources = sorted({str(row["target_month"]) for row in moved})
        for month in sources:
            # Misfiled versions must be the newest ones of their source month.
            flags = [int(row["fancard_version_id"]) in moved_ids for row in by_month[(creator_id, month)]]
            if flags != sorted(flags):
                return None
        subjects = {f"{creator_id}/{month}" for month in (*sources, target_month)}
        if any(
            item.subject_type == "fancard" and item.subject_id in subjects and item.severity == "error"
            for item in self.findings
        ):
            return None
        entries: list[FancardMonthEntry] = []
        for row in [*moved, *by_month.get((creator_id, target_month), [])]:
            path = Path(str(row["local_path"])).resolve()
            captured = parse_instant(row["captured_at"])
            if (
                captured is None or self._safe_path(path) == "[outside archive]"
                or path.parent.parent.name != str(row["target_month"])
                or not self._manifest_is_consistent(row)
            ):
                return None
            entries.append(FancardMonthEntry(
                row_id=int(row["fancard_version_id"]), source_month=str(row["target_month"]),
                number=int(row["version_number"]), path=path, captured=captured,
            ))
        entries.sort(key=lambda entry: entry.captured)
        if any(left.captured >= right.captured for left, right in zip(entries, entries[1:])):
            return None
        fancards_dirs = {entry.path.parent.parent.parent for entry in entries}
        if len(fancards_dirs) != 1:
            return None
        fancards_dir = fancards_dirs.pop()
        if fancards_dir.name != "fancards":
            return None
        return FancardMonthPlan(
            creator_id=creator_id, target_month=target_month, fancards_dir=fancards_dir,
            entries=entries, source_months=sources,
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

    def _rebuild_plan(
        self, spec: dict[str, object], key: tuple[str, ...], versions: list[sqlite3.Row],
    ) -> RebuildPlan | None:
        """Plan a version-row rebuild only when on-disk manifests are complete, verified evidence."""
        kind = str(spec["kind"])
        row_paths = [Path(str(row["local_path"])).resolve() for row in versions]
        parents = {path.parent for path in row_paths}
        if len(parents) != 1 or len(set(row_paths)) != len(row_paths):
            return None
        versions_dir = parents.pop()
        if versions_dir.name != "versions" or self._safe_path(versions_dir) == "[outside archive]":
            return None
        if not versions_dir.is_dir():
            return None  # nothing on disk to rebuild from; manifest_missing reports each version
        if any(str(row["status"]) != "completed" for row in versions):
            return None
        disk = sorted(
            path for path in versions_dir.iterdir()
            if path.is_dir() and re.fullmatch(r"v\d{4}", path.name)
        )
        if [int(path.name[1:]) for path in disk] != list(range(1, len(disk) + 1)):
            return None
        rows_by_path = dict(zip(row_paths, versions))
        if not set(rows_by_path) <= set(disk):
            return None
        if len(rows_by_path) == len(disk) and all(
            path.name == f"v{int(row['version_number']):04d}" for path, row in rows_by_path.items()
        ):
            return None  # rows already match the directories; nothing to rebuild, skip hashing

        entries: list[RebuildEntry] = []
        previous: datetime | None = None
        for number, path in enumerate(disk, start=1):
            try:
                manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError):
                return None
            if not isinstance(manifest, dict):
                return None
            captured = parse_instant(manifest.get("captured_at"))
            fingerprint = manifest.get("content_fingerprint")
            # Fan Card manifests carry no status: their versions are only written once completed.
            status = manifest.get("status", "completed" if kind == "fancard" else None)
            if (
                manifest.get("version") != number or status != "completed"
                or not self._rebuild_identity_matches(kind, key, path, manifest)
                or not isinstance(fingerprint, str) or not fingerprint
                or captured is None or (previous is not None and captured <= previous)
                or not self._files_verified(path, manifest)
            ):
                return None
            row = rows_by_path.get(path)
            if row is not None and (
                str(row["content_fingerprint"]) != fingerprint
                or capture_drift(manifest.get("captured_at"), row["captured_at"]) is None
            ):
                return None
            previous = captured
            entries.append(RebuildEntry(
                number=number, path=path, manifest=manifest,
                row_id=int(row[str(spec["row_id"])]) if row is not None else None,
            ))
        if len(versions) == len(disk) and all(
            int(rows_by_path[entry.path]["version_number"]) == entry.number for entry in entries
        ):
            return None
        return RebuildPlan(
            kind=kind, table=str(spec["table"]), row_id_column=str(spec["row_id"]),
            owner_id=key[0], target_month=key[1] if kind == "fancard" else None, entries=entries,
        )

    @staticmethod
    def _rebuild_identity_matches(
        kind: str, key: tuple[str, ...], path: Path, manifest: dict[str, object],
    ) -> bool:
        if kind == "post":
            # Post manifests carry no identity; the hash-verified post.json of that version does.
            files = manifest.get("files")
            if not isinstance(files, dict) or "post.json" not in files:
                return False
            try:
                post = json.loads((path / "post.json").read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError):
                return False
            return isinstance(post, dict) and str(post.get("post_id")) == key[0]
        if manifest.get("creator_id") != key[0]:
            return False
        return kind != "fancard" or manifest.get("target_month") == key[1]

    def _add_rebuild(
        self, plan: RebuildPlan, subject_id: str, creator_id: str | None, versions: list[sqlite3.Row],
    ) -> None:
        self._known_version_dirs.update(entry.path for entry in plan.entries)
        self.rebuild_plans[f"version_rebuild:{plan.kind}:{subject_id}"] = plan
        mapping = ", ".join(
            f"v{int(row['version_number']):04d}→{Path(str(row['local_path'])).name}"
            for row in versions
        )
        self._add(
            code="version_rebuild", severity="error", subject_type=plan.kind,
            subject_id=subject_id, creator_id=creator_id,
            issue="資料庫版本列與磁碟上完整的 manifest 歷史不一致，可依 manifest 確定性重建。",
            evidence=f"database: {mapping}; disk manifests: v0001–v{len(plan.entries):04d}",
            repairability="automatic",
            suggested_action="在副本中依 manifest 重新編號既有資料列並補回缺少的版本，不改寫任何檔案或捕捉時間。",
        )

    def _repair_action(self, finding: AuditFinding) -> AuditRepairAction:
        if finding.code == "version_rebuild":
            description = "依磁碟 manifest 重建版本資料列並更新 latest pointer。"
            prerequisites = [
                "所有版本目錄連續且 manifest 檔案 SHA-256 全部一致",
                "manifest captured_at 嚴格遞增",
                "既有資料列皆指向其中一個版本目錄且 fingerprint 相符",
            ]
        elif finding.code == "fancard_month":
            description = "把誤歸到上個月的 Fan Card 版本移到擷取月份，依擷取時間重新編號並重建 latest alias。"
            prerequisites = [
                "誤歸版本是來源月份最新的版本",
                "所有相關版本的 manifest 與檔案 SHA-256 一致",
                "合併後 captured_at 嚴格遞增",
            ]
        elif finding.code == "latest_pointer":
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
            and capture_drift(manifest.get("captured_at"), row["captured_at"]) is not None
        )
        return metadata_matches and self._files_verified(root, manifest)

    def _files_verified(self, root: Path, manifest: dict[str, object]) -> bool:
        files = manifest.get("files")
        if not isinstance(files, dict):
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

    _MAX_REPAIR_ROUNDS = 3

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

            database_backup = copied_database.with_name(f"{copied_database.name}.pre-repair.bak")
            shutil.copy2(copied_database, database_backup)
            source_schema = ArchiveAuditor(copied_config)._read_schema_version()
            self._migrate_copy(copied_database)

            applied: list[dict[str, object]] = []
            for _ in range(self._MAX_REPAIR_ROUNDS):
                auditor = ArchiveAuditor(copied_config)
                actions = auditor.run().repair_plan
                if not actions:
                    break
                before = {item.action_id: self._subject_state(copied_config, item) for item in actions}
                self._apply(copied_config, actions, auditor.rebuild_plans)
                applied.extend({
                    "action_id": item.action_id, "finding_code": item.finding_code,
                    "subject_type": item.subject_type, "subject_id": item.subject_id,
                    "description": item.description,
                    "before": before[item.action_id], "after": self._subject_state(copied_config, item),
                } for item in actions)
            indexer = IndexBuilder(copied_config)
            indexer.build(force=True)
            index_issues = indexer.check()
            if index_issues:
                raise RuntimeError(f"修復副本的靜態索引驗證失敗：{len(index_issues)} 項。")
            remaining = ArchiveAuditor(copied_config).run()
            if any(item.repairability == "automatic" for item in remaining.findings):
                raise RuntimeError("確定性修復後仍存在可自動修復問題。")

            from .service import ArchiveService  # service depends on this module's peers

            verify_issues = ArchiveService(copied_config).verify()
            report = self._write_report(
                staging, source_schema, remaining, applied, verify_issues, database_backup,
            )

            self._remap_paths(copied_database, staging, destination)
            self._remap_paths(database_backup, staging, destination)
            BackupStorage._replace_with_retry(staging, destination)
            return RepairCopyResult(
                applied_actions=len(applied),
                remaining_findings=remaining.blocking_count,
                database_backup=database_backup.relative_to(staging).as_posix(),
                report=report.relative_to(staging).as_posix(),
                unrecoverable_findings=sum(
                    item.repairability == "unrecoverable" for item in remaining.findings
                ),
                verify_issue_count=len(verify_issues),
            )
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    @staticmethod
    def _write_report(
        staging: Path, source_schema: int | None, remaining: AuditReport,
        applied: list[dict[str, object]], verify_issues: list, database_backup: Path,
    ) -> Path:
        """Difference summary kept inside the repaired copy; never contains absolute paths."""

        def relative(value: str) -> str:
            try:
                return Path(value).resolve().relative_to(staging.resolve()).as_posix()
            except ValueError:
                return "[outside archive]" if Path(value).is_absolute() else value

        report = staging / "repair-report.json"
        payload = {
            "generated_at": datetime.now(UTC).isoformat(),
            "source_schema_version": source_schema,
            "result_schema_version": remaining.schema_version,
            "database_backup": database_backup.relative_to(staging).as_posix(),
            "applied": applied,
            "remaining": [
                {
                    **item.model_dump(include={
                        "code", "severity", "subject_type", "subject_id", "creator_id", "version",
                        "issue", "evidence", "repairability", "suggested_action",
                    }),
                    "marking": (
                        "unknown/unrecoverable" if item.repairability == "unrecoverable"
                        else "needs manual review"
                    ),
                }
                for item in remaining.findings if item.severity != "info"
            ],
            "info_count": remaining.finding_count - remaining.blocking_count,
            "verify": {
                "issue_count": len(verify_issues),
                "issues": [
                    {"path": relative(issue.path), "reason": issue.reason}
                    for issue in verify_issues[:200]
                ],
            },
        }
        report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return report

    _STATE_QUERIES = {
        "post": ("post_versions", "version_id", "post_id=?",
                 "SELECT latest_version_id FROM posts WHERE post_id=?", "post.json"),
        "profile": ("creator_profile_versions", "profile_version_id", "creator_id=?",
                    "SELECT latest_profile_version_id FROM creators WHERE creator_id=?", "profile.json"),
        "fancard": ("fancard_versions", "fancard_version_id", "creator_id=? AND target_month=?",
                    None, "fancard.json"),
    }

    @classmethod
    def _subject_state(cls, config: AppConfig, action: AuditRepairAction) -> dict[str, object]:
        """Version → directory → fingerprint mapping, latest pointer and alias state of one subject."""
        table, row_id, key_sql, pointer_sql, alias = cls._STATE_QUERIES[action.subject_type]
        params = (
            tuple(action.subject_id.rsplit("/", 1)) if action.subject_type == "fancard"
            else (action.subject_id,)
        )
        uri = config.storage.database.resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as db:
            db.row_factory = sqlite3.Row
            rows = list(db.execute(
                f"SELECT {row_id} AS id,version_number,status,content_fingerprint,captured_at,local_path "
                f"FROM {table} WHERE {key_sql} ORDER BY version_number", params,
            ))
            pointer = db.execute(pointer_sql, params).fetchone() if pointer_sql else None
        completed = [row for row in rows if str(row["status"]) == "completed"]
        if pointer_sql:
            latest = next((row for row in rows if pointer and row["id"] == pointer[0]), None)
        else:
            latest = completed[-1] if completed else None
        alias_matches = None
        if completed:
            canonical = Path(str(completed[-1]["local_path"]))
            try:
                alias_matches = ArchiveAuditor._sha256(canonical.parent.parent / alias) == (
                    ArchiveAuditor._sha256(canonical / alias)
                )
            except OSError:
                alias_matches = False
        return {
            "versions": [
                {
                    "version": int(row["version_number"]),
                    "directory": Path(str(row["local_path"])).name,
                    "fingerprint": str(row["content_fingerprint"])[:12],
                    "captured_at": row["captured_at"],
                }
                for row in rows
            ],
            "latest": f"v{int(latest['version_number']):04d}" if latest else None,
            "alias_matches_latest": alias_matches,
        }

    @staticmethod
    def _migrate_copy(copied_database: Path) -> None:
        # Older schemas keep a content-fingerprint uniqueness rule that blocks A→B→A rebuilds.
        # The pre-repair backup already preserves the unmigrated database, so drop the extra one.
        migration_backup = copied_database.with_name(f"{copied_database.name}.pre-v{SCHEMA_VERSION}.bak")
        existed = migration_backup.exists()
        Database(copied_database)
        if not existed:
            migration_backup.unlink(missing_ok=True)

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

    def _apply(
        self, config: AppConfig, actions: list[AuditRepairAction],
        rebuild_plans: dict[str, RebuildPlan | FancardMonthPlan],
    ) -> None:
        with closing(sqlite3.connect(config.storage.database)) as db, db:
            db.row_factory = sqlite3.Row
            for action in actions:
                if action.finding_code == "version_rebuild":
                    self._apply_rebuild(db, rebuild_plans[action.action_id])
                    continue
                if action.finding_code == "fancard_month":
                    self._apply_fancard_month(db, rebuild_plans[action.action_id])
                    continue
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
    def _apply_rebuild(db: sqlite3.Connection, plan: RebuildPlan) -> None:
        table, row_id = plan.table, plan.row_id_column
        existing = [entry for entry in plan.entries if entry.row_id is not None]
        # Park renumbered rows on negative numbers first so UNIQUE(version_number) never collides.
        for entry in existing:
            db.execute(f"UPDATE {table} SET version_number=? WHERE {row_id}=?", (-entry.number, entry.row_id))
        latest_id: int | None = None
        for entry in plan.entries:
            if entry.row_id is not None:
                db.execute(f"UPDATE {table} SET version_number=? WHERE {row_id}=?", (entry.number, entry.row_id))
                latest_id = entry.row_id
                continue
            files = {str(name): str(digest) for name, digest in dict(entry.manifest["files"]).items()}
            if plan.kind == "post":
                cursor = db.execute(
                    "INSERT INTO post_versions(post_id,version_number,remote_updated_at,captured_at,"
                    "content_fingerprint,status,local_path,markdown_path,json_path) "
                    "VALUES(?,?,?,?,?,'completed',?,?,?)",
                    (plan.owner_id, entry.number, entry.manifest.get("remote_updated_at"),
                     entry.manifest["captured_at"], entry.manifest["content_fingerprint"],
                     str(entry.path), str(entry.path / "post.md") if "post.md" in files else None,
                     str(entry.path / "post.json")),
                )
                latest_id = int(cursor.lastrowid)
                continue
            media = next((name for name in files if name.startswith("cover." if plan.kind == "profile" else "card.")), None)
            media_path = str(entry.path / media) if media else None
            media_hash = files[media] if media else None
            if plan.kind == "profile":
                cursor = db.execute(
                    "INSERT INTO creator_profile_versions(creator_id,version_number,captured_at,"
                    "content_fingerprint,status,local_path,json_path,cover_path,cover_sha256) "
                    "VALUES(?,?,?,?,'completed',?,?,?,?)",
                    (plan.owner_id, entry.number, entry.manifest["captured_at"],
                     entry.manifest["content_fingerprint"], str(entry.path),
                     str(entry.path / "profile.json"), media_path, media_hash),
                )
            else:
                cursor = db.execute(
                    "INSERT INTO fancard_versions(creator_id,target_month,version_number,captured_at,"
                    "content_fingerprint,status,local_path,image_path,image_sha256) "
                    "VALUES(?,?,?,?,?,'completed',?,?,?)",
                    (plan.owner_id, plan.target_month, entry.number, entry.manifest["captured_at"],
                     entry.manifest["content_fingerprint"], str(entry.path), media_path, media_hash),
                )
            latest_id = int(cursor.lastrowid)
        if plan.kind == "profile":
            db.execute(
                "UPDATE creators SET latest_profile_version_id=? WHERE creator_id=?",
                (latest_id, plan.owner_id),
            )
        elif plan.kind == "post":
            db.execute("UPDATE posts SET latest_version_id=? WHERE post_id=?", (latest_id, plan.owner_id))

    @classmethod
    def _apply_fancard_month(cls, db: sqlite3.Connection, plan: FancardMonthPlan) -> None:
        """Rebuild the target month's versions directory in staging, then swap it in (copy only)."""
        target_root = plan.fancards_dir / plan.target_month
        target_root.mkdir(parents=True, exist_ok=True)
        token = uuid.uuid4().hex
        staging = target_root / f".versions.{token}.tmp"
        staging.mkdir()
        for number, entry in enumerate(plan.entries, start=1):
            destination = staging / f"v{number:04d}"
            shutil.copytree(entry.path, destination, copy_function=shutil.copy2)
            if entry.source_month != plan.target_month or entry.number != number:
                cls._relabel_fancard_version(destination, plan.target_month, number, entry)
        versions = target_root / "versions"
        retired = target_root / f".versions.{token}.old"
        if versions.exists():
            os.replace(versions, retired)
        os.replace(staging, versions)
        shutil.rmtree(retired, ignore_errors=True)
        for entry in plan.entries:
            if entry.source_month != plan.target_month:
                shutil.rmtree(entry.path)

        # Park rows on negative numbers first so UNIQUE(creator_id,target_month,version_number) never collides.
        for entry in plan.entries:
            db.execute(
                "UPDATE fancard_versions SET version_number=? WHERE fancard_version_id=?",
                (-entry.row_id, entry.row_id),
            )
        for number, entry in enumerate(plan.entries, start=1):
            path = versions / f"v{number:04d}"
            image = db.execute(
                "SELECT image_path FROM fancard_versions WHERE fancard_version_id=?", (entry.row_id,),
            ).fetchone()[0]
            db.execute(
                "UPDATE fancard_versions SET target_month=?,version_number=?,local_path=?,image_path=? "
                "WHERE fancard_version_id=?",
                (plan.target_month, number, str(path),
                 str(path / Path(str(image)).name) if image else image, entry.row_id),
            )

        for month in (*plan.source_months, plan.target_month):
            month_root = plan.fancards_dir / month
            latest = db.execute(
                "SELECT local_path FROM fancard_versions WHERE creator_id=? AND target_month=? "
                "AND status='completed' ORDER BY version_number DESC LIMIT 1",
                (plan.creator_id, month),
            ).fetchone()
            if latest is not None:
                cls._refresh_fancard_alias(month_root, Path(str(latest[0])))
            elif not any((month_root / "versions").glob("*")):
                shutil.rmtree(month_root)

    @staticmethod
    def _relabel_fancard_version(
        version: Path, month: str, number: int, entry: FancardMonthEntry,
    ) -> None:
        manifest_path = version / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        markdown = version / "fancard.md"
        if markdown.is_file():
            text = markdown.read_bytes().decode("utf-8")
            for pattern, replacement in (
                (r"^target_month: [^\r\n]*", f"target_month: {json.dumps(month)}"),
                (r"^archive_version: \d+(?=\r?$)", f"archive_version: {number}"),
                (r"^# Fan Card — \d{4}-\d{2}(?=\r?$)", f"# Fan Card — {month}"),
            ):
                text = re.sub(pattern, replacement, text, count=1, flags=re.MULTILINE)
            markdown.write_bytes(text.encode("utf-8"))
            if isinstance(manifest.get("files"), dict) and "fancard.md" in manifest["files"]:
                manifest["files"]["fancard.md"] = ArchiveAuditor._sha256(markdown)
        if entry.source_month != month:
            manifest["target_month_payment_seen"] = False
        manifest.setdefault("relocated_from", {"target_month": entry.source_month, "version": entry.number})
        manifest.update(version=number, target_month=month)
        manifest_path.write_bytes((json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    @staticmethod
    def _refresh_fancard_alias(month_root: Path, version: Path) -> None:
        for name in ("card.jpeg", "card.png"):
            (month_root / name).unlink(missing_ok=True)
        for source in version.iterdir():
            if source.name in {"fancard.json", "fancard.md"} or source.name.startswith("card."):
                temporary = month_root / f".{source.name}.{uuid.uuid4().hex}.tmp"
                shutil.copy2(source, temporary)
                os.replace(temporary, month_root / source.name)

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
