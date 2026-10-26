from __future__ import annotations

from pathlib import Path

import yaml

from .models import Post


def _styled_text(value: str, styles) -> str:
    parts: list[str] = []
    cursor = 0
    for style in sorted(styles, key=lambda item: (item.offset, item.length)):
        if style.offset < cursor or style.offset >= len(value):
            continue
        end = min(len(value), style.offset + style.length)
        parts.extend([value[cursor:style.offset], "**", value[style.offset:end], "**"])
        cursor = end
    parts.append(value[cursor:])
    return "".join(parts)


def render_markdown(
    post: Post, *, archive_version: int | None = None, captured_at: str | None = None,
    previous_version: str | None = None, next_version: str | None = None,
) -> str:
    metadata = {
        "post_id": post.post_id,
        "creator_id": post.creator_id,
        "creator_name": post.creator_name,
        "title": post.title,
        "published_at": post.published_at.isoformat() if post.published_at else None,
        "updated_at": post.updated_at.isoformat() if post.updated_at else None,
        "fee_required": post.fee_required,
        "type": post.post_type,
        "url": post.url,
    }
    if archive_version is not None:
        metadata.update({
            "archive_version": archive_version,
            "captured_at": captured_at,
            "previous_version": previous_version,
            "next_version": next_version,
            "content_fingerprint": post.content_fingerprint,
        })
    front_matter = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False).strip()
    asset_names = {asset.asset_id: asset.local_path for asset in post.assets if asset.local_path}
    lines = ["---", front_matter, "---", "", f"# {post.title}", ""]
    for block in post.blocks:
        text = _styled_text(block.text or "", block.styles).strip()
        if block.type == "paragraph" and text:
            lines.extend([text, ""])
        elif block.type == "heading" and text:
            level = min(max(block.level or 2, 2), 6)
            lines.extend([f"{'#' * level} {text}", ""])
        elif block.type == "quote" and text:
            lines.extend(["\n".join(f"> {line}" for line in text.splitlines()), ""])
        elif block.type == "separator":
            lines.extend(["---", ""])
        elif block.type == "image":
            path = asset_names.get(block.asset_id or "")
            if path:
                lines.extend([f"![圖片]({Path(path).as_posix()})", ""])
            elif block.url:
                lines.extend([f"![圖片（尚未下載）]({block.url})", ""])
        elif block.type == "file":
            path = asset_names.get(block.asset_id or "")
            label = block.name or "下載附件"
            target = Path(path).as_posix() if path else block.url
            if target:
                lines.extend([f"[{label}]({target})", ""])
        elif block.type == "embed" and block.url:
            lines.extend([f"[外部嵌入內容]({block.url})", ""])
        elif block.type == "raw":
            lines.extend(["<!-- 無法解析的內容區塊，完整資料請見 post.json -->", ""])
    return "\n".join(lines).rstrip() + "\n"

