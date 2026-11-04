from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from .config import AppConfig
from .database import Database, now_iso
from .downloader import (
    AssetDownloader, DownloadAuthorizationError, DownloadError,
    DownloadRateLimitedError, sha256_file,
)
from .fancard_perks import normalize_fancard_perks
from .markdown import render_markdown
from .models import Asset, AssetStatus, CreatorProfile, Post, PostStatus, VerificationIssue
from .security import confined_path, safe_filename, validate_url
from .storage import BackupStorage
from .timestamps import fanbox_month, isoformat_display
from .logging_setup import get_logger


class ArchiveService:
    def __init__(self, config: AppConfig, *, cookie: str = "", user_agent: str | None = None):
        self.config = config
        self.cookie = cookie
        self.user_agent = user_agent
        self.progress_callback: Callable[[object, int, int | None], None] | None = None
        self.storage = BackupStorage(config.storage.output_dir)
        self.db = Database(config.storage.database)
        self._migrate_legacy_versions()

    def save(self, post: Post, *, download_assets: bool = True, force: bool = False) -> PostStatus:
        self.storage.assign_asset_paths(post)
        post_dir = self.storage.prepare(post)
        previous = self.db.post_row(post.post_id)
        if (not force and self.config.sync.skip_completed and previous
                and previous["status"] == PostStatus.COMPLETED.value
                and previous["content_fingerprint"] == post.content_fingerprint
                and self._assets_intact(post)):
            self.db.set_post_pinned(post.post_id, bool(post.raw.get("isPinned", False)))
            return PostStatus.COMPLETED

        # Carry verified metadata forward for unchanged URLs, so an edited post
        # downloads only new or changed assets.
        if not force:
            for asset in [*post.assets, *([post.cover] if post.cover else [])]:
                old = self.db.asset_row(post.post_id, asset.asset_id, asset.url)
                if not old:
                    continue
                asset.local_path = old["local_path"] or asset.local_path
                asset.size = old["size"]
                asset.sha256 = old["sha256"]
                asset.etag = old["etag"]
                asset.last_modified = old["last_modified"]
                try:
                    asset.status = AssetStatus(str(old["status"]))
                except ValueError:
                    asset.status = AssetStatus.PENDING

        latest = self.db.latest_version(post.post_id, completed_only=True)
        latest_number = int(latest["version_number"]) if latest else 0
        retry_version = self.db.retryable_version_by_fingerprint(
            post.post_id, post.content_fingerprint or "", after_version=latest_number,
        )
        newest = self.db.latest_version(post.post_id)
        version_number = (int(retry_version["version_number"]) if retry_version
                          else (int(newest["version_number"]) + 1 if newest else 1))
        temp_dir, version_dir = self.storage.prepare_version(post, version_number)
        self.db.upsert_post(post, str(post_dir), PostStatus.DOWNLOADING)
        version_id = self.db.begin_version(post, version_number, str(version_dir))
        failures = 0
        try:
            if download_assets:
                settings = self.config.download
                with AssetDownloader(cookie=self.cookie, timeout=settings.timeout_seconds,
                                     retries=settings.retry_count,
                                     interval=settings.request_interval_seconds,
                                     resume=settings.resume,
                                     user_agent=self.user_agent,
                                     progress=self.progress_callback) as downloader:
                    selected = list(post.assets)
                    if post.cover and settings.download_cover:
                        selected.append(post.cover)
                    for asset in selected:
                        if asset.type == "image" and not settings.original_images:
                            continue
                        if asset.type == "file" and not settings.download_attachments:
                            continue
                        target = self.storage.absolute_asset_path(post, asset, base=temp_dir)
                        candidates = []
                        if retry_version:
                            candidates.append(self.storage.absolute_asset_path(
                                post, asset, base=Path(str(retry_version["local_path"])))
                            )
                        candidates.append(self.storage.absolute_asset_path(post, asset))
                        reusable = next((path for path in candidates if path.exists()), None)
                        if (reusable and asset.status == AssetStatus.COMPLETED
                                and asset.sha256 and sha256_file(reusable) == asset.sha256):
                            self.storage.link_or_copy(reusable, target)
                            continue
                        if retry_version:
                            partial = candidates[0].with_name(candidates[0].name + ".part")
                            if partial.exists():
                                self.storage.link_or_copy(partial, target.with_name(target.name + ".part"))
                        try:
                            downloader.download(asset, target)
                        except (DownloadAuthorizationError, DownloadRateLimitedError):
                            raise
                        except DownloadError:
                            failures += 1
                        finally:
                            self.db.set_asset(post.post_id, asset)
                    if post.creator_icon_url:
                        self._save_creator_icon(post, downloader)

            captured_at = now_iso()
            self._write_json(temp_dir / "post.json", post.model_dump(mode="json"))
            if self.config.markdown.enabled:
                previous_link = f"../v{version_number - 1:04d}/post.md" if version_number > 1 else None
                self.storage.atomic_write_text(
                    temp_dir / "post.md",
                    render_markdown(post, archive_version=version_number, captured_at=captured_at,
                                    previous_version=previous_link),
                )
            status = PostStatus.PARTIAL if failures else PostStatus.COMPLETED
            if not download_assets and (post.assets or post.cover):
                status = PostStatus.PENDING
            self._write_manifest(temp_dir, post, version_number, captured_at, status, latest)
            self.storage.publish_version(temp_dir, version_dir)
            error = f"{failures} 個資源失敗" if failures else None
            if status == PostStatus.COMPLETED:
                self.storage.update_latest_alias(post, version_dir)
                if self.config.markdown.enabled:
                    root_previous = f"versions/v{version_number - 1:04d}/post.md" if version_number > 1 else None
                    self.storage.atomic_write_text(
                        post_dir / "post.md",
                        render_markdown(post, archive_version=version_number, captured_at=captured_at,
                                        previous_version=root_previous),
                    )
                    self._update_previous_navigation(latest, version_number)
            self.db.finish_version(
                version_id, status=status, markdown_path=str(version_dir / "post.md"),
                json_path=str(version_dir / "post.json"), captured_at=captured_at, error=error,
                make_latest=status == PostStatus.COMPLETED,
            )
            self.db.set_post_status(post.post_id, status, error)
            return status
        except BaseException as exc:
            failed_at = now_iso()
            if temp_dir.exists():
                try:
                    self._write_json(temp_dir / "post.json", post.model_dump(mode="json"))
                    if self.config.markdown.enabled:
                        self.storage.atomic_write_text(
                            temp_dir / "post.md",
                            render_markdown(
                                post, archive_version=version_number, captured_at=failed_at,
                                previous_version=(f"../v{version_number - 1:04d}/post.md"
                                                  if version_number > 1 else None),
                            ),
                        )
                    self._write_manifest(
                        temp_dir, post, version_number, failed_at, PostStatus.FAILED, latest
                    )
                    self.storage.publish_version(temp_dir, version_dir)
                except BaseException:
                    # Keep the temporary directory and .part files for diagnosis
                    # and a future safe retry if even publishing the failed state fails.
                    pass
            self.db.finish_version(
                version_id, status=PostStatus.FAILED,
                markdown_path=str(version_dir / "post.md"), json_path=str(version_dir / "post.json"),
                captured_at=failed_at, error=str(exc),
            )
            self.db.set_post_status(post.post_id, PostStatus.FAILED, str(exc))
            raise

    def _save_creator_icon(self, post: Post, downloader: AssetDownloader) -> None:
        row = self.db.creator_row(post.creator_id)
        existing = Path(str(row["icon_path"])) if row and row["icon_path"] else None
        if (row and row["icon_url"] == post.creator_icon_url and existing and existing.is_file()
                and row["icon_sha256"] and sha256_file(existing) == row["icon_sha256"]):
            return
        suffix = Path(urlparse(post.creator_icon_url).path).suffix.lower() or ".img"
        if suffix not in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
            suffix = ".img"
        target = confined_path(
            self.config.storage.output_dir,
            Path(safe_filename(post.creator_id)) / f"creator-avatar{suffix}",
        )
        avatar = Asset(
            asset_id="creator-avatar", type="image", url=post.creator_icon_url,
            original_name=target.name, local_path=target.name,
        )
        try:
            downloader.download(avatar, target)
        except (DownloadAuthorizationError, DownloadRateLimitedError):
            raise
        except DownloadError as exc:
            get_logger().warning("creator avatar download failed creator_id=%s: %s", post.creator_id, exc)
            return
        if avatar.sha256:
            self.db.set_creator_icon(post.creator_id, post.creator_icon_url, str(target), avatar.sha256)

    def clear_posts(self) -> int:
        root = self.config.storage.output_dir.resolve()
        paths: list[Path] = []
        for raw in self.db.post_local_paths():
            path = Path(raw).resolve()
            try:
                relative = path.relative_to(root)
            except ValueError as exc:
                raise ValueError(f"Post 路徑超出備份根目錄：{path}") from exc
            if len(relative.parts) != 2 or "fancards" in {part.casefold() for part in relative.parts}:
                raise ValueError(f"拒絕清除非標準 Post 路徑：{path}")
            paths.append(path)

        staging = confined_path(root, Path(f".post-purge-{uuid.uuid4().hex}.tmp"))
        moved: list[tuple[Path, Path]] = []
        try:
            for source in paths:
                if not source.exists():
                    continue
                relative = source.relative_to(root)
                destination = confined_path(staging, relative)
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(source, destination)
                moved.append((source, destination))
            count = self.db.clear_post_records()
        except BaseException:
            for source, destination in reversed(moved):
                if destination.exists() and not source.exists():
                    source.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(destination, source)
            shutil.rmtree(staging, ignore_errors=True)
            raise
        if staging.exists():
            shutil.rmtree(staging)
        return count

    def profile_status(self, profile: CreatorProfile) -> str:
        latest = self.db.latest_profile_version(profile.creator_id)
        if latest is None:
            return "new"
        if str(latest["content_fingerprint"]) != profile.content_fingerprint:
            return "updated"
        if latest["cover_path"]:
            cover = Path(str(latest["cover_path"]))
            if not cover.is_file() or not latest["cover_sha256"]:
                return "updated"
            if sha256_file(cover) != str(latest["cover_sha256"]):
                return "updated"
        if not self._profile_item_images_intact(latest):
            return "updated"
        return "unchanged"

    def save_profile(self, profile: CreatorProfile) -> tuple[str, Path]:
        latest = self.db.latest_profile_version(profile.creator_id)
        status = self.profile_status(profile)
        if status == "unchanged" and latest is not None:
            root = self._profile_root(profile.creator_id)
            self._update_profile_aliases(root, Path(str(latest["local_path"])))
            return status, Path(str(latest["local_path"]))

        number = int(latest["version_number"]) + 1 if latest else 1
        root = self._profile_root(profile.creator_id)
        versions = confined_path(root, Path("versions"))
        final = confined_path(versions, Path(f"v{number:04d}"))
        temp = confined_path(versions, Path(f".v{number:04d}.{uuid.uuid4().hex}.tmp"))
        temp.mkdir(parents=True, exist_ok=False)
        cover_name: str | None = None
        cover_sha: str | None = None
        try:
            image_items = [item for item in profile.profile_items if item.image_url]
            if profile.cover_url or image_items:
                settings = self.config.download
                with AssetDownloader(
                    cookie=self.cookie, timeout=settings.timeout_seconds,
                    retries=settings.retry_count, interval=settings.request_interval_seconds,
                    resume=settings.resume, user_agent=self.user_agent,
                    progress=self.progress_callback,
                ) as downloader:
                    if profile.cover_url:
                        validate_url(profile.cover_url, download=True)
                        suffix = self._profile_image_suffix(profile.cover_url)
                        cover_name = f"cover{suffix}"
                        cover_target = temp / cover_name
                        reusable = self._reusable_profile_cover(profile, latest)
                        if reusable:
                            self.storage.link_or_copy(reusable, cover_target)
                            cover_sha = sha256_file(cover_target)
                        else:
                            asset = Asset(
                                asset_id="creator-profile-cover", type="cover", url=profile.cover_url,
                                original_name=cover_name, local_path=cover_name,
                            )
                            downloader.download(asset, cover_target)
                            cover_sha = asset.sha256
                    previous = self._load_profile_version(latest)
                    for index, item in enumerate(image_items, start=1):
                        validate_url(item.image_url or "", download=True)
                        identity = safe_filename(item.item_id, fallback=f"item-{index}", max_length=60)
                        relative = Path("images") / f"{index:03d}_{identity}{self._profile_image_suffix(item.image_url or '')}"
                        item.image_path = relative.as_posix()
                        target = confined_path(temp, relative)
                        reusable = self._reusable_profile_item(item.image_url or "", previous, latest)
                        if reusable:
                            self.storage.link_or_copy(reusable, target)
                            item.image_sha256 = sha256_file(target)
                        else:
                            asset = Asset(
                                asset_id=item.item_id or f"profile-item-{index}",
                                type="image", url=item.image_url or "",
                                original_name=target.name, local_path=item.image_path,
                            )
                            downloader.download(asset, target)
                            item.image_sha256 = asset.sha256
            captured_at = now_iso()
            self._write_json(temp / "profile.json", profile.model_dump(mode="json"))
            files = {"profile.json": sha256_file(temp / "profile.json")}
            if cover_name and cover_sha:
                files[cover_name] = cover_sha
            for item in profile.profile_items:
                if item.image_path and item.image_sha256:
                    files[item.image_path] = item.image_sha256
            self._write_json(temp / "manifest.json", {
                "creator_id": profile.creator_id,
                "version": number,
                "captured_at": captured_at,
                "content_fingerprint": profile.content_fingerprint,
                "status": "completed",
                "files": files,
            })
            self.storage.publish_version(temp, final)
            self._update_profile_aliases(root, final)
            self.db.register_profile_version(
                profile.creator_id, profile.name, number, profile.content_fingerprint,
                str(final), str(final / "profile.json"),
                str(final / cover_name) if cover_name else None, cover_sha, captured_at,
            )
            if profile.icon_url:
                self._save_profile_icon(profile)
            return status, final
        except BaseException:
            shutil.rmtree(temp, ignore_errors=True)
            raise

    def _profile_root(self, creator_id: str) -> Path:
        return confined_path(
            self.config.storage.output_dir, Path(safe_filename(creator_id)) / "profile"
        )

    def _reusable_profile_cover(self, profile: CreatorProfile, latest) -> Path | None:
        if not latest or not latest["cover_path"] or not latest["cover_sha256"]:
            return None
        try:
            previous = CreatorProfile.model_validate_json(
                Path(str(latest["json_path"])).read_text(encoding="utf-8")
            )
            path = Path(str(latest["cover_path"]))
            if (previous.cover_url == profile.cover_url and path.is_file()
                    and sha256_file(path) == str(latest["cover_sha256"])):
                return path
        except (OSError, ValueError):
            return None
        return None

    @staticmethod
    def _profile_image_suffix(url: str) -> str:
        suffix = Path(urlparse(url).path).suffix.lower()
        return suffix if suffix in {".jpg", ".jpeg", ".png", ".gif", ".webp"} else ".img"

    @staticmethod
    def _load_profile_version(latest) -> CreatorProfile | None:
        if not latest or not latest["json_path"]:
            return None
        try:
            return CreatorProfile.model_validate_json(
                Path(str(latest["json_path"])).read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            return None

    @staticmethod
    def _reusable_profile_item(
        image_url: str, previous: CreatorProfile | None, latest,
    ) -> Path | None:
        if previous is None or latest is None:
            return None
        old = next(
            (item for item in previous.profile_items if item.image_url == image_url), None
        )
        if not old or not old.image_path or not old.image_sha256:
            return None
        try:
            path = confined_path(Path(str(latest["local_path"])), Path(old.image_path))
        except ValueError:
            return None
        if path.is_file() and sha256_file(path) == old.image_sha256:
            return path
        return None

    def _profile_item_images_intact(self, latest) -> bool:
        previous = self._load_profile_version(latest)
        if previous is None:
            return False
        for item in previous.profile_items:
            if not item.image_url:
                continue
            if not item.image_path or not item.image_sha256:
                return False
            try:
                path = confined_path(Path(str(latest["local_path"])), Path(item.image_path))
            except ValueError:
                return False
            if not path.is_file() or sha256_file(path) != item.image_sha256:
                return False
        return True

    def _update_profile_aliases(self, root: Path, version: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        for old in root.glob("cover.*"):
            old.unlink(missing_ok=True)
        for source in version.rglob("*"):
            if not source.is_file():
                continue
            relative = source.relative_to(version)
            target = confined_path(root, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
            self.storage.link_or_copy(source, temporary)
            os.replace(temporary, target)

    def _save_profile_icon(self, profile: CreatorProfile) -> None:
        validate_url(profile.icon_url or "", download=True)
        row = self.db.creator_row(profile.creator_id)
        existing = Path(str(row["icon_path"])) if row and row["icon_path"] else None
        if (row and row["icon_url"] == profile.icon_url and existing and existing.is_file()
                and row["icon_sha256"] and sha256_file(existing) == row["icon_sha256"]):
            return
        suffix = Path(urlparse(profile.icon_url or "").path).suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
            suffix = ".img"
        target = confined_path(
            self.config.storage.output_dir,
            Path(safe_filename(profile.creator_id)) / f"creator-avatar{suffix}",
        )
        asset = Asset(
            asset_id="creator-avatar", type="image", url=profile.icon_url or "",
            original_name=target.name, local_path=target.name,
        )
        settings = self.config.download
        try:
            with AssetDownloader(
                cookie=self.cookie, timeout=settings.timeout_seconds,
                retries=settings.retry_count, interval=settings.request_interval_seconds,
                resume=settings.resume, user_agent=self.user_agent,
                progress=self.progress_callback,
            ) as downloader:
                downloader.download(asset, target)
        except (DownloadAuthorizationError, DownloadRateLimitedError):
            raise
        except DownloadError as exc:
            get_logger().warning(
                "creator profile icon download failed creator_id=%s: %s",
                profile.creator_id, exc,
            )
            return
        if asset.sha256:
            self.db.set_creator_icon(
                profile.creator_id, profile.icon_url or "", str(target), asset.sha256
            )

    def save_fancard(
        self, payload: dict, image_data: bytes | None, content_type: str | None = "image/jpeg",
        *, captured_at: str | None = None,
    ) -> tuple[str, Path]:
        body = payload.get("body")
        if not isinstance(body, dict):
            raise ValueError("Fan Card 回應缺少 body")
        plan = body.get("plan")
        if not isinstance(plan, dict) or not plan.get("creatorId"):
            raise ValueError("Fan Card 回應缺少 plan.creatorId")
        creator_id = str(plan["creatorId"])
        transactions = body.get("supportTransactions") or []
        months = sorted({
            str(item.get("targetMonth")) for item in transactions
            if isinstance(item, dict) and re.fullmatch(r"\d{4}-\d{2}", str(item.get("targetMonth") or ""))
        })
        if not months:
            raise ValueError("Fan Card 回應缺少有效 targetMonth")
        # The API has no card-month field and this month's payment can appear days after the
        # creator switches cards, so the card belongs to the JST month it was captured in.
        captured_at = captured_at or now_iso()
        target_month = fanbox_month(captured_at)
        if target_month is None:
            raise ValueError("Fan Card 擷取時間缺少 UTC offset")
        payment_seen = target_month in months
        encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        fingerprint = hashlib.sha256(encoded).hexdigest()
        image_sha = hashlib.sha256(image_data).hexdigest() if image_data is not None else ""
        creator_root = confined_path(
            self.config.storage.output_dir, Path(safe_filename(creator_id)) / "fancards" / target_month
        )
        latest = self.db.latest_fancard_version(creator_id, target_month)
        if latest and latest["content_fingerprint"] == fingerprint:
            image_path = Path(str(latest["image_path"] or ""))
            no_image = image_data is None and not latest["image_path"] and not latest["image_sha256"]
            image_intact = (image_data is not None and image_path.is_file()
                            and sha256_file(image_path) == str(latest["image_sha256"]))
            if no_image or image_intact:
                latest_path = Path(str(latest["local_path"]))
                self._update_fancard_aliases(
                    creator_root, latest_path, image_path.name if image_intact else None
                )
                return "unchanged", latest_path

        number = int(latest["version_number"]) + 1 if latest else 1
        versions_root = confined_path(creator_root, Path("versions"))
        final = confined_path(versions_root, Path(f"v{number:04d}"))
        temp = confined_path(versions_root, Path(f".v{number:04d}.{uuid.uuid4().hex}.tmp"))
        temp.mkdir(parents=True, exist_ok=False)
        suffix = ".png" if content_type and "png" in content_type.casefold() else ".jpeg"
        image_name = f"card{suffix}" if image_data is not None else None
        try:
            if image_name and image_data is not None:
                (temp / image_name).write_bytes(image_data)
            self._write_json(temp / "fancard.json", payload)
            self.storage.atomic_write_text(
                temp / "fancard.md",
                self._render_fancard_markdown(body, target_month, number, captured_at, image_name),
            )
            self._write_json(temp / "manifest.json", {
                "creator_id": creator_id,
                "target_month": target_month,
                "target_month_basis": "captured_at_jst",
                "target_month_payment_seen": payment_seen,
                "version": number,
                "captured_at": captured_at,
                "content_fingerprint": fingerprint,
                "files": ({image_name: image_sha} if image_name else {}) | {
                    "fancard.json": sha256_file(temp / "fancard.json"),
                    "fancard.md": sha256_file(temp / "fancard.md"),
                },
            })
            self.storage.publish_version(temp, final)
            self._update_fancard_aliases(creator_root, final, image_name)
            self.db.register_fancard_version(
                creator_id, target_month, number, fingerprint, str(final),
                str(final / image_name) if image_name else "", image_sha, captured_at,
            )
            return ("updated" if latest else "new"), final
        except BaseException:
            shutil.rmtree(temp, ignore_errors=True)
            raise

    def _update_fancard_aliases(self, root: Path, version: Path, image_name: str | None) -> None:
        root.mkdir(parents=True, exist_ok=True)
        for old_name in ("card.jpeg", "card.png"):
            if old_name != image_name:
                (root / old_name).unlink(missing_ok=True)
        if image_name:
            image_temp = root / f".{image_name}.{uuid.uuid4().hex}.tmp"
            self.storage.link_or_copy(version / image_name, image_temp)
            os.replace(image_temp, root / image_name)
        self.storage.atomic_write_bytes(root / "fancard.json", (version / "fancard.json").read_bytes())
        self.storage.atomic_write_bytes(root / "fancard.md", (version / "fancard.md").read_bytes())

    @staticmethod
    def _render_fancard_markdown(
        body: dict, target_month: str, version: int, captured_at: str, image_name: str | None,
    ) -> str:
        plan = body.get("plan") or {}
        user = plan.get("user") or {}
        lines = [
            "---",
            f"creator_id: {json.dumps(str(plan.get('creatorId') or ''), ensure_ascii=False)}",
            f"target_month: {json.dumps(target_month)}",
            f"archive_version: {version}",
            f"captured_at: {json.dumps(isoformat_display(captured_at, None))}",
            "---", "",
            f"# Fan Card — {target_month}", "",
            f"- 創作者：{user.get('name') or plan.get('creatorId') or ''}",
            f"- 方案：{plan.get('title') or ''}",
            f"- 金額：¥{plan.get('fee') or 0}/月",
            f"- 支援開始：{isoformat_display(body.get('supportStartDatetime'), '')}", "",
            "## 方案說明", "",
            str(plan.get("description") or "（無）"), "",
        ]
        if image_name:
            lines[8:8] = [f"![Fan Card]({image_name})", ""]
        else:
            lines[8:8] = ["> 此創作者未提供自訂 Fan Card 卡面。", ""]
        perks = normalize_fancard_perks(
            plan.get("perks"), creator_id=str(plan.get("creatorId") or "")
        )
        if perks:
            lines.extend(["## 方案權益", ""])
            for perk in perks:
                lines.extend([
                    f"### {perk['label']}", "",
                    f"- 狀態：{perk['status_label']}", "",
                    str(perk["description"]), "",
                ])
                if perk["guidance"]:
                    guidance = str(perk["guidance"])
                    if perk["settings_url"] and perk["settings_label"]:
                        guidance = (
                            f"Discord 連結可在[{perk['settings_label']}]"
                            f"({perk['settings_url']})中編輯。"
                        )
                    lines.extend([guidance, ""])
                if perk["action_url"]:
                    lines.extend([f"[{perk['action_label']}]({perk['action_url']})", ""])
        lines.extend(["## 支援月份", ""])
        paid_months = set()
        for item in body.get("supportTransactions") or []:
            if isinstance(item, dict):
                paid_months.add(str(item.get("targetMonth")))
                lines.append(f"- {item.get('targetMonth')}: ¥{item.get('paidAmount')}")
        if target_month not in paid_months:
            lines.extend(["", f"> {target_month} 的付款紀錄尚未出現；卡片月份依擷取當下的日本時間判定。"])
        return "\n".join(lines).rstrip() + "\n"

    def _write_manifest(self, directory: Path, post: Post, number: int, captured_at: str,
                        status: PostStatus, previous) -> None:
        files = {}
        for path in directory.rglob("*"):
            if path.is_file() and path.name != "manifest.json":
                files[path.relative_to(directory).as_posix()] = sha256_file(path)
        self._write_json(directory / "manifest.json", {
            "version": number,
            "captured_at": captured_at,
            "remote_updated_at": post.updated_at.isoformat() if post.updated_at else None,
            "content_fingerprint": post.content_fingerprint or "",
            "status": status.value,
            "previous_version": int(previous["version_number"]) if previous else None,
            "files": files,
        })

    def _update_previous_navigation(self, previous, next_number: int) -> None:
        if not previous or not previous["json_path"] or not previous["markdown_path"]:
            return
        try:
            old = Post.model_validate_json(Path(previous["json_path"]).read_text(encoding="utf-8"))
            number = int(previous["version_number"])
            self.storage.atomic_write_text(
                Path(previous["markdown_path"]),
                render_markdown(
                    old, archive_version=number, captured_at=previous["captured_at"],
                    previous_version=f"../v{number - 1:04d}/post.md" if number > 1 else None,
                    next_version=f"../v{next_number:04d}/post.md",
                ),
            )
            manifest_path = Path(previous["local_path"]) / "manifest.json"
            if manifest_path.exists():
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest.setdefault("files", {})["post.md"] = sha256_file(Path(previous["markdown_path"]))
                self._write_json(manifest_path, manifest)
        except (OSError, ValueError, json.JSONDecodeError):
            return

    @staticmethod
    def _write_json(path: Path, value: object) -> None:
        BackupStorage.atomic_write_text(
            path, json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        )

    def _migrate_legacy_versions(self) -> None:
        for row in self.db.completed_posts_without_versions():
            temp: Path | None = None
            root = Path(str(row["local_path"] or ""))
            metadata = root / "post.json"
            if not metadata.exists():
                continue
            try:
                post = Post.model_validate_json(metadata.read_text(encoding="utf-8"))
                post.content_fingerprint = post.content_fingerprint or str(row["content_fingerprint"] or "")
                temp, final = self.storage.prepare_version(post, 1)
                for name in ("post.md", "post.json", "images", "files", "cover"):
                    source = root / name
                    if source.is_file():
                        self.storage.link_or_copy(source, temp / name)
                    elif source.is_dir():
                        for item in source.rglob("*"):
                            if item.is_file():
                                self.storage.link_or_copy(item, temp / name / item.relative_to(source))
                captured = now_iso()
                if self.config.markdown.enabled:
                    markdown = render_markdown(post, archive_version=1, captured_at=captured)
                    self.storage.atomic_write_text(temp / "post.md", markdown)
                self._write_manifest(temp, post, 1, captured, PostStatus.COMPLETED, None)
                self.storage.publish_version(temp, final)
                if self.config.markdown.enabled:
                    self.storage.atomic_write_text(root / "post.md", markdown)
                self.db.register_legacy_version(
                    post.post_id, post.content_fingerprint or str(row["content_fingerprint"] or ""),
                    str(final), str(final / "post.md"), str(final / "post.json"), row["updated_at"],
                    captured,
                )
            except (OSError, ValueError) as exc:
                get_logger().error(
                    "legacy version migration failed post_id=%s path=%s: %s",
                    row["post_id"], root, exc,
                )
                if temp is not None:
                    shutil.rmtree(temp, ignore_errors=True)

    def _assets_intact(self, post: Post) -> bool:
        selected = [asset for asset in post.assets
                    if (asset.type != "image" or self.config.download.original_images)
                    and (asset.type != "file" or self.config.download.download_attachments)]
        if post.cover and self.config.download.download_cover:
            selected.append(post.cover)
        for asset in selected:
            row = self.db.asset_row(post.post_id, asset.asset_id, asset.url)
            if not row or row["status"] != AssetStatus.COMPLETED.value or not row["local_path"]:
                return False
            path = confined_path(self.storage.post_dir(post), Path(str(row["local_path"])))
            if not path.exists() or (row["size"] is not None and path.stat().st_size != row["size"]):
                return False
            if row["sha256"] and sha256_file(path) != row["sha256"]:
                return False
        return True

    def verify(
        self, progress_callback: Callable[[dict[str, object]], None] | None = None,
    ) -> list[VerificationIssue]:
        issues: list[VerificationIssue] = []
        root = self.config.storage.output_dir
        current = 0

        def publish(phase: str, total: int | None, item: str) -> None:
            if progress_callback is None:
                return
            if total is None:
                percent = None
            elif total == 0:
                percent = 100.0
            else:
                percent = min(100.0, current / total * 100)
            progress_callback({
                "phase": phase,
                "current": current,
                "total": total,
                "percent": percent,
                "item": item,
                "issue_count": len(issues),
            })

        def advance(phase: str, total: int, item: str) -> None:
            nonlocal current
            current += 1
            publish(phase, total, item)

        publish("scan", None, "掃描封存驗證項目")
        if not root.exists():
            issues.append(VerificationIssue(path=str(root), reason="備份目錄不存在"))
            advance("consistency", 1, "備份目錄")
            return issues

        post_snapshots: list[tuple[Path, Post | None, Exception | None]] = []
        for metadata in sorted(root.glob("*/*/post.json")):
            try:
                post = Post.model_validate_json(metadata.read_text(encoding="utf-8"))
            except Exception as exc:
                post_snapshots.append((metadata, None, exc))
                continue
            post_snapshots.append((metadata, post, None))

        manifest_snapshots: list[
            tuple[Path, str, str, str, Exception | None, list[tuple[str, object]]]
        ] = []

        def scan_manifests(pattern: str, phase: str, prefix: str) -> None:
            for manifest_path in sorted(root.glob(pattern)):
                parts = manifest_path.relative_to(root).parts
                if phase == "versions":
                    label = f"Post {parts[1]}"
                elif phase == "fancards":
                    label = f"@{parts[0]} / Fan Card {parts[2]}"
                else:
                    label = f"@{parts[0]} / Creator Profile"
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    files = manifest.get("files") or {}
                    if not isinstance(files, dict):
                        raise ValueError("files 欄位格式錯誤")
                    manifest_snapshots.append((
                        manifest_path, phase, prefix, label, None, list(files.items()),
                    ))
                except (OSError, ValueError, json.JSONDecodeError) as exc:
                    manifest_snapshots.append((
                        manifest_path, phase, prefix, label, exc, [],
                    ))

        scan_manifests("*/*/versions/v*/manifest.json", "versions", "歷史版本")
        scan_manifests("*/fancards/*/versions/v*/manifest.json", "fancards", "Fan Card")
        scan_manifests("*/profile/versions/v*/manifest.json", "profiles", "Profile")
        incomplete_versions = list(self.db.incomplete_versions())
        missing_versions = list(self.db.completed_posts_without_versions())
        total = (
            sum(1 + (len(post.assets) + (1 if post.cover else 0) if post else 0)
                for _, post, _ in post_snapshots)
            + sum(1 + len(files) for *_, files in manifest_snapshots)
            + len(incomplete_versions) + len(missing_versions)
        )
        total += 1 if total else 0  # the version/time audit step
        publish("scan", total, f"已建立 {total} 個驗證項目")

        for metadata, post, parse_error in post_snapshots:
            fallback_id = metadata.parent.name
            if parse_error is not None or post is None:
                issues.append(VerificationIssue(
                    path=str(metadata), reason=f"post.json 無法解析：{parse_error}",
                ))
                advance("posts", total, f"Post {fallback_id}")
                continue
            advance("posts", total, f"Post {post.post_id} 中繼資料")
            for asset in [*post.assets, *([post.cover] if post.cover else [])]:
                if not asset.local_path or asset.status != AssetStatus.COMPLETED:
                    issues.append(VerificationIssue(
                        path=str(metadata.parent / (asset.local_path or asset.asset_id)),
                        reason=f"資源尚未完成（{asset.status.value}）",
                        post_id=post.post_id,
                        asset_id=asset.asset_id,
                    ))
                    advance("posts", total, f"Post {post.post_id} 資源")
                    continue
                try:
                    path = confined_path(metadata.parent, Path(asset.local_path))
                except ValueError:
                    issues.append(VerificationIssue(
                        path=asset.local_path, reason="資源路徑超出投稿目錄",
                        post_id=post.post_id, asset_id=asset.asset_id,
                    ))
                    asset.status = AssetStatus.CORRUPT
                    self.db.set_asset(post.post_id, asset)
                    self.db.set_post_status(post.post_id, PostStatus.PARTIAL, "完整性驗證失敗")
                    advance("posts", total, f"Post {post.post_id} 資源")
                    continue
                if not path.exists():
                    asset.status = AssetStatus.MISSING
                    issues.append(VerificationIssue(path=str(path), reason="檔案遺失", post_id=post.post_id, asset_id=asset.asset_id))
                elif asset.size is not None and path.stat().st_size != asset.size:
                    asset.status = AssetStatus.CORRUPT
                    issues.append(VerificationIssue(path=str(path), reason="檔案大小不符", post_id=post.post_id, asset_id=asset.asset_id))
                elif asset.sha256 and sha256_file(path) != asset.sha256:
                    asset.status = AssetStatus.CORRUPT
                    issues.append(VerificationIssue(path=str(path), reason="SHA-256 不符", post_id=post.post_id, asset_id=asset.asset_id))
                if asset.status in {AssetStatus.MISSING, AssetStatus.CORRUPT}:
                    self.db.set_asset(post.post_id, asset)
                    self.db.set_post_status(post.post_id, PostStatus.PARTIAL, "完整性驗證失敗")
                advance("posts", total, f"Post {post.post_id} 資源")

        for manifest_path, phase, prefix, label, parse_error, files in manifest_snapshots:
            if parse_error is not None:
                reason_prefix = "manifest.json" if phase == "versions" else f"{prefix} manifest"
                issues.append(VerificationIssue(
                    path=str(manifest_path), reason=f"{reason_prefix} 無法驗證：{parse_error}",
                ))
                advance(phase, total, label)
                continue
            advance(phase, total, f"{label} manifest")
            for relative, expected in files:
                try:
                    path = confined_path(manifest_path.parent, Path(str(relative)))
                    if not path.exists():
                        issues.append(VerificationIssue(path=str(path), reason=f"{prefix} 檔案遺失"))
                    elif sha256_file(path) != str(expected):
                        issues.append(VerificationIssue(path=str(path), reason=f"{prefix} SHA-256 不符"))
                except (OSError, ValueError) as exc:
                    issues.append(VerificationIssue(
                        path=str(manifest_path), reason=f"{prefix} manifest 無法驗證：{exc}",
                    ))
                advance(phase, total, label)

        for row in incomplete_versions:
            issues.append(VerificationIssue(
                path=str(row["local_path"]),
                reason=f"版本尚未完成（{row['status']}）",
                post_id=str(row["post_id"]),
            ))
            advance("consistency", total, f"Post {row['post_id']} 一致性")
        for row in missing_versions:
            issues.append(VerificationIssue(
                path=str(row["local_path"] or self.config.storage.database),
                reason="資料庫標示為 completed，但缺少完成版本紀錄",
                post_id=str(row["post_id"]),
            ))
            advance("consistency", total, f"Post {row['post_id']} 一致性")
        issues.extend(self._history_issues())
        if total == 0:
            publish("scan", 0, "封存中沒有需要驗證的項目")
        else:
            advance("history", total, "版本與時間稽核")
        return issues

    def _history_issues(self) -> list[VerificationIssue]:
        """Read-only version/time audit; only error-level findings fail verification (warnings stay in `audit`)."""
        from .audit import ArchiveAuditor

        report = ArchiveAuditor(self.config).run()
        return [
            VerificationIssue(
                path=f"{finding.subject_type}/{finding.subject_id}",
                reason=f"版本／時間稽核（{finding.code}）：{finding.issue}"
                + ("可執行 repair-copy 在副本修復。" if finding.repairability == "automatic" else ""),
                post_id=finding.subject_id if finding.subject_type == "post" else None,
            )
            for finding in report.findings if finding.severity == "error"
        ]
