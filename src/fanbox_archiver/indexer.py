from __future__ import annotations

import html
import json
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

from .config import AppConfig
from .database import Database
from .downloader import sha256_file
from .models import CreatorProfile, Post
from .security import confined_path, safe_filename
from .storage import BackupStorage


TEMPLATE_VERSION = 9
TAIPEI = timezone(timedelta(hours=8))


@dataclass(slots=True)
class IndexBuildResult:
    rendered: int
    reused: int
    warnings: list[str]
    index_path: Path


class IndexBuilder:
    def __init__(self, config: AppConfig):
        self.config = config
        self.root = config.storage.output_dir.resolve()
        self.db = Database(config.storage.database)
        self.package_assets = Path(__file__).with_name("site_assets")
        self.shared_assets = Path(__file__).with_name("web_assets")

    def build(self, *, force: bool = False) -> IndexBuildResult:
        self.root.mkdir(parents=True, exist_ok=True)
        current_site = self.root / "_site"
        old_state = self._read_json(current_site / "state.json") if not force else {}
        staging = self.root / f"._site.{uuid.uuid4().hex}.tmp"
        staging.mkdir(parents=True)
        rendered = reused = 0
        warnings: list[str] = []
        state_pages: dict[str, str] = {}
        creators = self._creator_data()
        posts: list[dict] = []
        fancards: list[dict] = []

        try:
            assets = staging / "assets"
            assets.mkdir()
            for name in ("app.css", "app.js", "theme.js", "icons.svg"):
                shutil.copy2(self.package_assets / name, assets / name)
            shutil.copy2(self.shared_assets / "design-tokens.css", assets / "design-tokens.css")

            for creator in creators:
                page_rendered, page_reused, page_warnings, page_state = self._build_profile_pages(
                    creator, staging, current_site, old_state
                )
                rendered += page_rendered
                reused += page_reused
                warnings.extend(page_warnings)
                state_pages.update(page_state)

            with self.db.connect() as db:
                post_rows = list(db.execute("SELECT * FROM posts ORDER BY published_at DESC,post_id DESC"))
                completed_versions = list(db.execute(
                    "SELECT post_id,json_path FROM post_versions WHERE status='completed'"
                ))
            self._readable_post_ids = {
                str(row["post_id"]) for row in completed_versions
                if row["json_path"] and Path(str(row["json_path"])).is_file()
            }
            ordered_readable_ids = [
                str(row["post_id"]) for row in post_rows
                if str(row["post_id"]) in self._readable_post_ids
            ]
            self._post_neighbors = {
                post_id: {
                    "previous": ordered_readable_ids[index - 1] if index > 0 else None,
                    "next": ordered_readable_ids[index + 1] if index + 1 < len(ordered_readable_ids) else None,
                    "position": index + 1,
                    "total": len(ordered_readable_ids),
                }
                for index, post_id in enumerate(ordered_readable_ids)
            }
            for row in post_rows:
                item, page_rendered, page_reused, page_warnings, page_state = self._build_post_pages(
                    row, staging, current_site, old_state
                )
                posts.append(item)
                rendered += page_rendered
                reused += page_reused
                warnings.extend(page_warnings)
                state_pages.update(page_state)

            with self.db.connect() as db:
                card_rows = list(db.execute(
                    "SELECT * FROM fancard_versions WHERE status='completed' "
                    "ORDER BY creator_id,target_month,version_number"
                ))
            grouped_cards: dict[tuple[str, str], list] = {}
            for row in card_rows:
                grouped_cards.setdefault((str(row["creator_id"]), str(row["target_month"])), []).append(row)
            for key, rows in grouped_cards.items():
                item, page_rendered, page_reused, page_warnings, page_state = self._build_fancard_pages(
                    key, rows, staging, current_site, old_state
                )
                fancards.append(item)
                rendered += page_rendered
                reused += page_reused
                warnings.extend(page_warnings)
                state_pages.update(page_state)

            creator_cards: dict[str, int] = {}
            for item in fancards:
                creator_cards[item["creator_id"]] = creator_cards.get(item["creator_id"], 0) + 1
            for creator in creators:
                creator["fancard_months"] = creator_cards.get(creator["creator_id"], 0)

            stats = {
                "creators": len(creators),
                "posts": len(posts),
                "versions": sum(item["version_count"] for item in posts),
                "fancards": len(fancards),
                "issues": sum(item["status"] != "completed" for item in posts) + len(warnings),
            }
            built_at = datetime.now(UTC).isoformat()
            data = {
                "schema": 1,
                "template_version": TEMPLATE_VERSION,
                "built_at": built_at,
                "stats": stats,
                "creators": creators,
                "posts": posts,
                "fancards": fancards,
                "warnings": warnings,
            }
            data_text = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
            BackupStorage.atomic_write_text(
                staging / "data.js", f"window.__FANBOX_ARCHIVE_DATA__={data_text};\n"
            )
            build_info = {
                "schema": 1,
                "template_version": TEMPLATE_VERSION,
                "built_at": built_at,
                "stats": stats,
                "warnings": len(warnings),
            }
            self._write_json(staging / "build.json", build_info)
            page_hashes = {
                relative: sha256_file(confined_path(staging, Path(relative)))
                for relative in state_pages
            }
            self._write_json(staging / "state.json", {
                "schema": 1,
                "template_version": TEMPLATE_VERSION,
                "pages": state_pages,
                "hashes": page_hashes,
            })
            self._validate_staging(staging, state_pages)
            BackupStorage.publish_version(staging, current_site)
            BackupStorage.atomic_write_text(self.root / "index.html", self._index_html(creators, posts))
            return IndexBuildResult(rendered, reused, warnings, self.root / "index.html")
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    def check(self) -> list[str]:
        issues: list[str] = []
        site = self.root / "_site"
        for path in (self.root / "index.html", site / "data.js", site / "build.json", site / "state.json",
                     site / "assets/app.css", site / "assets/app.js",
                     site / "assets/design-tokens.css"):
            if not path.is_file():
                issues.append(f"缺少索引檔案：{path}")
        state = self._read_json(site / "state.json")
        for relative in (state.get("pages") or {}):
            try:
                path = confined_path(site, Path(relative))
            except ValueError:
                issues.append(f"索引狀態含不安全路徑：{relative}")
                continue
            if not path.is_file():
                issues.append(f"缺少閱讀頁：{relative}")
                continue
            expected = (state.get("hashes") or {}).get(relative)
            if expected and sha256_file(path) != expected:
                issues.append(f"閱讀頁雜湊不符：{relative}")
            issues.extend(self._check_links(path))
        if (self.root / "index.html").is_file():
            issues.extend(self._check_links(self.root / "index.html"))
        return issues

    def _creator_data(self) -> list[dict]:
        result: list[dict] = []
        for row in self.db.creator_listing(supporting_only=False):
            icon = Path(str(row["icon_path"] or ""))
            result.append({
                "creator_id": row["creator_id"],
                "name": row["name"],
                "url": row["url"],
                "post_count": row["post_count"],
                "completed_count": row["completed_count"],
                "last_sync": row["last_sync"],
                "status": row["status"],
                "avatar": self._relative_url(self.root / "index.html", icon) if icon.is_file() else None,
                "fancard_months": 0,
                "profile_version_count": 0,
                "profile_latest_path": None,
            })
        return result

    def _build_profile_pages(
        self, creator: dict, staging: Path, current: Path, old_state: dict,
    ) -> tuple[int, int, list[str], dict[str, str]]:
        creator_id = str(creator["creator_id"])
        versions = self.db.profile_versions(creator_id)
        creator["profile_version_count"] = len(versions)
        rendered = reused = 0
        warnings: list[str] = []
        state: dict[str, str] = {}
        completed_pages: list[tuple[int, str]] = []
        safe_creator = safe_filename(creator_id, fallback="unknown")
        for version in versions:
            number = int(version["version_number"])
            relative = f"creators/{safe_creator}/profile/v{number:04d}.html"
            source_json = Path(str(version["json_path"] or ""))
            manifest = Path(str(version["local_path"])) / "manifest.json"
            manifest_hash = sha256_file(manifest) if manifest.is_file() else "missing"
            fingerprint = (
                f"profile:{version['content_fingerprint']}:{manifest_hash}:"
                f"{version['status']}:{TEMPLATE_VERSION}"
            )
            if not source_json.is_file():
                warnings.append(f"Creator Profile {creator_id} v{number:04d} 缺少 profile.json")
                continue
            try:
                profile = CreatorProfile.model_validate_json(source_json.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                warnings.append(f"Creator Profile {creator_id} v{number:04d} 無法讀取：{exc}")
                continue
            destination = confined_path(staging, Path(relative))
            if self._reuse_page(relative, fingerprint, current, old_state, destination):
                reused += 1
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                BackupStorage.atomic_write_text(
                    destination, self._profile_html(profile, version, destination, versions)
                )
                rendered += 1
            state[relative] = fingerprint
            if version["status"] == "completed":
                completed_pages.append((number, relative))
        if completed_pages:
            _, latest_relative = max(completed_pages)
            latest_out = f"creators/{safe_creator}/profile/latest.html"
            latest_destination = confined_path(staging, Path(latest_out))
            latest_destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(confined_path(staging, Path(latest_relative)), latest_destination)
            state[latest_out] = state[latest_relative]
            creator["profile_latest_path"] = f"_site/{latest_out}"
        return rendered, reused, warnings, state

    def _build_post_pages(self, row, staging: Path, current: Path, old_state: dict):
        post_id = str(row["post_id"])
        versions = self.db.version_rows(post_id)
        item = {
            "post_id": post_id,
            "creator_id": str(row["creator_id"]),
            "title": str(row["title"]),
            "published_at": row["published_at"],
            "updated_at": row["updated_at"],
            "status": str(row["status"]),
            "tags": [],
            "fee_required": None,
            "version_count": len(versions),
            "latest_path": None,
            "cover": None,
            "url": f"https://www.fanbox.cc/@{row['creator_id']}/posts/{post_id}",
            "versions": [],
        }
        rendered = reused = 0
        warnings: list[str] = []
        state: dict[str, str] = {}
        completed_pages: list[tuple[int, str]] = []
        for version in versions:
            number = int(version["version_number"])
            relative = f"posts/{post_id}/v{number:04d}.html"
            source_json = Path(str(version["json_path"] or ""))
            manifest = Path(str(version["local_path"])) / "manifest.json"
            manifest_hash = sha256_file(manifest) if manifest.is_file() else "missing"
            fingerprint = f"post:{version['content_fingerprint']}:{manifest_hash}:{version['status']}:{TEMPLATE_VERSION}"
            item["versions"].append({
                "number": number,
                "captured_at": version["captured_at"],
                "remote_updated_at": version["remote_updated_at"],
                "status": version["status"],
                "path": f"_site/{relative}",
            })
            if not source_json.is_file():
                warnings.append(f"Post {post_id} v{number:04d} 缺少 post.json")
                continue
            post = Post.model_validate_json(source_json.read_text(encoding="utf-8"))
            if not item["tags"]:
                item["tags"] = post.tags
                item["fee_required"] = post.fee_required
                item["url"] = post.url
            if post.cover and post.cover.local_path:
                cover = confined_path(Path(str(version["local_path"])), Path(post.cover.local_path))
                if cover.is_file():
                    item["cover"] = self._relative_url(self.root / "index.html", cover)
            destination = confined_path(staging, Path(relative))
            if self._reuse_page(relative, fingerprint, current, old_state, destination):
                reused += 1
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                BackupStorage.atomic_write_text(
                    destination, self._post_html(post, version, destination, versions)
                )
                rendered += 1
            state[relative] = fingerprint
            if version["status"] == "completed":
                completed_pages.append((number, relative))
        if completed_pages:
            _, latest_relative = max(completed_pages)
            latest_out = f"posts/{post_id}/latest.html"
            latest_destination = confined_path(staging, Path(latest_out))
            latest_destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(confined_path(staging, Path(latest_relative)), latest_destination)
            state[latest_out] = state[latest_relative]
            item["latest_path"] = f"_site/{latest_out}"
        elif versions:
            warnings.append(f"Post {post_id} 沒有完成版本")
        else:
            warnings.append(f"Post {post_id} 沒有版本紀錄")
        return item, rendered, reused, warnings, state

    def _build_fancard_pages(self, key, rows, staging: Path, current: Path, old_state: dict):
        creator_id, month = key
        item = {
            "creator_id": creator_id,
            "target_month": month,
            "plan_title": "",
            "fee": None,
            "version_count": len(rows),
            "latest_path": None,
            "thumbnail": None,
            "versions": [],
        }
        rendered = reused = 0
        warnings: list[str] = []
        state: dict[str, str] = {}
        for row in rows:
            number = int(row["version_number"])
            relative = f"fancards/{quote(creator_id, safe='')}/{month}/v{number:04d}.html"
            manifest = Path(str(row["local_path"])) / "manifest.json"
            manifest_hash = sha256_file(manifest) if manifest.is_file() else "missing"
            fingerprint = f"card:{row['content_fingerprint']}:{manifest_hash}:{TEMPLATE_VERSION}"
            destination = confined_path(staging, Path(relative))
            source = Path(str(row["local_path"]))
            metadata = source / "fancard.json"
            if not metadata.is_file():
                warnings.append(f"Fan Card {creator_id}/{month}/v{number:04d} 缺少 fancard.json")
                continue
            payload = json.loads(metadata.read_text(encoding="utf-8"))
            body = payload.get("body") or {}
            plan = body.get("plan") or {}
            image_path = Path(str(row["image_path"] or ""))
            if not item["plan_title"]:
                item["plan_title"] = str(plan.get("title") or "")
                item["fee"] = plan.get("fee")
            if self._reuse_page(relative, fingerprint, current, old_state, destination):
                reused += 1
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                BackupStorage.atomic_write_text(
                    destination, self._fancard_html(body, row, destination, image_path, rows)
                )
                rendered += 1
            state[relative] = fingerprint
            item["versions"].append({"number": number, "path": f"_site/{relative}"})
            item["latest_path"] = f"_site/{relative}"
            if image_path.is_file():
                item["thumbnail"] = self._relative_url(self.root / "index.html", image_path)
        if item["latest_path"]:
            latest_relative = item["latest_path"].removeprefix("_site/")
            latest_out = f"fancards/{quote(creator_id, safe='')}/{month}/latest.html"
            target = confined_path(staging, Path(latest_out))
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(confined_path(staging, Path(latest_relative)), target)
            state[latest_out] = state[latest_relative]
            item["latest_path"] = f"_site/{latest_out}"
        return item, rendered, reused, warnings, state

    def _reuse_page(self, relative: str, fingerprint: str, current: Path, old_state: dict, destination: Path) -> bool:
        if old_state.get("template_version") != TEMPLATE_VERSION:
            return False
        if (old_state.get("pages") or {}).get(relative) != fingerprint:
            return False
        source = confined_path(current, Path(relative))
        if not source.is_file():
            return False
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        return True

    def _post_html(self, post: Post, version, output: Path, all_versions) -> str:
        version_root = Path(str(version["local_path"]))
        blocks: list[str] = []
        if post.cover and post.cover.local_path:
            cover = confined_path(version_root, Path(post.cover.local_path))
            if cover.is_file():
                cover_url = self._relative_url(output, cover)
                blocks.append(
                    f'<figure class="post-cover"><a href="{cover_url}">'
                    f'<img src="{cover_url}" alt="文章封面"></a></figure>'
                )
        assets = {asset.asset_id: asset for asset in post.assets}
        for block in post.blocks:
            text = self._styled_text(block.text or "", block.styles)
            if block.type == "paragraph" and text:
                blocks.append(f"<p>{text.replace(chr(10), '<br>')}</p>")
            elif block.type == "heading" and text:
                level = min(max(block.level or 2, 2), 6)
                blocks.append(f"<h{level}>{text}</h{level}>")
            elif block.type == "quote" and text:
                blocks.append(f"<blockquote>{text.replace(chr(10), '<br>')}</blockquote>")
            elif block.type == "separator":
                blocks.append("<hr>")
            elif block.type in {"image", "file"}:
                asset = assets.get(block.asset_id or "")
                if asset and asset.local_path:
                    source = confined_path(version_root, Path(asset.local_path))
                    href = self._relative_url(output, source)
                    if block.type == "image":
                        blocks.append(f'<figure><a href="{href}"><img loading="lazy" src="{href}" alt="圖片"></a></figure>')
                    else:
                        label = html.escape(block.name or asset.original_name or "下載附件")
                        blocks.append(f'<p class="attachment"><a href="{href}">{label}</a></p>')
            elif block.type == "embed":
                embed = self._embed_html(post, block, assets, version_root, output)
                if embed:
                    blocks.append(embed)
            elif block.type == "raw":
                blocks.append('<p class="notice">無法解析的內容區塊；完整資料請見 post.json。</p>')
        number = int(version["version_number"])
        nav = self._version_nav(all_versions, number, output, "posts", post.post_id)
        neighbors = getattr(self, "_post_neighbors", {}).get(post.post_id, {})
        previous_id = neighbors.get("previous")
        next_id = neighbors.get("next")
        post_nav = '<nav class="post-navigation" aria-label="投稿導覽">'
        post_nav += (
            f'<a href="../{html.escape(str(previous_id), quote=True)}/latest.html">← 上一篇</a>'
            if previous_id else '<span></span>'
        )
        if neighbors:
            post_nav += (
                f'<span>{int(neighbors["position"])} / {int(neighbors["total"])}</span>'
            )
        post_nav += (
            f'<a href="../{html.escape(str(next_id), quote=True)}/latest.html">下一篇 →</a>'
            if next_id else '<span></span>'
        )
        post_nav += "</nav>"
        source_url = html.escape(post.url, quote=True) if self._safe_https(post.url) else "#"
        body = "".join(blocks) or '<p class="empty">此版本沒有可顯示的正文。</p>'
        return self._reader_shell(
            title=post.title,
            eyebrow=f"{post.creator_name} · Post {post.post_id}",
            metadata=(f"發布 {self._date(post.published_at)} · 更新 {self._date(post.updated_at)} · "
                      f"{self._fee_label(post.fee_required)} · v{number:04d}"),
            body=body,
            navigation=post_nav + nav,
            actions=f'<a rel="noreferrer noopener" href="{source_url}">開啟 FANBOX 原文</a>',
            asset_prefix="../../assets",
        )

    def _profile_html(self, profile: CreatorProfile, version, output: Path, all_versions) -> str:
        version_root = Path(str(version["local_path"]))
        blocks: list[str] = []
        cover_path = Path(str(version["cover_path"] or ""))
        if cover_path.is_file():
            cover_url = self._relative_url(output, cover_path)
            blocks.append(
                f'<figure class="profile-cover"><a href="{cover_url}">'
                f'<img src="{cover_url}" alt="Creator Profile 封面"></a></figure>'
            )
        description = html.escape(profile.description).replace("\n", "<br>")
        blocks.append(
            '<section class="profile-about"><h2>關於創作者</h2>'
            f'<p>{description or "尚無自我介紹。"}</p></section>'
        )
        if profile.profile_items:
            items: list[str] = []
            for item in profile.profile_items:
                image = ""
                if item.image_path:
                    source = confined_path(version_root, Path(item.image_path))
                    if source.is_file():
                        image_url = self._relative_url(output, source)
                        image = f'<img loading="lazy" src="{image_url}" alt="">'
                label = html.escape(item.label or item.type or "Profile 項目")
                item_description = html.escape(item.description).replace("\n", "<br>")
                content = f"<strong>{label}</strong>"
                if item_description:
                    content += f"<p>{item_description}</p>"
                if item.url and self._safe_https(item.url):
                    content = (
                        f'<a rel="noreferrer noopener" href="{html.escape(item.url, quote=True)}">'
                        f"{content}</a>"
                    )
                items.append(f'<li class="profile-item">{image}<div>{content}</div></li>')
            blocks.append(
                '<section class="profile-links"><h2>公開連結與項目</h2>'
                f'<ul>{"".join(items)}</ul></section>'
            )
        flags = [
            "接受委託" if profile.is_accepting_request else "未開放委託",
            "已停止活動" if profile.is_stopped else "持續活動",
        ]
        if profile.has_adult_content:
            flags.append("包含成人內容")
        blocks.append(
            '<section class="profile-flags" aria-label="Profile 狀態">'
            + "".join(f'<span class="badge">{html.escape(flag)}</span>' for flag in flags)
            + "</section>"
        )
        number = int(version["version_number"])
        nav = self._version_nav(all_versions, number, output, "profiles", profile.creator_id)
        source_url = html.escape(profile.fanbox_url, quote=True) if self._safe_https(profile.fanbox_url) else "#"
        return self._reader_shell(
            title=profile.name,
            eyebrow=f"{profile.creator_id} · Creator Profile",
            metadata=f"保存 {self._date(version['captured_at'])} · v{number:04d}",
            body="".join(blocks), navigation=nav,
            actions=f'<a rel="noreferrer noopener" href="{source_url}">開啟 FANBOX Profile</a>',
            asset_prefix="../../../assets",
        )

    def _embed_html(self, post: Post, block, assets: dict, version_root: Path, output: Path) -> str:
        """Render a safe offline card for FANBOX url_embed blocks.

        Older archives stored only ``urlEmbedId`` on the content block.  Resolve
        those IDs from the untouched API response so rebuilding the index repairs
        existing backups without another network request.
        """
        raw = block.raw if isinstance(block.raw, dict) else {}
        embed_id = str(raw.get("urlEmbedId") or "")
        embed = raw.get("embed") if isinstance(raw.get("embed"), dict) else None
        if embed is None:
            body = post.raw.get("body") if isinstance(post.raw, dict) else None
            embed_map = body.get("urlEmbedMap") if isinstance(body, dict) else None
            candidate = embed_map.get(embed_id) if isinstance(embed_map, dict) else None
            embed = candidate if isinstance(candidate, dict) else {}

        kind = str(embed.get("type") or "")
        url = str(block.url or "")
        title = str(block.name or "")
        excerpt = str(block.text or "")
        creator = ""
        fee: int | None = None
        eyebrow = "外部連結"
        local_post_id = ""

        if kind == "fanbox.post":
            info = embed.get("postInfo") if isinstance(embed.get("postInfo"), dict) else {}
            creator_id = str(info.get("creatorId") or "")
            post_id = str(info.get("id") or "")
            local_post_id = post_id
            if not self._safe_https(url) and creator_id and post_id:
                url = f"https://www.fanbox.cc/@{creator_id}/posts/{post_id}"
            title = title or str(info.get("title") or "FANBOX Post")
            excerpt = excerpt or str(info.get("excerpt") or "")
            user = info.get("user") if isinstance(info.get("user"), dict) else {}
            creator = str(user.get("name") or creator_id)
            raw_fee = info.get("feeRequired")
            if isinstance(raw_fee, int):
                fee = raw_fee
            eyebrow = "FANBOX Post"
        elif kind == "default":
            url = str(embed.get("url") or url)
            title = title or str(embed.get("host") or "外部連結")
        elif kind == "html.card":
            if not self._safe_https(url):
                match = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', str(embed.get("html") or ""), re.I)
                url = match.group(1) if match else ""
            title = title or "外部連結"

        if not self._safe_https(url):
            return '<p class="notice">此外部連結無法安全還原；完整資料請見 post.json。</p>'

        href = url
        if local_post_id and local_post_id in getattr(self, "_readable_post_ids", set()):
            site_root = output.parents[2]
            local_page = confined_path(site_root, Path("posts") / local_post_id / "latest.html")
            href = self._relative_url(output, local_page)
            eyebrow = "FANBOX Post · 本機備份"

        preview = ""
        asset = assets.get(block.asset_id or "")
        if asset and asset.local_path:
            source = confined_path(version_root, Path(asset.local_path))
            if source.is_file():
                src = self._relative_url(output, source)
                preview = f'<img class="embed-card-image" loading="lazy" src="{src}" alt="">'

        meta = ""
        if creator:
            meta += f'<span>{html.escape(creator)}</span>'
        if fee is not None:
            meta += f'<span class="embed-card-fee">{html.escape(self._fee_label(fee))}</span>'
        description = f'<p>{html.escape(excerpt)}</p>' if excerpt else ""
        return (
            f'<a class="embed-card" rel="noreferrer noopener" href="{html.escape(href, quote=True)}">'
            f'<span class="embed-card-content"><span class="embed-card-eyebrow">{eyebrow}</span>'
            f'<strong>{html.escape(title or url)}</strong>{description}'
            f'<span class="embed-card-meta">{meta}</span></span>{preview}</a>'
        )

    def _fancard_html(self, body: dict, row, output: Path, image_path: Path, all_versions) -> str:
        plan = body.get("plan") or {}
        user = plan.get("user") or {}
        image_url = self._relative_url(output, image_path) if image_path.is_file() else ""
        if image_url:
            image = f'<a class="card-image" href="{image_url}"><img src="{image_url}" alt="Fan Card 原始卡面"></a>'
        elif body.get("supporterCardImageUrl"):
            image = '<p class="notice">卡面圖片遺失。</p>'
        else:
            image = '<p class="notice">本月未提供 Fan Card 卡面。</p>'
        description = html.escape(str(plan.get("description") or "（無）"))
        months = "".join(
            f"<li>{html.escape(str(item.get('targetMonth') or ''))} · ¥{html.escape(str(item.get('paidAmount') or ''))}</li>"
            for item in body.get("supportTransactions") or [] if isinstance(item, dict)
        )
        number = int(row["version_number"])
        nav = self._version_nav(all_versions, number, output, "fancards", f"{row['creator_id']}/{row['target_month']}")
        content = f"""
        <div class="fancard-layout">{image}<dl>
          <div><dt>創作者</dt><dd>{html.escape(str(user.get('name') or row['creator_id']))}</dd></div>
          <div><dt>方案</dt><dd>{html.escape(str(plan.get('title') or ''))}</dd></div>
          <div><dt>金額</dt><dd>¥{html.escape(str(plan.get('fee') or 0))}/月</dd></div>
          <div><dt>支援開始</dt><dd>{html.escape(self._date(body.get('supportStartDatetime')))}</dd></div>
        </dl></div>
        <section><h2>方案資訊</h2><div class="secret-text">{description}</div></section>
        <section><h2>支援月份</h2><ul>{months}</ul></section>
        """
        return self._reader_shell(
            title=f"Fan Card — {row['target_month']}",
            eyebrow=f"{user.get('name') or row['creator_id']} · Fan Card",
            metadata=f"{row['target_month']} · v{number:04d}", body=content,
            navigation=nav, actions="", asset_prefix="../../../assets",
        )

    def _version_nav(self, versions, current: int, output: Path, kind: str, identity: str) -> str:
        rows = sorted(versions, key=lambda row: int(row["version_number"]))
        numbers = [int(row["version_number"]) for row in rows]
        parts = ['<nav class="version-nav" aria-label="版本導覽">']
        if current in numbers and numbers.index(current) > 0:
            previous = numbers[numbers.index(current) - 1]
            parts.append(f'<a href="v{previous:04d}.html">← v{previous:04d}</a>')
        parts.append(f"<span>v{current:04d}</span>")
        if current in numbers and numbers.index(current) < len(numbers) - 1:
            following = numbers[numbers.index(current) + 1]
            parts.append(f'<a href="v{following:04d}.html">v{following:04d} →</a>')
        parts.append("</nav>")
        return "".join(parts)

    @staticmethod
    def _reader_shell(*, title: str, eyebrow: str, metadata: str, body: str,
                      navigation: str, actions: str, asset_prefix: str) -> str:
        return f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'self' data:; img-src 'self' data: file:; style-src 'self'; script-src 'self'; object-src 'none'; frame-src 'none'; connect-src 'none'; form-action 'none'">
<link rel="icon" href="data:,"><title>{html.escape(title)} · FANBOX Archive</title><script src="{asset_prefix}/theme.js"></script><link rel="stylesheet" href="{asset_prefix}/app.css"><link rel="stylesheet" href="{asset_prefix}/design-tokens.css"></head>
<body class="reader-page"><header class="reader-header"><a href="{asset_prefix}/../../index.html">← 回到索引</a><div class="reader-header-actions"><span>私人本機備份</span><button class="icon-button" type="button" data-theme-toggle>◐</button></div></header>
<main class="reader"><p class="eyebrow">{html.escape(eyebrow)}</p><h1>{html.escape(title)}</h1>
<p class="metadata">{html.escape(metadata)}</p>{navigation}<div class="reader-actions">{actions}</div>
<article>{body}</article><footer>此頁為本機備份，不代表遠端目前狀態。</footer></main></body></html>"""

    @staticmethod
    def _index_html(creators: list[dict], posts: list[dict]) -> str:
        fallback = "".join(
            f'<li><a href="{html.escape(str(item["latest_path"] or "#"), quote=True)}">{html.escape(item["title"])}</a> — {html.escape(item["creator_id"])}</li>'
            for item in posts[:100]
        )
        return f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'self' data:; img-src 'self' data: file:; style-src 'self'; script-src 'self'; object-src 'none'; frame-src 'none'; connect-src 'none'; form-action 'none'">
<meta name="color-scheme" content="light dark"><title>FANBOX Archive</title>
<link rel="icon" href="data:,"><script src="_site/assets/theme.js"></script><link rel="stylesheet" href="_site/assets/app.css"><link rel="stylesheet" href="_site/assets/design-tokens.css"></head><body>
<div id="app"><header class="topbar"><strong>FANBOX Archive</strong><span>正在載入本機索引…</span></header>
<noscript><main class="noscript"><h1>本機備份</h1><p>JavaScript 已停用，以下顯示最近文章。</p><ul>{fallback}</ul></main></noscript></div>
<script src="_site/data.js"></script><script src="_site/assets/app.js"></script></body></html>"""

    def _validate_staging(self, staging: Path, pages: dict[str, str]) -> None:
        for required in ("assets/app.css", "assets/app.js", "assets/theme.js",
                         "assets/design-tokens.css", "data.js", "build.json", "state.json"):
            if not confined_path(staging, Path(required)).is_file():
                raise ValueError(f"索引建置缺少必要檔案：{required}")
        for relative in pages:
            if not confined_path(staging, Path(relative)).is_file():
                raise ValueError(f"索引建置缺少閱讀頁：{relative}")

    def _check_links(self, document: Path) -> list[str]:
        issues: list[str] = []
        text = document.read_text(encoding="utf-8")
        for raw in re.findall(r'(?:href|src)="([^"]+)"', text):
            if not raw or raw.startswith("#") or urlparse(raw).scheme in {"https", "data"}:
                continue
            local = (document.parent / Path(unquote(raw.split("#", 1)[0]))).resolve()
            try:
                local.relative_to(self.root)
            except ValueError:
                issues.append(f"連結超出備份根目錄：{document.name} → {raw}")
                continue
            if not local.is_file():
                issues.append(f"破損連結：{document.name} → {raw}")
        return issues

    @staticmethod
    def _relative_url(from_file: Path, to_file: Path) -> str:
        relative = Path(os.path.relpath(to_file.resolve(), from_file.resolve().parent))
        return "/".join(quote(part) if part not in {"..", "."} else part for part in relative.parts)

    @staticmethod
    def _safe_https(value: str) -> bool:
        parsed = urlparse(value)
        return parsed.scheme == "https" and bool(parsed.hostname)

    @staticmethod
    def _date(value) -> str:
        if not value:
            return "-"
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return value
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(TAIPEI).strftime("%Y年%m月%d日 %H:%M")

    @staticmethod
    def _fee_label(value: int | None) -> str:
        if value is None:
            return "檔位未知"
        if value <= 0:
            return "全體公開"
        return f"¥{value:,}"

    @staticmethod
    def _styled_text(value: str, styles) -> str:
        parts: list[str] = []
        cursor = 0
        for style in sorted(styles, key=lambda item: (item.offset, item.length)):
            start = max(cursor, min(len(value), style.offset))
            end = max(start, min(len(value), style.offset + style.length))
            if start < cursor or end <= start:
                continue
            parts.append(html.escape(value[cursor:start]))
            parts.append(f"<strong>{html.escape(value[start:end])}</strong>")
            cursor = end
        parts.append(html.escape(value[cursor:]))
        return "".join(parts)

    @staticmethod
    def _read_json(path: Path) -> dict:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    @staticmethod
    def _write_json(path: Path, value: object) -> None:
        BackupStorage.atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")
