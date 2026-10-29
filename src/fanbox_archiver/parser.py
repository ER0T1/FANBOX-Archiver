from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup, NavigableString, Tag

from .models import Asset, ContentBlock, Post, TextStyle


ORIGINAL_IMAGE_RE = re.compile(r"^https://downloads\.fanbox\.cc/images/post/[^/]+/[^/]+$")
DOWNLOAD_FILE_RE = re.compile(r"^https://downloads\.fanbox\.cc/files/post/[^/]+/[^/]+$")
POST_ID_RE = re.compile(r"/(?:posts?|post)/(?P<id>\d+)")
CREATOR_RE = re.compile(r"/@(?P<id>[A-Za-z0-9_.-]+)")


def _asset_id(url: str, fallback: str) -> str:
    name = Path(unquote(urlparse(url).path)).stem
    return name or fallback


def _filename(url: str, fallback: str) -> str:
    return Path(unquote(urlparse(url).path)).name or fallback


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        match = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", text)
        if match:
            return datetime(int(match[1]), int(match[2]), int(match[3]))
    return None


def _normalise_text(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
    value = re.sub(r"[ \t]+\n", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


class HtmlPostParser:
    """Fallback parser for an already-rendered, user-supplied FANBOX page."""

    def parse_file(self, path: Path, source_url: str | None = None) -> Post:
        return self.parse(path.read_text(encoding="utf-8"), source_url=source_url)

    def parse(self, html: str, source_url: str | None = None) -> Post:
        soup = BeautifulSoup(html, "lxml")
        title = self._title(soup)
        creator_id, creator_name = self._creator(soup)
        original_anchors = self._original_image_anchors(soup)
        file_anchors = self._file_anchors(soup)
        media_anchors = [*original_anchors, *file_anchors]
        post_id = self._post_id(soup, source_url, original_anchors)
        url = source_url or f"https://www.fanbox.cc/@{creator_id}/posts/{post_id}"
        published = self._published(soup)
        root = self._content_root(soup, media_anchors)

        assets: list[Asset] = []
        seen_urls: set[str] = set()
        for index, anchor in enumerate(original_anchors, 1):
            href = str(anchor.get("href"))
            if href in seen_urls:
                continue
            seen_urls.add(href)
            assets.append(Asset(
                asset_id=_asset_id(href, f"image-{index}"),
                type="image",
                url=href,
                original_name=_filename(href, f"{index:03d}.bin"),
            ))
        for index, anchor in enumerate(file_anchors, 1):
            href = str(anchor.get("href"))
            if href in seen_urls:
                continue
            seen_urls.add(href)
            assets.append(Asset(
                asset_id=_asset_id(href, f"file-{index}"),
                type="file",
                url=href,
                original_name=self._attachment_name(anchor, href),
            ))

        blocks = self._blocks(root, assets)
        cover = self._cover(soup)
        post = Post(
            post_id=post_id,
            creator_id=creator_id,
            creator_name=creator_name,
            title=title,
            published_at=published,
            url=url,
            post_type="entry",
            blocks=blocks,
            assets=assets,
            cover=cover,
            raw={"source": "rendered_html"},
        )
        post.content_fingerprint = fingerprint(post)
        return post

    @staticmethod
    def _title(soup: BeautifulSoup) -> str:
        if soup.title and soup.title.string:
            return soup.title.string.split("｜", 1)[0].strip()
        heading = soup.select_one("article h1") or soup.find("h1")
        return heading.get_text(" ", strip=True) if heading else "untitled"

    @staticmethod
    def _creator(soup: BeautifulSoup) -> tuple[str, str]:
        for anchor in soup.select('a[href^="/@"]'):
            match = CREATOR_RE.fullmatch(str(anchor.get("href", "")))
            if match and anchor.get_text(strip=True):
                return match["id"], anchor.get_text(" ", strip=True)
        return "unknown", "unknown"

    @staticmethod
    def _original_image_anchors(soup: BeautifulSoup) -> list[Tag]:
        result: list[Tag] = []
        for anchor in soup.find_all("a", href=True):
            href = str(anchor["href"])
            if ORIGINAL_IMAGE_RE.match(href):
                result.append(anchor)
        return result

    @staticmethod
    def _file_anchors(soup: BeautifulSoup) -> list[Tag]:
        return [anchor for anchor in soup.find_all("a", href=True)
                if DOWNLOAD_FILE_RE.match(str(anchor["href"]))]

    @staticmethod
    def _attachment_name(anchor: Tag, url: str) -> str:
        container = anchor.find_parent(["figure", "article"]) or anchor.parent
        if isinstance(container, Tag):
            for line in container.get_text("\n", strip=True).splitlines():
                candidate = line.strip()
                if candidate and "下載" not in candidate and "ダウンロード" not in candidate and len(candidate) <= 180:
                    if Path(candidate).suffix:
                        return candidate
        return _filename(url, "attachment.bin")

    @staticmethod
    def _post_id(soup: BeautifulSoup, source_url: str | None, anchors: list[Tag]) -> str:
        candidates = [source_url or ""]
        candidates.extend(str(a.get("href", "")) for a in soup.find_all("a", href=True))
        for candidate in candidates:
            match = POST_ID_RE.search(candidate)
            if match:
                return match["id"]
        if anchors:
            match = re.search(r"/images/post/(\d+)/", str(anchors[0]["href"]))
            if match:
                return match[1]
        raise ValueError("無法從 HTML 判斷投稿 ID")

    @staticmethod
    def _published(soup: BeautifulSoup) -> datetime | None:
        time_node = soup.find("time")
        if time_node:
            parsed = _parse_datetime(time_node.get("datetime") or time_node.get_text(" ", strip=True))
            if parsed:
                return parsed
        text = soup.get_text(" ", strip=True)
        match = re.search(r"\d{4}年\d{1,2}月\d{1,2}日", text)
        return _parse_datetime(match.group(0)) if match else None

    @staticmethod
    def _content_root(soup: BeautifulSoup, anchors: list[Tag]) -> Tag:
        draft = soup.select_one('.public-DraftEditor-content [data-contents="true"]')
        if draft:
            node: Tag = draft
            anchor_set = set(anchors)
            while node.parent and isinstance(node.parent, Tag):
                contained = set(node.find_all("a", href=True)) & anchor_set
                if contained == anchor_set or node.name == "article":
                    return node
                node = node.parent
            return draft
        article = soup.find("article")
        return article if isinstance(article, Tag) else soup

    def _blocks(self, root: Tag, assets: list[Asset]) -> list[ContentBlock]:
        asset_by_url = {asset.url: asset for asset in assets}
        blocks: list[ContentBlock] = []
        consumed_images: set[str] = set()

        # FANBOX's rendered editor uses block-level divs. Process the shallowest
        # useful nodes to retain text/image order while avoiding duplicate text.
        candidates = root.find_all(["h1", "h2", "h3", "h4", "p", "blockquote", "hr", "a", "div"], recursive=True)
        for node in candidates:
            if any(parent is not root and parent in candidates and parent.name in {"p", "blockquote"}
                   for parent in node.parents if isinstance(parent, Tag)):
                continue
            if node.name == "a" and node.get("href") in asset_by_url:
                href = str(node["href"])
                if href not in consumed_images:
                    asset = asset_by_url[href]
                    if asset.type == "image":
                        blocks.append(ContentBlock(type="image", asset_id=asset.asset_id, url=href))
                    else:
                        blocks.append(ContentBlock(type="file", asset_id=asset.asset_id, url=href, name=asset.original_name))
                    consumed_images.add(href)
                continue
            if node.name != "a" and node.find_parent("a", href=True):
                continue
            atomic_parent = node.find_parent("figure")
            if (node.name != "a" and atomic_parent
                    and atomic_parent.find("a", href=lambda value: value in asset_by_url)):
                continue
            if node.name == "hr":
                blocks.append(ContentBlock(type="separator"))
                continue
            # A container is only a text block if it has no nested block container.
            if node.name == "div" and (
                node.find(["div", "p", "h1", "h2", "h3", "h4", "blockquote", "hr"], recursive=False)
                or node.find("a", href=True)
            ):
                continue
            text = _normalise_text(node.get_text("\n", strip=True))
            if not text:
                continue
            if node.name in {"h1", "h2", "h3", "h4"}:
                block = ContentBlock(type="heading", text=text, level=max(2, int(node.name[1])))
            elif node.name == "blockquote":
                block = ContentBlock(type="quote", text=text)
            elif node.name == "a" and node.get("href"):
                href = str(node["href"])
                block = ContentBlock(type="paragraph", text=f"[{text}]({href})")
            else:
                block = ContentBlock(type="paragraph", text=text)
            if not blocks or blocks[-1].model_dump() != block.model_dump():
                blocks.append(block)

        # If the live DOM structure changed, never silently lose discovered media.
        for asset in assets:
            if asset.url not in consumed_images:
                block_type = "image" if asset.type == "image" else "file"
                blocks.append(ContentBlock(type=block_type, asset_id=asset.asset_id, url=asset.url, name=asset.original_name))
        return blocks

    @staticmethod
    def _cover(soup: BeautifulSoup) -> Asset | None:
        node = soup.select_one('meta[property="og:image"]')
        if not node or not node.get("content"):
            return None
        url = str(node["content"])
        if "s.pximg.net/common/" in url:
            return None
        return Asset(asset_id="cover", type="cover", url=url, original_name=_filename(url, "cover.bin"))


class StructuredPostParser:
    """Parser for the response body returned by FANBOX post.info."""

    def parse(self, payload: dict[str, Any]) -> Post:
        body = payload.get("body", payload)
        if isinstance(body, dict) and isinstance(body.get("post"), dict):
            body = body["post"]
        if not isinstance(body, dict) or not body.get("id"):
            raise ValueError("投稿資料缺少 body.id")
        post_type = str(body.get("type") or "unknown")
        assets: list[Asset] = []
        blocks: list[ContentBlock] = []
        parse_warnings: list[str] = []
        raw_content = body.get("body")
        content = raw_content if isinstance(raw_content, dict) else {}
        if post_type in {"article", "image", "file"} and not isinstance(raw_content, dict):
            parse_warnings.append(f"{post_type} 投稿的 body 不是物件，已略過無法解析的內容。")

        if post_type == "article":
            image_map = content.get("imageMap") if isinstance(content.get("imageMap"), dict) else {}
            file_map = content.get("fileMap") if isinstance(content.get("fileMap"), dict) else {}
            url_embed_map = content.get("urlEmbedMap") if isinstance(content.get("urlEmbedMap"), dict) else {}
            raw_blocks = content.get("blocks") if isinstance(content.get("blocks"), list) else []
            if content.get("blocks") is not None and not isinstance(content.get("blocks"), list):
                parse_warnings.append("article.body.blocks 不是陣列，已略過無法解析的內容。")
            for index, raw in enumerate(raw_blocks, 1):
                if not isinstance(raw, dict):
                    parse_warnings.append(f"article 第 {index} 個區塊格式不正確，已保留為 raw 區塊。")
                    blocks.append(ContentBlock(type="raw", raw={"value": raw}))
                    continue
                kind = raw.get("type")
                if kind in {"p", "paragraph"}:
                    text = str(raw.get("text") or "")
                    styles = self._text_styles(raw.get("styles"), text)
                    blocks.append(ContentBlock(type="paragraph", text=text, styles=styles))
                elif kind in {"header", "heading"}:
                    text = str(raw.get("text") or "")
                    blocks.append(ContentBlock(
                        type="heading", text=text, level=2,
                        styles=self._text_styles(raw.get("styles"), text),
                    ))
                elif kind == "image":
                    reference = str(raw.get("imageId") or f"block-{index}")
                    item = image_map.get(reference)
                    asset = self._asset_or_warning(item, "image", reference, parse_warnings)
                    if asset:
                        assets.append(asset)
                        blocks.append(ContentBlock(type="image", asset_id=asset.asset_id, url=asset.url))
                    else:
                        blocks.append(ContentBlock(type="raw", raw=raw))
                elif kind == "file":
                    reference = str(raw.get("fileId") or f"block-{index}")
                    item = file_map.get(reference)
                    asset = self._asset_or_warning(item, "file", reference, parse_warnings)
                    if asset:
                        assets.append(asset)
                        blocks.append(ContentBlock(type="file", asset_id=asset.asset_id, url=asset.url, name=asset.original_name))
                    else:
                        blocks.append(ContentBlock(type="raw", raw=raw))
                elif kind == "url_embed":
                    embed_id = str(raw.get("urlEmbedId") or "")
                    embed = url_embed_map.get(embed_id) if isinstance(url_embed_map, dict) else None
                    embed = embed if isinstance(embed, dict) else {}
                    if not embed:
                        parse_warnings.append(
                            f"embed {embed_id or f'block-{index}'} 缺少 urlEmbedMap 資料，已保留原始區塊。"
                        )
                    url, title, excerpt = self._url_embed_details(embed)
                    asset_id = None
                    post_info = embed.get("postInfo") if isinstance(embed.get("postInfo"), dict) else {}
                    cover = post_info.get("cover") if isinstance(post_info.get("cover"), dict) else {}
                    cover_url = str(cover.get("url") or "")
                    if cover_url:
                        asset_id = f"url-embed-{embed_id}"
                        assets.append(Asset(
                            asset_id=asset_id, type="image", url=cover_url,
                            original_name=_filename(cover_url, f"{asset_id}.bin"),
                        ))
                    blocks.append(ContentBlock(
                        type="embed", url=url, name=title, text=excerpt,
                        asset_id=asset_id, raw={"urlEmbedId": embed_id, "embed": embed},
                    ))
                else:
                    parse_warnings.append(
                        f"article 第 {index} 個區塊類型 {kind or 'unknown'} 尚未支援，已保留原始資料。"
                    )
                    blocks.append(ContentBlock(type="raw", raw=raw))
        elif post_type == "image":
            if content.get("text"):
                blocks.append(ContentBlock(type="paragraph", text=str(content["text"])))
            for index, item in enumerate(content.get("images") or [], 1):
                asset = self._asset_or_warning(item, "image", f"image-{index}", parse_warnings)
                if asset:
                    assets.append(asset)
                    blocks.append(ContentBlock(type="image", asset_id=asset.asset_id, url=asset.url))
        elif post_type == "file":
            if content.get("text"):
                blocks.append(ContentBlock(type="paragraph", text=str(content["text"])))
            for index, item in enumerate(content.get("files") or [], 1):
                asset = self._asset_or_warning(item, "file", f"file-{index}", parse_warnings)
                if asset:
                    assets.append(asset)
                    blocks.append(ContentBlock(type="file", asset_id=asset.asset_id, url=asset.url, name=asset.original_name))
        else:
            text = content.get("text") if isinstance(raw_content, dict) else raw_content
            if text:
                blocks.append(ContentBlock(type="paragraph", text=str(text)))

        user = body.get("user") if isinstance(body.get("user"), dict) else {}
        creator = body.get("creatorId") or "unknown"
        if creator == "unknown":
            parse_warnings.append("投稿缺少 creatorId，已使用 unknown；請更新 fixture 或檢查 FANBOX 回應。")
        if not body.get("title"):
            parse_warnings.append("投稿缺少 title，已使用 untitled。")
        post = Post(
            post_id=str(body["id"]),
            creator_id=str(creator),
            creator_name=str(user.get("name") or creator),
            creator_icon_url=str(user.get("iconUrl") or "") or None,
            title=str(body.get("title") or "untitled"),
            published_at=_parse_datetime(body.get("publishedDatetime")),
            updated_at=_parse_datetime(body.get("updatedDatetime")),
            url=f"https://www.fanbox.cc/@{creator}/posts/{body['id']}",
            post_type=post_type,
            fee_required=body.get("feeRequired"),
            tags=list(body.get("tags") or []),
            blocks=blocks,
            assets=self._deduplicate(assets),
            parse_warnings=parse_warnings,
            raw=body,
        )
        cover_url = body.get("coverImageUrl")
        if cover_url:
            post.cover = Asset(asset_id="cover", type="cover", url=str(cover_url), original_name=_filename(str(cover_url), "cover.bin"))
        post.content_fingerprint = fingerprint(post)
        return post

    @staticmethod
    def _text_styles(value: object, text: str) -> list[TextStyle]:
        result: list[TextStyle] = []
        for item in value if isinstance(value, list) else []:
            if not isinstance(item, dict) or item.get("type") != "bold":
                continue
            try:
                offset = int(item.get("offset"))
                length = int(item.get("length"))
            except (TypeError, ValueError):
                continue
            if offset < 0 or length <= 0 or offset >= len(text):
                continue
            result.append(TextStyle(type="bold", offset=offset, length=min(length, len(text) - offset)))
        return sorted(result, key=lambda style: (style.offset, style.length))

    @staticmethod
    def _url_embed_details(embed: dict[str, Any]) -> tuple[str, str | None, str | None]:
        kind = str(embed.get("type") or "")
        if kind == "fanbox.post":
            info = embed.get("postInfo") if isinstance(embed.get("postInfo"), dict) else {}
            creator_id = str(info.get("creatorId") or "")
            post_id = str(info.get("id") or "")
            url = (f"https://www.fanbox.cc/@{creator_id}/posts/{post_id}"
                   if creator_id and post_id else "")
            return url, str(info.get("title") or "") or None, str(info.get("excerpt") or "") or None
        if kind == "default":
            return str(embed.get("url") or ""), str(embed.get("host") or "") or None, None
        if kind == "html.card":
            html_value = str(embed.get("html") or "")
            soup = BeautifulSoup(html_value, "html.parser")
            frame = soup.find("iframe", src=True)
            return (str(frame["src"]) if isinstance(frame, Tag) else ""), "外部連結", None
        return str(embed.get("url") or ""), None, None

    @staticmethod
    def _asset(item: dict[str, Any], kind: str, fallback: str) -> Asset:
        url = item.get("originalUrl") or item.get("url")
        if not url:
            raise ValueError(f"資源 {fallback} 缺少原始下載 URL")
        extension = str(item.get("extension") or "").lstrip(".")
        name = item.get("name")
        if name and extension and not str(name).casefold().endswith(f".{extension.casefold()}"):
            name = f"{name}.{extension}"
        name = name or _filename(str(url), fallback + (f".{extension}" if extension else ""))
        return Asset(
            asset_id=str(item.get("id") or _asset_id(str(url), fallback)),
            type=kind,  # type: ignore[arg-type]
            url=str(url),
            original_name=str(name),
            width=item.get("width"),
            height=item.get("height"),
        )

    @classmethod
    def _asset_or_warning(
        cls, item: object, kind: str, fallback: str, parse_warnings: list[str],
    ) -> Asset | None:
        if not isinstance(item, dict):
            parse_warnings.append(f"{kind} 資源 {fallback} 缺少對應資料，已略過。")
            return None
        try:
            return cls._asset(item, kind, fallback)
        except ValueError:
            preview_only = any(item.get(key) for key in ("thumbnailUrl", "previewUrl"))
            suffix = "；僅有縮圖／預覽網址，不會推測為原始檔。" if preview_only else "。"
            parse_warnings.append(f"{kind} 資源 {fallback} 缺少原始下載 URL，已略過{suffix}")
            return None

    @staticmethod
    def _deduplicate(assets: Iterable[Asset]) -> list[Asset]:
        result: list[Asset] = []
        seen: set[tuple[str, str]] = set()
        for asset in assets:
            key = (asset.asset_id, asset.url)
            if key not in seen:
                seen.add(key)
                result.append(asset)
        return result


def fingerprint(post: Post) -> str:
    data = {
        "title": post.title,
        "post_type": post.post_type,
        "fee_required": post.fee_required,
        "tags": post.tags,
        "blocks": [block.model_dump(mode="json") for block in post.blocks],
        "assets": [(asset.asset_id, asset.type, asset.url, asset.original_name) for asset in post.assets],
        "cover": ((post.cover.asset_id, post.cover.url, post.cover.original_name) if post.cover else None),
    }
    encoded = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
