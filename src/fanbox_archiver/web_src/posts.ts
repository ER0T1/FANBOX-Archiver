namespace FanboxUI {
  export interface PostListActions {
    onOpen(postId: string): void;
    onPage(page: number): void;
    onTag?(tag: string): void;
    activeTag?: string;
    order?: SortOrder;
    onOrder?(order: SortOrder): void;
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
      : h("span", {class: "post-cover placeholder", "aria-hidden": "true"}, t("posts.cover_placeholder")),
    h("span", {class: "post-main"},
      h("span", {class: "post-meta"}, formatDate(item.published_at),
        item.is_pinned ? h("span", {class: "pin-badge"}, t("posts.pinned")) : null,
        h("span", {class: "fee-badge"}, feeLabel(item.fee_required))),
      h("strong", {}, item.title),
      h("small", {}, t("posts.card_meta", {creator: item.creator_name, post_id: item.post_id, count: item.version_count})),
      item.tags.length ? h("span", {class: "post-tags", "aria-label": t("posts.tags_label", {tags: item.tags.join(t("posts.tag_separator"))})},
        item.tags.map(tag => h("span", {class: "post-tag"}, tag))) : null),
    h("span", {class: `badge status-${item.status}`}, item.status));
  }

  export function renderPagination(
    data: Pick<Page<unknown>, "page" | "pages">,
    onPage: (page: number) => void,
    label = t("posts.pagination"),
  ): HTMLElement | null {
    if (data.pages <= 1) return null;
    const previous = h("button", {
      type: "button", disabled: data.page <= 1,
      onclick: () => onPage(data.page - 1),
    }, t("common.previous_page"));
    const next = h("button", {
      type: "button", disabled: data.page >= data.pages,
      onclick: () => onPage(data.page + 1),
    }, t("common.next_page"));
    const pageJump = h("details", {class: "page-jump"},
      h("summary", {"aria-label": t("common.page_position", {page: data.page, pages: data.pages})}, `${data.page} / ${data.pages}`),
      h("div", {class: "page-menu", role: "listbox", "aria-label": t("common.page_jump")},
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
        h("p", {class: "eyebrow"}, t("posts.eyebrow")), h("h1", {}, t("posts.title")),
        h("p", {}, t("posts.total", {count: data.total}))),
      actions.onOrder ? sortToggle(actions.order ?? "desc", actions.onOrder, t("posts.sort_label")) : null),
      h("div", {class: "post-list"}, cards.length ? cards : h("p", {class: "empty"}, t("posts.empty"))),
      renderPagination(data, actions.onPage));
  }

  export function renderCreatorPostList(data: PostPage, actions: PostListActions): HTMLElement {
    const cards = data.items.map(item => renderPostCard(item, actions.onOpen));
    const filter = actions.onTag ? h("section", {class: "tag-filter", "aria-label": t("posts.tag_filter_label")},
      h("div", {class: "tag-filter-heading"},
        h("strong", {}, t("posts.tag_filter_title")),
        h("span", {}, actions.activeTag ? t("posts.tag_current", {tag: actions.activeTag}) : t("posts.tag_all_posts"))),
      h("div", {class: "tag-filter-options"},
        h("button", {type: "button", class: actions.activeTag ? "" : "active",
          "aria-pressed": actions.activeTag ? "false" : "true", onclick: () => actions.onTag?.("")},
        t("posts.tag_all", {count: data.creator_total})),
        data.tag_facets.length ? data.tag_facets.map(facet => h("button", {
          type: "button", class: actions.activeTag === facet.name ? "active" : "",
          "aria-pressed": actions.activeTag === facet.name ? "true" : "false",
          onclick: () => actions.onTag?.(facet.name),
        }, `${facet.name} ${facet.count}`)) : h("span", {class: "tag-filter-empty"}, t("posts.tag_none")))) : null;
    return h("div", {class: "creator-posts"},
      filter,
      actions.onOrder ? h("div", {class: "list-toolbar"},
        sortToggle(actions.order ?? "desc", actions.onOrder, t("posts.sort_label"))) : null,
      h("div", {class: "post-list"}, cards.length ? cards : h("p", {class: "empty"}, t("posts.empty"))),
      renderPagination(data, actions.onPage, t("posts.creator_pagination")));
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
        h("span", {class: "embed-source"}, preview.local_available ? t("reader.embed_local") : t("reader.embed_remote")),
        h("strong", {}, preview.title || `Post ${preview.post_id}`),
        preview.excerpt ? h("span", {class: "embed-excerpt"}, preview.excerpt) : null,
        h("span", {class: "embed-meta"}, meta)),
      preview.cover_url
        ? h("img", {class: "embed-cover", src: preview.cover_url, alt: "", loading: "lazy"})
        : h("span", {class: "embed-cover placeholder", "aria-hidden": "true"}, "FANBOX"));
  }

  function blockView(block: ContentBlock, onOpenPost: (postId: string) => void): HTMLElement | null {
    if (block.type === "image" && block.media_url) return h("figure", {},
      h("a", {href: block.media_url, target: "_blank"}, h("img", {src: block.media_url, loading: "lazy", alt: block.name || t("reader.image_alt")})));
    if (block.type === "file" && block.media_url) return h("p", {class: "attachment"}, h("a", {href: block.media_url}, block.name || block.filename || t("reader.download_attachment")));
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
      title: item?.title || (direction === "previous" ? t("reader.first_post") : t("reader.last_post")),
    },
    h("span", {}, direction === "previous" ? t("reader.previous") : t("reader.next")),
    h("strong", {}, item?.title || (direction === "previous" ? t("reader.no_previous") : t("reader.no_next"))));
    return h("nav", {
      class: `post-navigation ${placement}`,
      "aria-label": placement === "top" ? t("reader.nav_top") : t("reader.nav_bottom"),
    }, control(navigation.previous, "previous"),
    h("span", {class: "post-position"}, navigation.position ? `${navigation.position} / ${navigation.total}` : "—"),
    control(navigation.next, "next"));
  }

  export function renderPostReader(post: PostDetail, actions: PostReaderActions): HTMLElement {
    const body = post.blocks
      .map(block => blockView(block, actions.onOpenPost))
      .filter((block): block is HTMLElement => block !== null);
    return h("article", {class: "reader"},
      h("button", {type: "button", class: "back", onclick: actions.onBack}, t("reader.back")),
      navigationView(post.navigation, "top", actions.onOpenPost),
      post.cover_url ? h("a", {href: post.cover_url, target: "_blank"}, h("img", {class: "cover", src: post.cover_url, alt: t("reader.cover_alt")})) : null,
      h("header", {class: "reader-heading"}, h("p", {class: "eyebrow"}, `${post.creator_name} · POST ${post.post_id}`),
        h("h1", {}, post.title), h("div", {class: "reader-meta"},
          post.is_pinned ? h("span", {class: "pin-badge"}, t("reader.pinned")) : null,
          h("span", {class: "fee-badge"}, feeLabel(post.fee_required)),
          h("span", {}, t("reader.published", {time: formatDate(post.published_at)})),
          h("span", {}, t("reader.updated", {time: formatDate(post.updated_at)}))),
        actions.versionSelect),
      h("section", {class: "content"}, body.length ? body : h("p", {class: "empty"}, t("reader.empty_body"))),
      navigationView(post.navigation, "bottom", actions.onOpenPost),
      h("footer", {}, h("a", {href: post.url, target: "_blank", rel: "noreferrer"}, t("reader.open_original"))));
  }
}
