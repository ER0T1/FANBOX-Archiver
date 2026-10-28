from __future__ import annotations

import mimetypes
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .config import AppConfig
from .database import Database
from .models import Asset, CreatorProfile, Post
from .security import confined_path


class ReaderNotFound(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class MediaFile:
    path: Path
    filename: str
    media_type: str


class ArchiveReader:
    """Read archive data on demand without generating a static site."""

    def __init__(self, config: AppConfig):
        self.root = config.storage.output_dir.resolve()
        self.db = Database(config.storage.database)

    def status(self) -> dict[str, Any]:
        counts = self.db.statistics()
        latest = self.db.latest_run()
        return {
            "counts": counts,
            "latest_run": dict(latest) if latest else None,
        }

    def list_posts(
        self, *, page: int = 1, page_size: int = 50, query: str = "",
        creator: str = "", status: str = "",
    ) -> dict[str, Any]:
        page = max(1, page)
        page_size = min(max(1, page_size), 100)
        where, values = self._post_filter(query=query, creator=creator, status=status)
        pin_order = "p.is_pinned DESC," if creator else ""
        with self.db.connect() as db:
            total = int(db.execute(
                f"SELECT COUNT(*) FROM posts p JOIN creators c ON c.creator_id=p.creator_id {where}", values
            ).fetchone()[0])
            rows = list(db.execute(
                f"""
                SELECT p.*,c.name AS creator_name,
                       COUNT(v.version_id) AS version_count,
                       MAX(CASE WHEN v.status='completed' THEN v.version_number END) AS latest_version
                FROM posts p
                JOIN creators c ON c.creator_id=p.creator_id
                LEFT JOIN post_versions v ON v.post_id=p.post_id
                {where}
                GROUP BY p.post_id
                ORDER BY {pin_order}p.published_at DESC,p.post_id DESC
                LIMIT ? OFFSET ?
                """,
                [*values, page_size, (page - 1) * page_size],
            ))
        items = [self._post_summary(row) for row in rows]
        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": max(1, (total + page_size - 1) // page_size),
        }

    def post_navigation(
        self, post_id: str, *, creator: str = "", query: str = "",
    ) -> dict[str, Any]:
        where, values = self._post_filter(query=query, creator=creator)
        pin_order = "p.is_pinned DESC," if creator else ""
        with self.db.connect() as db:
            rows = list(db.execute(
                f"""
                SELECT p.post_id,p.creator_id,c.name AS creator_name,p.title,
                       p.published_at,p.is_pinned
                FROM posts p
                JOIN creators c ON c.creator_id=p.creator_id
                {where}
                ORDER BY {pin_order}p.published_at DESC,p.post_id DESC
                """,
                values,
            ))
        index = next(
            (position for position, row in enumerate(rows) if str(row["post_id"]) == post_id),
            None,
        )
        if index is None:
            return {"previous": None, "next": None, "position": None, "total": len(rows)}

        def summary(position: int) -> dict[str, Any] | None:
            if position < 0 or position >= len(rows):
                return None
            row = rows[position]
            return {
                "post_id": str(row["post_id"]),
                "creator_id": str(row["creator_id"]),
                "creator_name": str(row["creator_name"]),
                "title": str(row["title"]),
                "published_at": row["published_at"],
                "is_pinned": bool(row["is_pinned"]),
            }

        return {
            "previous": summary(index - 1),
            "next": summary(index + 1),
            "position": index + 1,
            "total": len(rows),
        }

    def list_creators(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for row in self.db.creator_listing(supporting_only=False):
            creator_id = str(row["creator_id"])
            result.append({
                "creator_id": creator_id,
                "name": str(row["name"]),
                "url": row["url"],
                "post_count": int(row["post_count"] or 0),
                "completed_count": int(row["completed_count"] or 0),
                "last_sync": row["last_sync"],
                "status": str(row["status"]),
                "avatar_url": f"/api/creators/{quote(creator_id, safe='')}/avatar" if row["icon_path"] else None,
                "profile_available": bool(row["profile_version_count"]),
                "profile_version_count": int(row["profile_version_count"]),
                "latest_profile_captured_at": row["latest_profile_captured_at"],
            })
        return result

    def creator(self, creator_id: str) -> dict[str, Any]:
        item = next(
            (creator for creator in self.list_creators() if creator["creator_id"] == creator_id),
            None,
        )
        if item is None:
            raise ReaderNotFound("找不到創作者")
        cards = self.list_fancards(creator=creator_id)
        item["fancard_count"] = len(cards)
        item["fanbox_url"] = f"https://www.fanbox.cc/@{creator_id}"
        return item

    def creator_profile(self, creator_id: str, *, version: int | None = None) -> dict[str, Any]:
        row, profile = self._load_profile(creator_id, version)
        number = int(row["version_number"])
        versions = [
            {
                "number": int(item["version_number"]),
                "captured_at": item["captured_at"],
                "status": item["status"],
            }
            for item in self.db.profile_versions(creator_id)
        ]
        profile_items = []
        for index, item in enumerate(profile.profile_items):
            value = item.model_dump(
                mode="json", exclude={"image_path", "image_sha256"}
            )
            value["image_url"] = (
                f"/api/creators/{quote(creator_id, safe='')}/profile/versions/"
                f"{number}/items/{index}/image" if item.image_path else None
            )
            profile_items.append(value)
        return {
            "creator_id": profile.creator_id,
            "name": profile.name,
            "description": profile.description,
            "fanbox_url": profile.fanbox_url,
            "has_adult_content": profile.has_adult_content,
            "is_accepting_request": profile.is_accepting_request,
            "is_stopped": profile.is_stopped,
            "profile_items": profile_items,
            "cover_url": (
                f"/api/creators/{quote(creator_id, safe='')}/profile/versions/{number}/cover"
                if row["cover_path"] else None
            ),
            "version": number,
            "captured_at": row["captured_at"],
            "versions": versions,
        }

    def creator_profile_versions(self, creator_id: str) -> list[dict[str, Any]]:
        if self.db.creator_row(creator_id) is None:
            raise ReaderNotFound("找不到創作者")
        return [
            {
                "number": int(row["version_number"]),
                "captured_at": row["captured_at"],
                "status": row["status"],
                "has_cover": bool(row["cover_path"]),
            }
            for row in self.db.profile_versions(creator_id)
        ]

    def creator_profile_cover(self, creator_id: str, version: int) -> MediaFile:
        row, _ = self._load_profile(creator_id, version)
        if not row["cover_path"]:
            raise ReaderNotFound("此 Profile 沒有橫幅")
        return self._local_media(Path(str(row["cover_path"])), f"{creator_id}-cover")

    def creator_profile_item_image(
        self, creator_id: str, version: int, item_index: int,
    ) -> MediaFile:
        row, profile = self._load_profile(creator_id, version)
        if item_index < 0 or item_index >= len(profile.profile_items):
            raise ReaderNotFound("找不到 Profile 圖片")
        item = profile.profile_items[item_index]
        if not item.image_path:
            raise ReaderNotFound("此 Profile Item 沒有本機圖片")
        version_root = Path(str(row["local_path"])).resolve()
        try:
            version_root.relative_to(self.root)
            path = confined_path(version_root, Path(item.image_path))
        except ValueError as exc:
            raise ReaderNotFound("Profile 圖片路徑不安全") from exc
        return self._local_media(path, f"{creator_id}-profile-{item_index + 1}")

    def creator_avatar(self, creator_id: str) -> MediaFile:
        row = self.db.creator_row(creator_id)
        if row is None or not row["icon_path"]:
            raise ReaderNotFound("找不到創作者頭像")
        return self._local_media(Path(str(row["icon_path"])), f"{creator_id}-avatar")

    def list_fancards(self, *, query: str = "", creator: str = "") -> list[dict[str, Any]]:
        clauses = ["f.status='completed'"]
        values: list[object] = []
        if creator:
            clauses.append("f.creator_id=?")
            values.append(creator)
        if query:
            clauses.append("(f.creator_id LIKE ? ESCAPE '\\' OR f.target_month LIKE ? ESCAPE '\\')")
            pattern = f"%{self._escape_like(query)}%"
            values.extend((pattern, pattern))
        where = " AND ".join(clauses)
        with self.db.connect() as db:
            rows = list(db.execute(
                f"""
                SELECT f.*,c.name AS creator_name,
                       (SELECT COUNT(*) FROM fancard_versions all_f
                        WHERE all_f.creator_id=f.creator_id
                          AND all_f.target_month=f.target_month) AS version_count
                FROM fancard_versions f
                JOIN creators c ON c.creator_id=f.creator_id
                WHERE {where}
                  AND f.version_number=(
                    SELECT MAX(latest.version_number) FROM fancard_versions latest
                    WHERE latest.creator_id=f.creator_id
                      AND latest.target_month=f.target_month
                      AND latest.status='completed'
                  )
                ORDER BY f.target_month DESC,f.creator_id COLLATE NOCASE
                """,
                values,
            ))
        return [self._fancard_summary(row) for row in rows]

    def fancard(
        self, creator_id: str, target_month: str, *, version: int | None = None,
    ) -> dict[str, Any]:
        row, body = self._load_fancard(creator_id, target_month, version)
        with self.db.connect() as db:
            versions = list(db.execute(
                "SELECT * FROM fancard_versions WHERE creator_id=? AND target_month=? "
                "ORDER BY version_number",
                (creator_id, target_month),
            ))
        plan = body.get("plan") if isinstance(body.get("plan"), dict) else {}
        user = plan.get("user") if isinstance(plan.get("user"), dict) else {}
        number = int(row["version_number"])
        months = sorted({
            str(item.get("targetMonth"))
            for item in (body.get("supportTransactions") or [])
            if isinstance(item, dict) and re.fullmatch(r"\d{4}-\d{2}", str(item.get("targetMonth") or ""))
        })
        return {
            "creator_id": creator_id,
            "creator_name": str(user.get("name") or creator_id),
            "target_month": target_month,
            "plan_title": str(plan.get("title") or ""),
            "fee": plan.get("fee"),
            "description": str(plan.get("description") or ""),
            "perks": plan.get("perks") if isinstance(plan.get("perks"), list) else [],
            "support_start": body.get("supportStartDatetime"),
            "support_months": months,
            "version": number,
            "versions": [
                {
                    "number": int(item["version_number"]),
                    "captured_at": item["captured_at"],
                    "status": item["status"],
                }
                for item in versions
            ],
            "image_url": (
                f"/api/fancards/{quote(creator_id, safe='')}/{target_month}/"
                f"versions/{number}/image"
                if row["image_path"] else None
            ),
        }

    def fancard_image(self, creator_id: str, target_month: str, version: int) -> MediaFile:
        row, _ = self._load_fancard(creator_id, target_month, version)
        if not row["image_path"]:
            raise ReaderNotFound("此 Fan Card 沒有卡面")
        return self._local_media(
            Path(str(row["image_path"])), f"{creator_id}-{target_month}-card"
        )

    def post(self, post_id: str, *, version: int | None = None) -> dict[str, Any]:
        row, post = self._load_post(post_id, version)
        number = int(row["version_number"])
        versions = [
            {
                "number": int(item["version_number"]),
                "captured_at": item["captured_at"],
                "remote_updated_at": item["remote_updated_at"],
                "status": item["status"],
            }
            for item in self.db.version_rows(post_id)
        ]
        assets = {asset.asset_id: asset for asset in post.assets}
        blocks: list[dict[str, Any]] = []
        for block in post.blocks:
            item = {
                "type": block.type,
                "text": block.text,
                "asset_id": block.asset_id,
                "url": block.url,
                "name": block.name,
                "level": block.level,
                "styles": [style.model_dump(mode="json") for style in block.styles],
            }
            asset = assets.get(block.asset_id or "")
            if asset and asset.local_path:
                item["media_url"] = self._media_url(post_id, number, asset.asset_id)
                item["media_type"] = asset.type
                item["filename"] = asset.original_name
            if block.type == "embed":
                item["embed"] = self._embed_preview(post, block, item.get("media_url"))
            blocks.append(item)
        cover_url = None
        if post.cover and post.cover.local_path:
            cover_url = self._media_url(post_id, number, post.cover.asset_id)
        return {
            "post_id": post.post_id,
            "creator_id": post.creator_id,
            "creator_name": post.creator_name,
            "title": post.title,
            "published_at": post.published_at.isoformat() if post.published_at else None,
            "updated_at": post.updated_at.isoformat() if post.updated_at else None,
            "url": post.url,
            "post_type": post.post_type,
            "fee_required": post.fee_required,
            "is_pinned": bool(post.raw.get("isPinned", False)),
            "tags": post.tags,
            "status": row["status"],
            "version": number,
            "versions": versions,
            "cover_url": cover_url,
            "blocks": blocks,
        }

    def media(self, post_id: str, version: int, asset_id: str) -> MediaFile:
        row, post = self._load_post(post_id, version)
        asset = next(
            (item for item in [*post.assets, *([post.cover] if post.cover else [])]
             if item.asset_id == asset_id),
            None,
        )
        if not asset or not asset.local_path:
            raise ReaderNotFound("找不到指定資源")
        version_root = Path(str(row["local_path"])).resolve()
        try:
            version_root.relative_to(self.root)
            path = confined_path(version_root, Path(asset.local_path))
        except ValueError as exc:
            raise ReaderNotFound("資源路徑不安全") from exc
        if not path.is_file():
            raise ReaderNotFound("資源檔案不存在")
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return MediaFile(path, asset.original_name or path.name, media_type)

    def _embed_preview(
        self, source_post: Post, block: Any, cover_url: str | None,
    ) -> dict[str, Any] | None:
        """Return presentation data for an archived URL embed.

        Old archives may only retain ``urlEmbedId`` on the block, so use the
        untouched post response as a fallback.  A local target is advertised
        only when its latest completed JSON can actually be read.
        """
        raw = block.raw if isinstance(block.raw, dict) else {}
        embed_id = str(raw.get("urlEmbedId") or "")
        embed = raw.get("embed") if isinstance(raw.get("embed"), dict) else None
        if embed is None:
            body = source_post.raw.get("body") if isinstance(source_post.raw, dict) else None
            embed_map = body.get("urlEmbedMap") if isinstance(body, dict) else None
            candidate = embed_map.get(embed_id) if isinstance(embed_map, dict) else None
            embed = candidate if isinstance(candidate, dict) else {}

        if str(embed.get("type") or "") != "fanbox.post":
            return None
        info = embed.get("postInfo") if isinstance(embed.get("postInfo"), dict) else {}
        target_post_id = str(info.get("id") or "")
        creator_id = str(info.get("creatorId") or "")
        if not target_post_id.isdigit() or not creator_id:
            return None

        fanbox_url = f"https://www.fanbox.cc/@{creator_id}/posts/{target_post_id}"
        local_available = False
        try:
            self._load_post(target_post_id, None)
            local_available = True
        except ReaderNotFound:
            pass

        user = info.get("user") if isinstance(info.get("user"), dict) else {}
        fee = info.get("feeRequired")
        return {
            "kind": "fanbox.post",
            "post_id": target_post_id,
            "creator_id": creator_id,
            "creator_name": str(user.get("name") or creator_id),
            "title": str(info.get("title") or block.name or "FANBOX 投稿"),
            "excerpt": str(info.get("excerpt") or block.text or ""),
            "published_at": info.get("publishedDatetime"),
            "fee_required": fee if isinstance(fee, int) else None,
            "cover_url": cover_url,
            "fanbox_url": fanbox_url,
            "local_available": local_available,
        }

    def _load_post(self, post_id: str, version: int | None) -> tuple[Any, Post]:
        if not post_id.isdigit():
            raise ReaderNotFound("投稿 ID 無效")
        rows = self.db.version_rows(post_id)
        if version is None:
            candidates = [row for row in rows if row["status"] == "completed"]
            row = candidates[-1] if candidates else None
        else:
            row = next((item for item in rows if int(item["version_number"]) == version), None)
        if row is None:
            raise ReaderNotFound("找不到投稿版本")
        source = Path(str(row["json_path"] or ""))
        try:
            source.resolve().relative_to(self.root)
        except ValueError as exc:
            raise ReaderNotFound("投稿資料路徑不安全") from exc
        if not source.is_file():
            raise ReaderNotFound("投稿資料檔案不存在")
        try:
            post = Post.model_validate_json(source.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ReaderNotFound("投稿資料無法讀取") from exc
        return row, post

    def _load_profile(
        self, creator_id: str, version: int | None,
    ) -> tuple[Any, CreatorProfile]:
        rows = self.db.profile_versions(creator_id)
        if version is None:
            completed = [row for row in rows if row["status"] == "completed"]
            row = completed[-1] if completed else None
        else:
            row = next(
                (item for item in rows if int(item["version_number"]) == version), None
            )
        if row is None:
            raise ReaderNotFound("找不到 Profile 版本")
        source = Path(str(row["json_path"] or "")).resolve()
        try:
            source.relative_to(self.root)
        except ValueError as exc:
            raise ReaderNotFound("Profile 資料路徑不安全") from exc
        if not source.is_file():
            raise ReaderNotFound("Profile 資料檔案不存在")
        try:
            profile = CreatorProfile.model_validate_json(source.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ReaderNotFound("Profile 資料無法讀取") from exc
        return row, profile

    def _load_fancard(
        self, creator_id: str, target_month: str, version: int | None,
    ) -> tuple[Any, dict[str, Any]]:
        if not re.fullmatch(r"\d{4}-\d{2}", target_month):
            raise ReaderNotFound("Fan Card 月份無效")
        with self.db.connect() as db:
            rows = list(db.execute(
                "SELECT * FROM fancard_versions WHERE creator_id=? AND target_month=? "
                "ORDER BY version_number",
                (creator_id, target_month),
            ))
        if version is None:
            completed = [row for row in rows if row["status"] == "completed"]
            row = completed[-1] if completed else None
        else:
            row = next((item for item in rows if int(item["version_number"]) == version), None)
        if row is None:
            raise ReaderNotFound("找不到 Fan Card 版本")
        source = Path(str(row["local_path"])).resolve() / "fancard.json"
        try:
            source.relative_to(self.root)
        except ValueError as exc:
            raise ReaderNotFound("Fan Card 資料路徑不安全") from exc
        if not source.is_file():
            raise ReaderNotFound("Fan Card 資料檔案不存在")
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ReaderNotFound("Fan Card 資料無法讀取") from exc
        body = payload.get("body")
        if not isinstance(body, dict):
            raise ReaderNotFound("Fan Card 資料格式無效")
        return row, body

    def _fancard_summary(self, row: Any) -> dict[str, Any]:
        try:
            _, body = self._load_fancard(
                str(row["creator_id"]), str(row["target_month"]), int(row["version_number"])
            )
        except ReaderNotFound:
            body = {}
        plan = body.get("plan") if isinstance(body.get("plan"), dict) else {}
        return {
            "creator_id": str(row["creator_id"]),
            "creator_name": str(row["creator_name"]),
            "target_month": str(row["target_month"]),
            "plan_title": str(plan.get("title") or ""),
            "fee": plan.get("fee"),
            "version_count": int(row["version_count"] or 0),
            "image_url": (
                f"/api/fancards/{quote(str(row['creator_id']), safe='')}/{row['target_month']}/"
                f"versions/{int(row['version_number'])}/image"
                if row["image_path"] else None
            ),
        }

    def _local_media(self, path: Path, fallback_name: str) -> MediaFile:
        resolved = path.resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise ReaderNotFound("資源路徑不安全") from exc
        if not resolved.is_file():
            raise ReaderNotFound("資源檔案不存在")
        media_type = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
        return MediaFile(resolved, resolved.name or fallback_name, media_type)

    def _post_summary(self, row: Any) -> dict[str, Any]:
        item = {
            "post_id": str(row["post_id"]),
            "creator_id": str(row["creator_id"]),
            "creator_name": str(row["creator_name"]),
            "title": str(row["title"]),
            "published_at": row["published_at"],
            "updated_at": row["updated_at"],
            "status": str(row["status"]),
            "version_count": int(row["version_count"] or 0),
            "latest_version": int(row["latest_version"]) if row["latest_version"] is not None else None,
            "cover_url": None,
            "fee_required": None,
            "is_pinned": bool(row["is_pinned"]),
            "tags": [],
        }
        if item["latest_version"] is not None:
            try:
                _, post = self._load_post(item["post_id"], item["latest_version"])
                item["fee_required"] = post.fee_required
                item["tags"] = post.tags
                if post.cover and post.cover.local_path:
                    item["cover_url"] = self._media_url(
                        item["post_id"], item["latest_version"], post.cover.asset_id
                    )
            except ReaderNotFound:
                pass
        return item

    def _post_filter(
        self, *, query: str = "", creator: str = "", status: str = "",
    ) -> tuple[str, list[object]]:
        clauses: list[str] = []
        values: list[object] = []
        if query:
            clauses.append(
                "(p.title LIKE ? ESCAPE '\\' OR p.post_id LIKE ? ESCAPE '\\' "
                "OR p.creator_id LIKE ? ESCAPE '\\' OR c.name LIKE ? ESCAPE '\\')"
            )
            pattern = f"%{self._escape_like(query)}%"
            values.extend((pattern, pattern, pattern, pattern))
        if creator:
            clauses.append("p.creator_id=?")
            values.append(creator)
        if status:
            clauses.append("p.status=?")
            values.append(status)
        return (f"WHERE {' AND '.join(clauses)}" if clauses else "", values)

    @staticmethod
    def _escape_like(value: str) -> str:
        return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    @staticmethod
    def _media_url(post_id: str, version: int, asset_id: str) -> str:
        return f"/api/posts/{post_id}/versions/{version}/media/{quote(asset_id, safe='')}"
