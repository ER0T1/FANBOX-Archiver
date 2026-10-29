namespace FanboxUI {
  export interface PostListActions {
    onOpen(postId: string): void;
    onPage(page: number): void;
  }

  export interface PostReaderActions {
    onBack(): void;
    onOpenPost(postId: string): void;
    versionSelect: HTMLElement;
  }

  export function renderPostCard(item: PostSummary, onOpen: (postId: string) => void): HTMLElement {
    return h("button", {
      type: "button", class: `post-card${item.is_pinned ? " pinned" : ""}`,
      onclick: () => onOpen(item.post_id),
    },
    item.cover_url
      ? h("img", {class: "post-cover", src: item.cover_url, alt: "", loading: "lazy"})
      : h("span", {class: "post-cover placeholder", "aria-hidden": "true"}, "POST"),
    h("span", {class: "post-main"},
      h("span", {class: "post-meta"}, formatDate(item.published_at),
        item.is_pinned ? h("span", {class: "pin-badge"}, "置頂") : null,
        h("span", {class: "fee-badge"}, feeLabel(item.fee_required))),
      h("strong", {}, item.title),
      h("small", {}, `${item.creator_name} · Post ${item.post_id} · ${item.version_count} 個版本`)),
    h("span", {class: `badge status-${item.status}`}, item.status));
  }

  export function renderPagination(
    data: Pick<Page<unknown>, "page" | "pages">,
    onPage: (page: number) => void,
    label = "投稿分頁",
  ): HTMLElement {
    const previous = h("button", {
      type: "button", disabled: data.page <= 1,
      onclick: () => onPage(data.page - 1),
    }, "← 上一頁");
    const next = h("button", {
      type: "button", disabled: data.page >= data.pages,
      onclick: () => onPage(data.page + 1),
    }, "下一頁 →");
    const pageJump = h("details", {class: "page-jump"},
      h("summary", {"aria-label": `目前第 ${data.page} 頁，共 ${data.pages} 頁`}, `${data.page} / ${data.pages}`),
      h("div", {class: "page-menu", role: "listbox", "aria-label": "跳至頁數"},
        Array.from({length: data.pages}, (_, index) => {
          const page = index + 1;
          return h("button", {
            type: "button", role: "option", "aria-selected": page === data.page,
            onclick: () => {
              (pageJump as HTMLDetailsElement).open = false;
              onPage(page);
            },
          }, String(page));
        })));
    return h("nav", {class: "pagination", "aria-label": label}, previous, pageJump, next);
  }

  export function renderPostListPage(data: Page<PostSummary>, actions: PostListActions): HTMLElement {
    const cards = data.items.map(item => renderPostCard(item, actions.onOpen));
    return h("section", {class: "page"},
      h("header", {class: "heading"}, h("div", {},
        h("p", {class: "eyebrow"}, "POSTS"), h("h1", {}, "投稿"), h("p", {}, `${data.total} 篇備份`))),
      h("div", {class: "post-list"}, cards.length ? cards : h("p", {class: "empty"}, "沒有符合條件的投稿。")),
      renderPagination(data, actions.onPage));
  }

  export function renderCreatorPostList(data: Page<PostSummary>, actions: PostListActions): HTMLElement {
    const cards = data.items.map(item => renderPostCard(item, actions.onOpen));
    return h("div", {class: "creator-posts"},
      h("div", {class: "post-list"}, cards.length ? cards : h("p", {class: "empty"}, "沒有符合條件的投稿。")),
      renderPagination(data, actions.onPage, "創作者投稿分頁"));
  }

  function richText(block: ContentBlock): DocumentFragment {
    const fragment = document.createDocumentFragment();
    const text = block.text ?? "";
    const styles = [...(block.styles ?? [])].sort((left, right) => left.offset - right.offset);
    let position = 0;
    for (const style of styles) {
      const start = Math.max(position, style.offset);
      if (start > position) fragment.append(text.slice(position, start));
      const end = Math.min(text.length, style.offset + style.length);
      fragment.append(h("strong", {}, text.slice(start, end)));
      position = end;
    }
    if (position < text.length) fragment.append(text.slice(position));
    return fragment;
  }

  function embedView(block: ContentBlock, onOpenPost: (postId: string) => void): HTMLElement | null {
    const preview = block.embed;
    if (!preview || preview.kind !== "fanbox.post" || !preview.post_id) {
      if (!block.url) return null;
      return h("p", {class: "attachment"}, h("a", {href: block.url, target: "_blank", rel: "noreferrer"}, block.name || block.url));
    }
    const meta: HTMLElement[] = [];
    if (preview.published_at) meta.push(h("span", {}, formatDate(preview.published_at)));
    if (preview.fee_required !== null && preview.fee_required !== undefined) {
      meta.push(h("span", {class: "embed-fee"}, feeLabel(preview.fee_required)));
    }
    if (preview.creator_name) meta.push(h("span", {}, preview.creator_name));
    const attributes: Record<string, unknown> = preview.local_available
      ? {href: `#post-${preview.post_id}`, onclick: (event: Event) => {
          event.preventDefault();
          onOpenPost(preview.post_id as string);
        }}
      : {href: preview.fanbox_url || "#", target: "_blank", rel: "noreferrer noopener"};
    return h("a", {class: "embed-card", ...attributes},
      h("span", {class: "embed-content"},
        h("span", {class: "embed-source"}, preview.local_available ? "FANBOX 投稿 · 本機備份" : "FANBOX 投稿"),
        h("strong", {}, preview.title || `Post ${preview.post_id}`),
        preview.excerpt ? h("span", {class: "embed-excerpt"}, preview.excerpt) : null,
        h("span", {class: "embed-meta"}, meta)),
      preview.cover_url
        ? h("img", {class: "embed-cover", src: preview.cover_url, alt: "", loading: "lazy"})
        : h("span", {class: "embed-cover placeholder", "aria-hidden": "true"}, "FANBOX"));
  }

  function blockView(block: ContentBlock, onOpenPost: (postId: string) => void): HTMLElement | null {
    if (block.type === "image" && block.media_url) return h("figure", {},
      h("a", {href: block.media_url, target: "_blank"}, h("img", {src: block.media_url, loading: "lazy", alt: block.name || "投稿圖片"})));
    if (block.type === "file" && block.media_url) return h("p", {class: "attachment"}, h("a", {href: block.media_url}, block.name || block.filename || "下載附件"));
    if (block.type === "separator") return h("hr");
    if (block.type === "quote") return h("blockquote", {}, richText(block));
    if (block.type === "heading") return h(`h${Math.min(Math.max(block.level || 2, 2), 6)}`, {}, richText(block));
    if (block.type === "embed") return embedView(block, onOpenPost);
    if (block.text) return h("p", {class: "body-text"}, richText(block));
    return null;
  }

  function navigationView(
    navigation: PostNavigation, placement: "top" | "bottom", onOpenPost: (postId: string) => void,
  ): HTMLElement {
    const control = (item: PostNeighbor | null, direction: "previous" | "next") => h("button", {
      type: "button", class: `post-nav-button ${direction}`, disabled: !item,
      onclick: () => item && onOpenPost(item.post_id),
      title: item?.title || (direction === "previous" ? "已是第一篇" : "已是最後一篇"),
    },
    h("span", {}, direction === "previous" ? "← 上一篇" : "下一篇 →"),
    h("strong", {}, item?.title || (direction === "previous" ? "沒有更前面的投稿" : "沒有更後面的投稿")));
    return h("nav", {
      class: `post-navigation ${placement}`,
      "aria-label": placement === "top" ? "文章頂端導覽" : "文章底部導覽",
    }, control(navigation.previous, "previous"),
    h("span", {class: "post-position"}, navigation.position ? `${navigation.position} / ${navigation.total}` : "—"),
    control(navigation.next, "next"));
  }

  export function renderPostReader(post: PostDetail, actions: PostReaderActions): HTMLElement {
    const body = post.blocks
      .map(block => blockView(block, actions.onOpenPost))
      .filter((block): block is HTMLElement => block !== null);
    return h("article", {class: "reader"},
      h("button", {type: "button", class: "back", onclick: actions.onBack}, "← 回到投稿"),
      navigationView(post.navigation, "top", actions.onOpenPost),
      post.cover_url ? h("a", {href: post.cover_url, target: "_blank"}, h("img", {class: "cover", src: post.cover_url, alt: "投稿封面"})) : null,
      h("header", {class: "reader-heading"}, h("p", {class: "eyebrow"}, `${post.creator_name} · POST ${post.post_id}`),
        h("h1", {}, post.title), h("div", {class: "reader-meta"},
          post.is_pinned ? h("span", {class: "pin-badge"}, "置頂投稿") : null,
          h("span", {class: "fee-badge"}, feeLabel(post.fee_required)),
          h("span", {}, `發布 ${formatDate(post.published_at)}`), h("span", {}, `更新 ${formatDate(post.updated_at)}`)),
        actions.versionSelect),
      h("section", {class: "content"}, body.length ? body : h("p", {class: "empty"}, "此版本沒有可顯示的正文。")),
      navigationView(post.navigation, "bottom", actions.onOpenPost),
      h("footer", {}, h("a", {href: post.url, target: "_blank", rel: "noreferrer"}, "開啟 FANBOX 原文 ↗")));
  }
}
