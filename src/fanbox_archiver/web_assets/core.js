"use strict";
var FanboxUI;
(function (FanboxUI) {
    function createInitialState() {
        return {
            view: "posts",
            page: 1,
            q: "",
            tag: "",
            current: null,
            postNavigation: null,
            creatorId: null,
            creatorTab: "profile",
            creator: null,
            creatorProfile: null,
            jobFilter: "all",
            activeJob: null,
            backupScreen: "form",
            backupJobId: null,
        };
    }
    FanboxUI.createInitialState = createInitialState;
})(FanboxUI || (FanboxUI = {}));
var FanboxUI;
(function (FanboxUI) {
    const dateFormatter = new Intl.DateTimeFormat("zh-TW", {
        timeZone: "Asia/Taipei",
        dateStyle: "medium",
        timeStyle: "short",
    });
    function formatDate(value) {
        return value ? dateFormatter.format(new Date(value)) : "—";
    }
    FanboxUI.formatDate = formatDate;
    function humanBytes(value) {
        const bytes = Number(value ?? 0);
        if (!Number.isFinite(bytes) || bytes <= 0)
            return "0 B";
        const units = ["B", "KB", "MB", "GB", "TB"];
        const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
        const scaled = bytes / (1024 ** index);
        const digits = index === 0 || scaled >= 100 ? 0 : scaled >= 10 ? 1 : 2;
        return `${scaled.toFixed(digits)} ${units[index]}`;
    }
    FanboxUI.humanBytes = humanBytes;
    function feeLabel(value) {
        if (value === null || value === undefined)
            return "檔位未記錄";
        return Number(value) <= 0 ? "全體公開" : `¥${Number(value).toLocaleString()}`;
    }
    FanboxUI.feeLabel = feeLabel;
})(FanboxUI || (FanboxUI = {}));
var FanboxUI;
(function (FanboxUI) {
    function appendChild(parent, child) {
        if (Array.isArray(child)) {
            for (const item of child)
                appendChild(parent, item);
        }
        else if (child instanceof Node) {
            parent.append(child);
        }
        else if (child !== null && child !== undefined && child !== false) {
            parent.append(document.createTextNode(String(child)));
        }
    }
    function h(tag, attrs = {}, ...children) {
        const node = document.createElement(tag);
        for (const [key, value] of Object.entries(attrs)) {
            if (key.startsWith("on") && typeof value === "function") {
                node.addEventListener(key.slice(2), value);
            }
            else if (value !== null && value !== undefined && value !== false) {
                node.setAttribute(key, value === true ? "" : String(value));
            }
        }
        for (const child of children)
            appendChild(node, child);
        return node;
    }
    FanboxUI.h = h;
})(FanboxUI || (FanboxUI = {}));
var FanboxUI;
(function (FanboxUI) {
    function customSelect(options) {
        const normalized = options.options.map(option => ({ value: String(option.value), label: String(option.label) }));
        let selectedValue = String(options.value ?? normalized[0]?.value ?? "");
        const menuId = `${options.id || "select"}-menu-${Math.random().toString(36).slice(2, 9)}`;
        const summaryText = FanboxUI.h("span", { class: "select-value" });
        const menu = FanboxUI.h("div", { id: menuId, class: "select-menu", role: "listbox", "aria-label": options.label });
        const root = FanboxUI.h("details", { class: "custom-select", id: options.id });
        const summary = FanboxUI.h("summary", { role: "combobox", "aria-label": options.label, "aria-controls": menuId,
            "aria-expanded": "false", "aria-haspopup": "listbox" }, summaryText);
        const update = (nextValue) => {
            selectedValue = String(nextValue);
            const selected = normalized.find(option => option.value === selectedValue) ?? normalized[0];
            summaryText.textContent = selected?.label ?? "";
            for (const item of menu.querySelectorAll('[role="option"]')) {
                const active = item.dataset.value === selectedValue;
                item.setAttribute("aria-selected", active ? "true" : "false");
                item.tabIndex = active ? 0 : -1;
            }
        };
        for (const option of normalized) {
            menu.append(FanboxUI.h("button", { type: "button", role: "option", "data-value": option.value, onclick: () => {
                    const changed = selectedValue !== option.value;
                    update(option.value);
                    root.open = false;
                    summary.focus();
                    if (changed)
                        options.onChange?.(option.value);
                } }, option.label));
        }
        summary.addEventListener("keydown", event => {
            if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key))
                return;
            event.preventDefault();
            root.open = true;
            const choices = [...menu.querySelectorAll('[role="option"]')];
            const selectedIndex = Math.max(0, choices.findIndex(item => item.dataset.value === selectedValue));
            const targetIndex = event.key === "End" ? choices.length - 1 : event.key === "ArrowUp"
                ? Math.max(0, selectedIndex - 1) : event.key === "ArrowDown"
                ? Math.min(choices.length - 1, selectedIndex + 1) : 0;
            choices[targetIndex]?.focus();
        });
        menu.addEventListener("keydown", event => {
            const choices = [...menu.querySelectorAll('[role="option"]')];
            const index = choices.indexOf(document.activeElement);
            if (event.key === "Escape") {
                event.preventDefault();
                root.open = false;
                summary.focus();
                return;
            }
            if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key))
                return;
            event.preventDefault();
            const targetIndex = event.key === "Home" ? 0 : event.key === "End" ? choices.length - 1
                : event.key === "ArrowDown" ? Math.min(choices.length - 1, index + 1) : Math.max(0, index - 1);
            choices[targetIndex]?.focus();
        });
        root.addEventListener("toggle", () => {
            summary.setAttribute("aria-expanded", root.open ? "true" : "false");
            if (root.open)
                menu.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: "nearest" });
        });
        Object.defineProperty(root, "value", { get: () => selectedValue, set: update });
        root.append(summary, menu);
        update(selectedValue);
        return root;
    }
    FanboxUI.customSelect = customSelect;
    function closeDropdownsOutside(target) {
        for (const dropdown of document.querySelectorAll(".custom-select[open], .page-jump[open]")) {
            if (!(target instanceof Node) || !dropdown.contains(target))
                dropdown.open = false;
        }
    }
    FanboxUI.closeDropdownsOutside = closeDropdownsOutside;
    function closeDropdownsAndFocus() {
        const dropdowns = [...document.querySelectorAll(".custom-select[open], .page-jump[open]")];
        for (const dropdown of dropdowns) {
            dropdown.open = false;
            dropdown.querySelector("summary")?.focus();
        }
        return dropdowns.length > 0;
    }
    FanboxUI.closeDropdownsAndFocus = closeDropdownsAndFocus;
    function renderError(error, onRetry) {
        const message = error instanceof Error ? error.message : String(error);
        return FanboxUI.h("section", { class: "panel error" }, FanboxUI.h("p", { class: "eyebrow" }, "ERROR"), FanboxUI.h("h1", {}, "無法讀取封存"), FanboxUI.h("p", {}, message), FanboxUI.h("button", { type: "button", onclick: onRetry }, "重試"));
    }
    FanboxUI.renderError = renderError;
    function setActiveNavigation(nav, view) {
        const active = view === "creator" ? "creators" : view;
        for (const button of nav.querySelectorAll("button")) {
            button.classList.toggle("active", button.dataset.view === active);
        }
    }
    FanboxUI.setActiveNavigation = setActiveNavigation;
    function setSearchState(search, view, creatorTab) {
        search.disabled = ["backup", "maintenance", "settings"].includes(view)
            || (view === "creator" && creatorTab === "profile");
        search.placeholder = view === "posts" ? "搜尋標題、Post ID 或創作者…"
            : view === "creators" ? "搜尋創作者…"
                : view === "creator" && creatorTab === "fancards" ? "搜尋月份…"
                    : view === "creator" && creatorTab === "posts" ? "搜尋此創作者的投稿…"
                        : view === "backup" ? "備份執行期間可繼續閱讀封存"
                            : view === "maintenance" ? "封存驗證與維護"
                                : view === "settings" ? "本機設定" : "創作者個人資料";
    }
    FanboxUI.setSearchState = setSearchState;
})(FanboxUI || (FanboxUI = {}));
var FanboxUI;
(function (FanboxUI) {
    async function requestJson(url, options = {}) {
        const headers = new Headers(options.headers);
        if (!headers.has("Accept"))
            headers.set("Accept", "application/json");
        const response = await fetch(url, { ...options, headers });
        if (!response.ok) {
            let detail = `HTTP ${response.status}`;
            try {
                const body = await response.json();
                if (body && typeof body === "object" && "detail" in body) {
                    detail = String(body.detail);
                }
            }
            catch {
            }
            throw new Error(detail);
        }
        return response.json();
    }
    FanboxUI.requestJson = requestJson;
    function getPosts(params) {
        return requestJson(`/api/posts?${params.toString()}`);
    }
    FanboxUI.getPosts = getPosts;
    function getPost(postId, params) {
        const query = params.toString();
        return requestJson(`/api/posts/${encodeURIComponent(postId)}${query ? `?${query}` : ""}`);
    }
    FanboxUI.getPost = getPost;
    function getCreators() {
        return requestJson("/api/creators");
    }
    FanboxUI.getCreators = getCreators;
    function getCreator(creatorId) {
        return requestJson(`/api/creators/${encodeURIComponent(creatorId)}`);
    }
    FanboxUI.getCreator = getCreator;
    function getCreatorProfile(creatorId, version = null) {
        const query = version === null ? "" : `?version=${version}`;
        return requestJson(`/api/creators/${encodeURIComponent(creatorId)}/profile${query}`);
    }
    FanboxUI.getCreatorProfile = getCreatorProfile;
    function getFanCards(params) {
        const query = params.toString();
        return requestJson(`/api/fancards${query ? `?${query}` : ""}`);
    }
    FanboxUI.getFanCards = getFanCards;
    function getFanCard(creatorId, month, version = null) {
        const query = version === null ? "" : `?version=${version}`;
        return requestJson(`/api/fancards/${encodeURIComponent(creatorId)}/${encodeURIComponent(month)}${query}`);
    }
    FanboxUI.getFanCard = getFanCard;
    function getSettings() {
        return requestJson("/api/config");
    }
    FanboxUI.getSettings = getSettings;
    function saveSettings(patch, sessionToken) {
        return requestJson("/api/config", {
            method: "PATCH",
            headers: { "Content-Type": "application/json", "X-Fanbox-Token": sessionToken },
            body: JSON.stringify(patch),
        });
    }
    FanboxUI.saveSettings = saveSettings;
    function getJobs() {
        return requestJson("/api/jobs");
    }
    FanboxUI.getJobs = getJobs;
    function getJob(jobId) {
        return requestJson(`/api/jobs/${encodeURIComponent(jobId)}`);
    }
    FanboxUI.getJob = getJob;
    function startBackupJob(payload, sessionToken) {
        return requestJson("/api/jobs/backup", {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-Fanbox-Token": sessionToken },
            body: JSON.stringify(payload),
        });
    }
    FanboxUI.startBackupJob = startBackupJob;
    function startVerificationJob(sessionToken) {
        return requestJson("/api/jobs/verify", {
            method: "POST", headers: { "X-Fanbox-Token": sessionToken },
        });
    }
    FanboxUI.startVerificationJob = startVerificationJob;
    function cancelJob(jobId, sessionToken) {
        return requestJson(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, {
            method: "POST", headers: { "X-Fanbox-Token": sessionToken },
        });
    }
    FanboxUI.cancelJob = cancelJob;
    function retryJob(jobId, sessionToken) {
        return requestJson(`/api/jobs/${encodeURIComponent(jobId)}/retry`, {
            method: "POST", headers: { "X-Fanbox-Token": sessionToken },
        });
    }
    FanboxUI.retryJob = retryJob;
})(FanboxUI || (FanboxUI = {}));
var FanboxUI;
(function (FanboxUI) {
    function renderPostCard(item, onOpen) {
        return FanboxUI.h("button", {
            type: "button", class: `post-card${item.is_pinned ? " pinned" : ""}`,
            onclick: () => onOpen(item.post_id),
        }, item.cover_url
            ? FanboxUI.h("img", { class: "post-cover", src: item.cover_url, alt: "", loading: "lazy" })
            : FanboxUI.h("span", { class: "post-cover placeholder", "aria-hidden": "true" }, "POST"), FanboxUI.h("span", { class: "post-main" }, FanboxUI.h("span", { class: "post-meta" }, FanboxUI.formatDate(item.published_at), item.is_pinned ? FanboxUI.h("span", { class: "pin-badge" }, "置頂") : null, FanboxUI.h("span", { class: "fee-badge" }, FanboxUI.feeLabel(item.fee_required))), FanboxUI.h("strong", {}, item.title), FanboxUI.h("small", {}, `${item.creator_name} · Post ${item.post_id} · ${item.version_count} 個版本`), item.tags.length ? FanboxUI.h("span", { class: "post-tags", "aria-label": `標籤：${item.tags.join("、")}` }, item.tags.map(tag => FanboxUI.h("span", { class: "post-tag" }, tag))) : null), FanboxUI.h("span", { class: `badge status-${item.status}` }, item.status));
    }
    FanboxUI.renderPostCard = renderPostCard;
    function renderPagination(data, onPage, label = "投稿分頁") {
        if (data.pages <= 1)
            return null;
        const previous = FanboxUI.h("button", {
            type: "button", disabled: data.page <= 1,
            onclick: () => onPage(data.page - 1),
        }, "← 上一頁");
        const next = FanboxUI.h("button", {
            type: "button", disabled: data.page >= data.pages,
            onclick: () => onPage(data.page + 1),
        }, "下一頁 →");
        const pageJump = FanboxUI.h("details", { class: "page-jump" }, FanboxUI.h("summary", { "aria-label": `目前第 ${data.page} 頁，共 ${data.pages} 頁` }, `${data.page} / ${data.pages}`), FanboxUI.h("div", { class: "page-menu", role: "listbox", "aria-label": "跳至頁數" }, Array.from({ length: data.pages }, (_, index) => {
            const page = index + 1;
            return FanboxUI.h("button", {
                type: "button", role: "option", "aria-selected": page === data.page,
                onclick: () => {
                    pageJump.open = false;
                    onPage(page);
                },
            }, String(page));
        })));
        return FanboxUI.h("nav", { class: "pagination", "aria-label": label }, previous, pageJump, next);
    }
    FanboxUI.renderPagination = renderPagination;
    function renderPostListPage(data, actions) {
        const cards = data.items.map(item => renderPostCard(item, actions.onOpen));
        return FanboxUI.h("section", { class: "page" }, FanboxUI.h("header", { class: "heading" }, FanboxUI.h("div", {}, FanboxUI.h("p", { class: "eyebrow" }, "POSTS"), FanboxUI.h("h1", {}, "投稿"), FanboxUI.h("p", {}, `${data.total} 篇備份`))), FanboxUI.h("div", { class: "post-list" }, cards.length ? cards : FanboxUI.h("p", { class: "empty" }, "沒有符合條件的投稿。")), renderPagination(data, actions.onPage));
    }
    FanboxUI.renderPostListPage = renderPostListPage;
    function renderCreatorPostList(data, actions) {
        const cards = data.items.map(item => renderPostCard(item, actions.onOpen));
        const filter = actions.onTag ? FanboxUI.h("section", { class: "tag-filter", "aria-label": "依標籤篩選投稿" }, FanboxUI.h("div", { class: "tag-filter-heading" }, FanboxUI.h("strong", {}, "標籤篩選"), FanboxUI.h("span", {}, actions.activeTag ? `目前：${actions.activeTag}` : "顯示全部投稿")), FanboxUI.h("div", { class: "tag-filter-options" }, FanboxUI.h("button", { type: "button", class: actions.activeTag ? "" : "active",
            "aria-pressed": actions.activeTag ? "false" : "true", onclick: () => actions.onTag?.("") }, `全部 ${data.creator_total}`), data.tag_facets.length ? data.tag_facets.map(facet => FanboxUI.h("button", {
            type: "button", class: actions.activeTag === facet.name ? "active" : "",
            "aria-pressed": actions.activeTag === facet.name ? "true" : "false",
            onclick: () => actions.onTag?.(facet.name),
        }, `${facet.name} ${facet.count}`)) : FanboxUI.h("span", { class: "tag-filter-empty" }, "尚無已保存的投稿標籤"))) : null;
        return FanboxUI.h("div", { class: "creator-posts" }, filter, FanboxUI.h("div", { class: "post-list" }, cards.length ? cards : FanboxUI.h("p", { class: "empty" }, "沒有符合條件的投稿。")), renderPagination(data, actions.onPage, "創作者投稿分頁"));
    }
    FanboxUI.renderCreatorPostList = renderCreatorPostList;
    function richText(block) {
        const fragment = document.createDocumentFragment();
        const text = block.text ?? "";
        const styles = [...(block.styles ?? [])].sort((left, right) => left.offset - right.offset);
        let position = 0;
        for (const style of styles) {
            const start = Math.max(position, style.offset);
            if (start > position)
                fragment.append(text.slice(position, start));
            const end = Math.min(text.length, style.offset + style.length);
            fragment.append(FanboxUI.h("strong", {}, text.slice(start, end)));
            position = end;
        }
        if (position < text.length)
            fragment.append(text.slice(position));
        return fragment;
    }
    function embedView(block, onOpenPost) {
        const preview = block.embed;
        if (!preview || preview.kind !== "fanbox.post" || !preview.post_id) {
            if (!block.url)
                return null;
            return FanboxUI.h("p", { class: "attachment" }, FanboxUI.h("a", { href: block.url, target: "_blank", rel: "noreferrer" }, block.name || block.url));
        }
        const meta = [];
        if (preview.published_at)
            meta.push(FanboxUI.h("span", {}, FanboxUI.formatDate(preview.published_at)));
        if (preview.fee_required !== null && preview.fee_required !== undefined) {
            meta.push(FanboxUI.h("span", { class: "embed-fee" }, FanboxUI.feeLabel(preview.fee_required)));
        }
        if (preview.creator_name)
            meta.push(FanboxUI.h("span", {}, preview.creator_name));
        const attributes = preview.local_available
            ? { href: `#post-${preview.post_id}`, onclick: (event) => {
                    event.preventDefault();
                    onOpenPost(preview.post_id);
                } }
            : { href: preview.fanbox_url || "#", target: "_blank", rel: "noreferrer noopener" };
        return FanboxUI.h("a", { class: "embed-card", ...attributes }, FanboxUI.h("span", { class: "embed-content" }, FanboxUI.h("span", { class: "embed-source" }, preview.local_available ? "FANBOX 投稿 · 本機備份" : "FANBOX 投稿"), FanboxUI.h("strong", {}, preview.title || `Post ${preview.post_id}`), preview.excerpt ? FanboxUI.h("span", { class: "embed-excerpt" }, preview.excerpt) : null, FanboxUI.h("span", { class: "embed-meta" }, meta)), preview.cover_url
            ? FanboxUI.h("img", { class: "embed-cover", src: preview.cover_url, alt: "", loading: "lazy" })
            : FanboxUI.h("span", { class: "embed-cover placeholder", "aria-hidden": "true" }, "FANBOX"));
    }
    function blockView(block, onOpenPost) {
        if (block.type === "image" && block.media_url)
            return FanboxUI.h("figure", {}, FanboxUI.h("a", { href: block.media_url, target: "_blank" }, FanboxUI.h("img", { src: block.media_url, loading: "lazy", alt: block.name || "投稿圖片" })));
        if (block.type === "file" && block.media_url)
            return FanboxUI.h("p", { class: "attachment" }, FanboxUI.h("a", { href: block.media_url }, block.name || block.filename || "下載附件"));
        if (block.type === "separator")
            return FanboxUI.h("hr");
        if (block.type === "quote")
            return FanboxUI.h("blockquote", {}, richText(block));
        if (block.type === "heading")
            return FanboxUI.h(`h${Math.min(Math.max(block.level || 2, 2), 6)}`, {}, richText(block));
        if (block.type === "embed")
            return embedView(block, onOpenPost);
        if (block.text)
            return FanboxUI.h("p", { class: "body-text" }, richText(block));
        return null;
    }
    function navigationView(navigation, placement, onOpenPost) {
        const control = (item, direction) => FanboxUI.h("button", {
            type: "button", class: `post-nav-button ${direction}`, disabled: !item,
            onclick: () => item && onOpenPost(item.post_id),
            title: item?.title || (direction === "previous" ? "已是第一篇" : "已是最後一篇"),
        }, FanboxUI.h("span", {}, direction === "previous" ? "← 上一篇" : "下一篇 →"), FanboxUI.h("strong", {}, item?.title || (direction === "previous" ? "沒有更前面的投稿" : "沒有更後面的投稿")));
        return FanboxUI.h("nav", {
            class: `post-navigation ${placement}`,
            "aria-label": placement === "top" ? "文章頂端導覽" : "文章底部導覽",
        }, control(navigation.previous, "previous"), FanboxUI.h("span", { class: "post-position" }, navigation.position ? `${navigation.position} / ${navigation.total}` : "—"), control(navigation.next, "next"));
    }
    function renderPostReader(post, actions) {
        const body = post.blocks
            .map(block => blockView(block, actions.onOpenPost))
            .filter((block) => block !== null);
        return FanboxUI.h("article", { class: "reader" }, FanboxUI.h("button", { type: "button", class: "back", onclick: actions.onBack }, "← 回到投稿"), navigationView(post.navigation, "top", actions.onOpenPost), post.cover_url ? FanboxUI.h("a", { href: post.cover_url, target: "_blank" }, FanboxUI.h("img", { class: "cover", src: post.cover_url, alt: "投稿封面" })) : null, FanboxUI.h("header", { class: "reader-heading" }, FanboxUI.h("p", { class: "eyebrow" }, `${post.creator_name} · POST ${post.post_id}`), FanboxUI.h("h1", {}, post.title), FanboxUI.h("div", { class: "reader-meta" }, post.is_pinned ? FanboxUI.h("span", { class: "pin-badge" }, "置頂投稿") : null, FanboxUI.h("span", { class: "fee-badge" }, FanboxUI.feeLabel(post.fee_required)), FanboxUI.h("span", {}, `發布 ${FanboxUI.formatDate(post.published_at)}`), FanboxUI.h("span", {}, `更新 ${FanboxUI.formatDate(post.updated_at)}`)), actions.versionSelect), FanboxUI.h("section", { class: "content" }, body.length ? body : FanboxUI.h("p", { class: "empty" }, "此版本沒有可顯示的正文。")), navigationView(post.navigation, "bottom", actions.onOpenPost), FanboxUI.h("footer", {}, FanboxUI.h("a", { href: post.url, target: "_blank", rel: "noreferrer" }, "開啟 FANBOX 原文 ↗")));
    }
    FanboxUI.renderPostReader = renderPostReader;
})(FanboxUI || (FanboxUI = {}));
var FanboxUI;
(function (FanboxUI) {
    function perkStatusClass(status) {
        const safeStatus = ["accessible", "inaccessible", "unavailable", "available", "unknown"].includes(status)
            ? status : "unknown";
        return `perk-status status-${safeStatus}`;
    }
    FanboxUI.perkStatusClass = perkStatusClass;
    function renderCreatorsPage(creators, query, onOpen) {
        const term = query.toLocaleLowerCase();
        const items = creators.filter(item => `${item.name} ${item.creator_id}`.toLocaleLowerCase().includes(term));
        const cards = items.map(item => FanboxUI.h("button", {
            type: "button", class: "creator-card", onclick: () => onOpen(item.creator_id),
        }, item.avatar_url
            ? FanboxUI.h("img", { src: item.avatar_url, alt: "", loading: "lazy" })
            : FanboxUI.h("span", { class: "avatar" }, item.name.slice(0, 1)), FanboxUI.h("span", { class: "post-main" }, FanboxUI.h("strong", {}, item.name), FanboxUI.h("small", {}, `${item.creator_id} · ${item.post_count} 篇投稿`)), FanboxUI.h("span", { class: `badge status-${item.status}` }, item.status)));
        return FanboxUI.h("section", { class: "page" }, FanboxUI.h("header", { class: "heading" }, FanboxUI.h("div", {}, FanboxUI.h("p", { class: "eyebrow" }, "CREATORS"), FanboxUI.h("h1", {}, "創作者"), FanboxUI.h("p", {}, `${items.length} 位符合目前條件`))), FanboxUI.h("div", { class: "creator-grid" }, cards.length ? cards : FanboxUI.h("p", { class: "empty" }, "沒有符合條件的創作者。")));
    }
    FanboxUI.renderCreatorsPage = renderCreatorsPage;
    function renderCreatorShell(creator, tab, content, profile, actions) {
        const tabs = [
            ["profile", "個人資料", "PROFILE"], ["posts", "投稿", "POSTS"],
            ["fancards", "粉絲卡", "FAN CARD"],
        ];
        return FanboxUI.h("section", { class: "page creator-page", "data-creator-id": creator.creator_id }, FanboxUI.h("button", { type: "button", class: "back", onclick: actions.onBack }, "← 回到創作者"), FanboxUI.h("header", { class: `creator-hero${profile?.cover_url ? " has-cover" : ""}` }, profile?.cover_url ? FanboxUI.h("img", { class: "creator-cover", src: profile.cover_url, alt: "" }) : null, creator.avatar_url
            ? FanboxUI.h("img", { src: creator.avatar_url, alt: "" })
            : FanboxUI.h("span", { class: "avatar large" }, creator.name.slice(0, 1)), FanboxUI.h("div", {}, FanboxUI.h("p", { class: "eyebrow" }, `@${creator.creator_id}`), FanboxUI.h("h1", {}, creator.name), FanboxUI.h("p", {}, `${creator.post_count} 篇投稿 · ${creator.fancard_count} 張粉絲卡`)), FanboxUI.h("a", { class: "external-button", href: creator.fanbox_url, target: "_blank", rel: "noreferrer" }, "開啟 FANBOX ↗")), FanboxUI.h("nav", { class: "subnav", "aria-label": "創作者頁面" }, tabs.map(([key, zh, en]) => FanboxUI.h("button", {
            type: "button", class: key === tab ? "active" : "", "data-creator-tab": key,
            onclick: () => actions.onTab(key),
        }, FanboxUI.h("strong", {}, zh), FanboxUI.h("small", {}, en)))), FanboxUI.h("div", { class: "creator-content", "aria-live": "polite" }, content));
    }
    FanboxUI.renderCreatorShell = renderCreatorShell;
    function renderCreatorProfile(creator, profile, versionSelect) {
        const safeLinks = (profile?.profile_items ?? []).filter(item => item.url?.startsWith("https://"));
        const profileImages = (profile?.profile_items ?? []).filter(item => item.image_url);
        return FanboxUI.h("div", { class: "profile-layout" }, !profile ? FanboxUI.h("section", { class: "profile-empty" }, FanboxUI.h("p", { class: "eyebrow" }, "PROFILE ARCHIVE"), FanboxUI.h("h2", {}, "尚未備份個人資料"), FanboxUI.h("p", {}, "執行新版備份後，這裡會顯示離線可讀的自我介紹、連結與歷史版本。")) : null, profile ? FanboxUI.h("section", { class: "info-panel profile-about" }, FanboxUI.h("p", { class: "eyebrow" }, "ABOUT"), FanboxUI.h("h2", {}, "關於創作者"), profileImages.length ? FanboxUI.h("div", { class: "profile-gallery", "aria-label": "創作者 Profile 圖片" }, profileImages.map((item, index) => FanboxUI.h("a", { href: item.image_url, target: "_blank" }, FanboxUI.h("img", { src: item.image_url, alt: item.label || `Profile 圖片 ${index + 1}`, loading: "lazy" })))) : null, profile.description ? FanboxUI.h("p", { class: "body-text" }, profile.description)
            : FanboxUI.h("p", { class: "profile-about-empty" }, "這位創作者尚未提供文字或圖片形式的個人介紹。")) : null, safeLinks.length ? FanboxUI.h("section", { class: "info-panel profile-links" }, FanboxUI.h("p", { class: "eyebrow" }, "LINKS"), FanboxUI.h("h2", {}, "公開連結"), FanboxUI.h("div", { class: "link-grid" }, safeLinks.map(item => FanboxUI.h("a", {
            href: item.url, target: "_blank", rel: "noreferrer",
        }, FanboxUI.h("strong", {}, item.label || item.type || "外部連結"), item.description ? FanboxUI.h("span", {}, item.description) : null)))) : null, profile ? FanboxUI.h("section", { class: "info-panel profile-meta" }, FanboxUI.h("p", { class: "eyebrow" }, "ARCHIVE METADATA"), FanboxUI.h("h2", {}, "狀態與版本"), FanboxUI.h("div", { class: "status-list" }, profile.has_adult_content ? FanboxUI.h("span", { class: "profile-flag adult" }, "成人內容") : FanboxUI.h("span", { class: "profile-flag" }, "一般內容"), FanboxUI.h("span", { class: "profile-flag" }, profile.is_accepting_request ? "開放委託" : "未開放委託"), profile.is_stopped ? FanboxUI.h("span", { class: "profile-flag danger" }, "已停止活動") : FanboxUI.h("span", { class: "profile-flag" }, "持續活動")), FanboxUI.h("dl", {}, FanboxUI.h("div", {}, FanboxUI.h("dt", {}, "捕捉時間"), FanboxUI.h("dd", {}, FanboxUI.formatDate(profile.captured_at))), FanboxUI.h("div", {}, FanboxUI.h("dt", {}, "版本"), FanboxUI.h("dd", {}, versionSelect)))) : null, FanboxUI.h("section", { class: "profile-stats" }, FanboxUI.h("div", {}, FanboxUI.h("strong", {}, creator.post_count), FanboxUI.h("span", {}, "投稿")), FanboxUI.h("div", {}, FanboxUI.h("strong", {}, creator.completed_count), FanboxUI.h("span", {}, "完整備份")), FanboxUI.h("div", {}, FanboxUI.h("strong", {}, creator.fancard_count), FanboxUI.h("span", {}, "粉絲卡"))));
    }
    FanboxUI.renderCreatorProfile = renderCreatorProfile;
    function renderFanCardList(data, actions) {
        const cards = data.items.map(item => FanboxUI.h("button", {
            type: "button", class: "fancard-card", onclick: () => actions.onOpen(item.creator_id, item.target_month),
        }, item.image_url
            ? FanboxUI.h("img", { src: item.image_url, alt: `${item.creator_name} 粉絲卡`, loading: "lazy" })
            : FanboxUI.h("div", { class: "card-placeholder" }, "無卡面"), FanboxUI.h("span", { class: "post-main" }, FanboxUI.h("span", { class: "eyebrow" }, item.target_month), FanboxUI.h("strong", {}, item.plan_title || "方案未命名"), FanboxUI.h("small", {}, `${FanboxUI.feeLabel(item.fee)}/月 · ${item.version_count} 個版本`))));
        return FanboxUI.h("div", { class: "fancard-grid" }, cards.length ? cards : FanboxUI.h("p", { class: "empty" }, "尚未備份粉絲卡。"));
    }
    FanboxUI.renderFanCardList = renderFanCardList;
    function renderFanCardReader(card, actions) {
        const perks = card.perks.length ? FanboxUI.h("section", { class: "perk-section" }, FanboxUI.h("p", { class: "eyebrow" }, "PLAN BENEFITS"), FanboxUI.h("h2", {}, "方案權益"), FanboxUI.h("div", { class: "perk-grid" }, card.perks.map(perk => FanboxUI.h("article", { class: "perk-card" }, FanboxUI.h("div", { class: "perk-card-heading" }, FanboxUI.h("h3", {}, perk.label), FanboxUI.h("span", { class: perkStatusClass(perk.status) }, perk.status_label)), FanboxUI.h("p", {}, perk.description), perk.guidance ? FanboxUI.h("p", { class: "perk-guidance" }, perk.guidance, " ", perk.settings_url ? FanboxUI.h("a", { href: perk.settings_url, target: "_blank", rel: "noreferrer" }, `${perk.settings_label || "帳號設定"} ↗`) : null) : null, perk.action_url && perk.action_label ? FanboxUI.h("a", {
            class: "perk-action", href: perk.action_url, target: "_blank", rel: "noreferrer",
        }, `${perk.action_label} ↗`) : null)))) : null;
        return FanboxUI.h("article", { class: "reader fancard-reader" }, FanboxUI.h("button", { type: "button", class: "back", onclick: actions.onBack }, "← 回到粉絲卡"), card.image_url
            ? FanboxUI.h("a", { href: card.image_url, target: "_blank" }, FanboxUI.h("img", { class: "card-image", src: card.image_url, alt: `${card.creator_name} 粉絲卡` }))
            : FanboxUI.h("div", { class: "card-placeholder large" }, "本月未提供自訂卡面"), FanboxUI.h("header", { class: "reader-heading" }, FanboxUI.h("p", { class: "eyebrow" }, `${card.target_month} · ${card.creator_id}`), FanboxUI.h("h1", {}, card.creator_name), FanboxUI.h("p", {}, `${card.plan_title || "方案未命名"} · ${FanboxUI.feeLabel(card.fee)}/月`), actions.versionSelect), FanboxUI.h("section", { class: "content" }, FanboxUI.h("h2", {}, "方案資訊"), FanboxUI.h("p", { class: "body-text" }, card.description || "（無方案說明）"), card.support_start ? FanboxUI.h("p", {}, `支援開始：${FanboxUI.formatDate(card.support_start)}`) : null, card.support_months.length ? FanboxUI.h("p", {}, `保存月份：${card.support_months.join("、")}`) : null, perks));
    }
    FanboxUI.renderFanCardReader = renderFanCardReader;
})(FanboxUI || (FanboxUI = {}));
var FanboxUI;
(function (FanboxUI) {
    function settingCheckbox(label, checked) {
        const input = FanboxUI.h("input", { type: "checkbox", checked });
        return { input, node: FanboxUI.h("label", { class: "setting-toggle" }, input, FanboxUI.h("span", {}, label)) };
    }
    function settingNumber(label, value, min, max, step = 1, hint = null) {
        const input = FanboxUI.h("input", { type: "number", value, min, max, step });
        return { input, node: FanboxUI.h("label", { class: "setting-field" }, FanboxUI.h("span", {}, label), input, hint ? FanboxUI.h("small", {}, hint) : null) };
    }
    function renderSettingsPage(data, message, activeJob, onSave) {
        const value = data.editable;
        const originalImages = settingCheckbox("下載原始圖片", value.download.original_images);
        const attachments = settingCheckbox("下載附件", value.download.download_attachments);
        const covers = settingCheckbox("下載投稿與 Profile 封面", value.download.download_cover);
        const resume = settingCheckbox("支援續傳", value.download.resume);
        const hashes = settingCheckbox("下載後驗證 SHA-256", value.download.verify_sha256);
        const retries = settingNumber("失敗重試次數", value.download.retry_count, 0, 10);
        const interval = settingNumber("請求間隔（秒）", value.download.request_interval_seconds, 1, 3600, .5, "最低 1 秒；提高此值可降低請求頻率。");
        const timeout = settingNumber("請求逾時（秒）", value.download.timeout_seconds, 5, 600);
        const skipCompleted = settingCheckbox("略過已完成且未更新的投稿", value.sync.skip_completed);
        const checkUpdates = settingCheckbox("檢查遠端更新", value.sync.check_updates);
        const preserveDeleted = settingCheckbox("保留遠端已刪除投稿的本機備份", value.sync.preserve_deleted_posts);
        const rotate = settingCheckbox("輪替創作者處理順序", value.sync.rotate_creators);
        const maxPosts = settingNumber("單次最多下載投稿數", value.sync.max_posts_per_run, 1, 100, 1, "new、updated 與 retry 共用的下載配額；略過的投稿不占配額。新工作可單次覆寫。");
        const unchangedStop = settingNumber("連續未變投稿停止掃描數", value.sync.recent_unchanged_stop_count, 1, 500, 1, "連續遇到已完成且未更新投稿時停止掃描；這不是下載數量。");
        const defaultDryRun = settingCheckbox("完整備份只預覽，不下載", value.backup_defaults.dry_run);
        const defaultProfile = settingCheckbox("預設拉取個人資料", value.backup_defaults.include_profile);
        const defaultFancard = settingCheckbox("預設拉取粉絲卡", value.backup_defaults.include_fancard);
        const markdown = settingCheckbox("產生 Markdown", value.markdown.enabled);
        const frontMatter = settingCheckbox("加入 YAML front matter", value.markdown.yaml_front_matter);
        const relativePaths = settingCheckbox("Markdown 使用相對圖片路徑", value.markdown.relative_image_paths);
        const preserveOrder = settingCheckbox("保留原始內容順序", value.markdown.preserve_original_order);
        const fileLogs = settingCheckbox("寫入檔案日誌", value.logging.write_to_file);
        const keepDays = settingNumber("日誌保留天數", value.logging.keep_days, 1, 365);
        const logLevel = FanboxUI.customSelect({ id: "log-level", label: "日誌等級", value: value.logging.level,
            options: ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"].map(item => ({ value: item, label: item })) });
        const blocked = Boolean(activeJob);
        const feedback = FanboxUI.h("p", { class: "settings-error", role: "alert", hidden: true });
        const form = FanboxUI.h("form", { class: "settings-form", "aria-disabled": blocked, onsubmit: async (event) => {
                event.preventDefault();
                if (blocked)
                    return;
                feedback.hidden = true;
                const error = await onSave({ download: {
                        original_images: originalImages.input.checked, download_attachments: attachments.input.checked,
                        download_cover: covers.input.checked, resume: resume.input.checked, verify_sha256: hashes.input.checked,
                        retry_count: Number(retries.input.value), request_interval_seconds: Number(interval.input.value),
                        timeout_seconds: Number(timeout.input.value),
                    }, sync: {
                        skip_completed: skipCompleted.input.checked, check_updates: checkUpdates.input.checked,
                        preserve_deleted_posts: preserveDeleted.input.checked, rotate_creators: rotate.input.checked,
                        max_posts_per_run: Number(maxPosts.input.value),
                        recent_unchanged_stop_count: Number(unchangedStop.input.value),
                    }, backup_defaults: {
                        dry_run: defaultDryRun.input.checked, include_profile: defaultProfile.input.checked,
                        include_fancard: defaultFancard.input.checked,
                    }, markdown: {
                        enabled: markdown.input.checked, yaml_front_matter: frontMatter.input.checked,
                        relative_image_paths: relativePaths.input.checked, preserve_original_order: preserveOrder.input.checked,
                    }, logging: { level: logLevel.value, write_to_file: fileLogs.input.checked,
                        keep_days: Number(keepDays.input.value) } });
                if (error) {
                    feedback.textContent = `儲存失敗：${error}`;
                    feedback.hidden = false;
                }
            } }, FanboxUI.h("fieldset", { disabled: blocked }, FanboxUI.h("section", { class: "settings-card backup-settings" }, FanboxUI.h("p", { class: "eyebrow" }, "BACKUP"), FanboxUI.h("h2", {}, "備份"), FanboxUI.h("section", { class: "settings-section" }, FanboxUI.h("h3", {}, "工作數量與掃描停止"), FanboxUI.h("p", { class: "settings-section-description" }, "下載配額與掃描停止門檻是兩個不同概念。"), FanboxUI.h("div", { class: "settings-grid two-columns" }, maxPosts.node, unchangedStop.node)), FanboxUI.h("section", { class: "settings-section" }, FanboxUI.h("h3", {}, "新工作預設"), FanboxUI.h("p", { class: "settings-section-description" }, "每次進入新工作表單時套用；重試仍沿用原工作設定。"), FanboxUI.h("div", { class: "setting-toggles" }, defaultDryRun.node, defaultProfile.node, defaultFancard.node)), FanboxUI.h("section", { class: "settings-section" }, FanboxUI.h("h3", {}, "內容與保存"), FanboxUI.h("div", { class: "setting-toggles" }, originalImages.node, attachments.node, covers.node, resume.node, hashes.node, preserveDeleted.node)), FanboxUI.h("section", { class: "settings-section" }, FanboxUI.h("h3", {}, "更新判定與處理順序"), FanboxUI.h("div", { class: "setting-toggles" }, skipCompleted.node, checkUpdates.node, rotate.node)), FanboxUI.h("section", { class: "settings-section" }, FanboxUI.h("h3", {}, "網路與失敗處理"), FanboxUI.h("div", { class: "settings-grid" }, retries.node, interval.node, timeout.node))), FanboxUI.h("section", { class: "settings-card" }, FanboxUI.h("p", { class: "eyebrow" }, "OUTPUT & LOGGING"), FanboxUI.h("h2", {}, "輸出與紀錄"), FanboxUI.h("section", { class: "settings-section" }, FanboxUI.h("h3", {}, "Markdown"), FanboxUI.h("div", { class: "setting-toggles" }, markdown.node, frontMatter.node, relativePaths.node, preserveOrder.node)), FanboxUI.h("section", { class: "settings-section" }, FanboxUI.h("h3", {}, "日誌"), FanboxUI.h("div", { class: "settings-grid two-columns" }, FanboxUI.h("label", { class: "setting-field" }, FanboxUI.h("span", {}, "日誌等級"), logLevel), keepDays.node), FanboxUI.h("div", { class: "setting-toggles" }, fileLogs.node))), FanboxUI.h("div", { class: "settings-actions" }, FanboxUI.h("button", { type: "submit", class: "primary",
            disabled: !data.writable || blocked }, "儲存設定"), !data.writable ? FanboxUI.h("span", { class: "notice" }, "目前伺服器未指定可寫入的設定檔。") : null, blocked ? FanboxUI.h("span", { class: "notice" }, "工作結束後即可儲存設定。") : null, feedback)));
        return FanboxUI.h("section", { class: "page settings-page" }, FanboxUI.h("header", { class: "heading" }, FanboxUI.h("div", {}, FanboxUI.h("p", { class: "eyebrow" }, "LOCAL SETTINGS"), FanboxUI.h("h1", {}, "設定"), FanboxUI.h("p", {}, "只顯示安全的一般選項；儲存與認證路徑維持唯讀。"))), message ? FanboxUI.h("p", { class: "settings-saved", role: "status" }, message) : null, FanboxUI.activeJobNotice(activeJob), FanboxUI.h("section", { class: "settings-paths" }, FanboxUI.h("div", {}, FanboxUI.h("span", {}, "封存目錄"), FanboxUI.h("code", {}, data.storage.output_dir)), FanboxUI.h("div", {}, FanboxUI.h("span", {}, "資料庫"), FanboxUI.h("code", {}, data.storage.database)), FanboxUI.h("div", {}, FanboxUI.h("span", {}, "設定檔"), FanboxUI.h("code", {}, data.config_path || "未指定"))), form);
    }
    FanboxUI.renderSettingsPage = renderSettingsPage;
})(FanboxUI || (FanboxUI = {}));
var FanboxUI;
(function (FanboxUI) {
    const activeStatuses = new Set(["queued", "running", "cancelling"]);
    function jobLabel(job) {
        if (job.kind === "verify")
            return "封存完整性驗證";
        return ({ profile: "個人資料拉取", fancard: "粉絲卡拉取" })[job.request.mode ?? ""]
            || (job.request.dry_run ? "完整備份預覽" : "完整備份");
    }
    FanboxUI.jobLabel = jobLabel;
    function activeJobNotice(job) {
        if (!job)
            return null;
        return FanboxUI.h("p", { class: "global-job-notice", role: "status" }, FanboxUI.h("strong", {}, `目前工作：${jobLabel(job)}`), `（${statusText(job.status)}）`, FanboxUI.h("span", {}, "同一時間只允許一項寫入或維護操作；完成、失敗或取消後會自動解鎖。"));
    }
    FanboxUI.activeJobNotice = activeJobNotice;
    function valueNumber(data, key) {
        const value = Number(data[key] ?? 0);
        return Number.isFinite(value) ? value : 0;
    }
    function valueString(data, key) {
        const value = data[key];
        return value === null || value === undefined ? "" : String(value);
    }
    function isRecord(value) {
        return Boolean(value) && typeof value === "object" && !Array.isArray(value);
    }
    function stopReasonLabel(reason) {
        return { limit_reached: "已達下載上限", remote_exhausted: "遠端頁面已掃描完畢",
            backfill_completed: "歷史回補已完成", unchanged_threshold: "已達連續未變停止門檻",
            eligible_exhausted: "其餘投稿不需下載" }[reason] || "掃描完成";
    }
    FanboxUI.stopReasonLabel = stopReasonLabel;
    function isActiveJob(job) {
        return Boolean(job && activeStatuses.has(job.status));
    }
    FanboxUI.isActiveJob = isActiveJob;
    function requestCreators(request) {
        if (Array.isArray(request.creators))
            return [...new Set(request.creators.filter(Boolean))];
        return request.creator ? [request.creator] : [];
    }
    FanboxUI.requestCreators = requestCreators;
    function filterBackupCreators(creators, query, selected) {
        const term = query.trim().toLocaleLowerCase();
        const chosen = new Set(selected);
        return creators.filter(item => !chosen.has(item.creator_id)
            && (!term || `${item.name} ${item.creator_id}`.toLocaleLowerCase().includes(term)));
    }
    FanboxUI.filterBackupCreators = filterBackupCreators;
    function jobCreatorLabel(job, creators) {
        const selected = requestCreators(job.request);
        if (!selected.length)
            return "全部創作者";
        if (selected.length > 1)
            return `${selected.length} 位創作者`;
        const item = creators.find(creator => creator.creator_id === selected[0]);
        return item ? `${item.name}（@${item.creator_id}）` : `@${selected[0]}`;
    }
    FanboxUI.jobCreatorLabel = jobCreatorLabel;
    function statusText(status) {
        return ({ queued: "等待中", running: "執行中", cancelling: "停止中", completed: "已完成",
            failed: "失敗", cancelled: "已取消", interrupted: "已中斷" })[status];
    }
    FanboxUI.statusText = statusText;
    function eventLabel(event) {
        const data = event.data;
        if (event.kind === "job_started")
            return `工作開始（${valueString(data, "scope")}）`;
        if (event.kind === "plan_ready")
            return `計畫：上限 ${valueNumber(data, "requested_max_posts")}、發現 ${valueNumber(data, "discovered")}、符合 ${valueNumber(data, "eligible")}、選取 ${valueNumber(data, "selected")}、略過 ${valueNumber(data, "skipped")}（${stopReasonLabel(valueString(data, "stop_reason"))}）`;
        if (event.kind === "fancard_finished")
            return `粉絲卡 ${valueString(data, "creator_id")}：${valueString(data, "status")}`;
        if (event.kind === "profile_started")
            return `正在備份 @${valueString(data, "creator_id")} 的個人資料`;
        if (event.kind === "profile_finished")
            return `個人資料 ${valueString(data, "creator_id")}：${valueString(data, "status")}（v${String(valueNumber(data, "version")).padStart(4, "0")}）`;
        if (event.kind === "profile_warning")
            return `個人資料警告：${valueString(data, "creator_id")}：${valueString(data, "message")}`;
        if (event.kind === "asset_progress") {
            const total = valueNumber(data, "total");
            return `${valueString(data, "name")}：${FanboxUI.humanBytes(valueNumber(data, "downloaded"))}${total ? ` / ${FanboxUI.humanBytes(total)}` : ""}`;
        }
        if (event.kind === "item_finished")
            return `Post ${valueString(data, "post_id")}：${data.unchanged ? "內容未變" : valueString(data, "error") || valueString(data, "status")}`;
        if (event.kind === "warning")
            return `警告：${data.creator_id ? `${valueString(data, "creator_id")}：` : ""}${valueString(data, "message")}`;
        if (event.kind === "job_finished")
            return data.dry_run ? "預覽完成" : `完成：成功 ${valueNumber(data, "success")}、未完成 ${valueNumber(data, "failure")}`;
        if (event.kind === "job_failed")
            return `錯誤：${valueString(data, "error")}`;
        if (event.kind === "job_cancelled")
            return "工作已取消";
        if (event.kind === "job_interrupted")
            return "伺服器曾重新啟動，工作已中斷且未自動重跑";
        return event.kind;
    }
    function eventTone(kind) {
        if (["warning", "profile_warning", "job_interrupted"].includes(kind))
            return "warning";
        if (kind === "job_failed")
            return "error";
        if (kind === "plan_ready")
            return "plan";
        if (kind === "job_finished")
            return "success";
        return "neutral";
    }
    function planSummary(event, creators) {
        if (!event)
            return null;
        const data = event.data;
        const creatorNames = new Map(creators.map(item => [item.creator_id, item.name]));
        const metrics = [["新增", valueNumber(data, "new"), "new"],
            ["更新", valueNumber(data, "updated"), "updated"], ["重試", valueNumber(data, "retried"), "retry"],
            ["略過", valueNumber(data, "skipped"), "skipped"]];
        const scans = Array.isArray(data.scans) ? data.scans.filter(isRecord) : [];
        const rows = scans.map(scan => {
            const creatorId = valueString(scan, "creator_id");
            const profile = valueString(scan, "profile");
            return FanboxUI.h("tr", {}, FanboxUI.h("th", { scope: "row" }, FanboxUI.h("strong", {}, creatorNames.get(creatorId) || creatorId), FanboxUI.h("small", {}, creatorId)), FanboxUI.h("td", { class: "number new" }, valueNumber(scan, "new")), FanboxUI.h("td", { class: "number updated" }, valueNumber(scan, "updated")), FanboxUI.h("td", { class: "number retry" }, valueNumber(scan, "retry")), FanboxUI.h("td", { class: "number skipped" }, valueNumber(scan, "skipped")), FanboxUI.h("td", { class: "number" }, valueNumber(scan, "discovered")), FanboxUI.h("td", { class: `profile-result ${profile || "none"}` }, profile || "—"));
        });
        const creatorCount = Array.isArray(data.creators) ? data.creators.length : valueNumber(data, "creators") || rows.length;
        const requested = valueNumber(data, "requested_max_posts");
        const selected = valueNumber(data, "selected");
        const reason = stopReasonLabel(valueString(data, "stop_reason"));
        return FanboxUI.h("section", { class: "plan-panel" }, FanboxUI.h("div", { class: "section-title" }, FanboxUI.h("div", {}, FanboxUI.h("p", { class: "eyebrow" }, "BACKUP PLAN"), FanboxUI.h("h2", {}, "本次備份摘要")), FanboxUI.h("span", { class: "plan-creators" }, `${creatorCount} 位創作者`)), FanboxUI.h("p", { class: "plan-capacity" }, `上限 ${requested}／發現 ${valueNumber(data, "discovered")}／符合 ${valueNumber(data, "eligible")}／選取 ${selected}／略過 ${valueNumber(data, "skipped")}`, selected < requested ? FanboxUI.h("strong", {}, reason) : null), FanboxUI.h("div", { class: "metric-grid" }, metrics.map(([label, value, tone]) => FanboxUI.h("div", { class: `metric ${tone}` }, FanboxUI.h("strong", {}, value), FanboxUI.h("span", {}, label)))), rows.length ? FanboxUI.h("div", { class: "table-scroll" }, FanboxUI.h("table", { class: "plan-table" }, FanboxUI.h("thead", {}, FanboxUI.h("tr", {}, FanboxUI.h("th", {}, "創作者"), FanboxUI.h("th", {}, "新增"), FanboxUI.h("th", {}, "更新"), FanboxUI.h("th", {}, "重試"), FanboxUI.h("th", {}, "略過"), FanboxUI.h("th", {}, "發現"), FanboxUI.h("th", {}, "Profile"))), FanboxUI.h("tbody", {}, rows))) : null);
    }
    function currentActivity(job) {
        const event = [...(job.events ?? [])].reverse().find(item => ["asset_progress", "item_finished", "fancard_finished",
            "profile_started", "profile_finished", "profile_warning", "warning", "job_failed", "job_finished",
            "job_cancelled", "job_interrupted", "job_started"].includes(item.kind));
        if (!event)
            return FanboxUI.h("section", { class: "current-activity" }, FanboxUI.h("p", { class: "eyebrow" }, "CURRENT"), FanboxUI.h("h2", {}, "正在準備備份…"));
        const isAsset = event.kind === "asset_progress";
        const total = valueNumber(event.data, "total");
        const downloaded = valueNumber(event.data, "downloaded");
        const percent = total > 0 ? Math.min(100, Math.max(0, downloaded / total * 100)) : null;
        return FanboxUI.h("section", { class: `current-activity tone-${eventTone(event.kind)}` }, FanboxUI.h("div", { class: "activity-top" }, FanboxUI.h("div", {}, FanboxUI.h("p", { class: "eyebrow" }, isAsset ? "CURRENT DOWNLOAD" : "CURRENT STATUS"), FanboxUI.h("h2", {}, isAsset ? valueString(event.data, "name") || "下載資源" : eventLabel(event))), FanboxUI.h("time", {}, FanboxUI.formatDate(event.timestamp))), isAsset ? FanboxUI.h("div", { class: "progress-area" }, FanboxUI.h("div", { class: "progress-label" }, FanboxUI.h("span", {}, `${FanboxUI.humanBytes(downloaded)}${total ? ` / ${FanboxUI.humanBytes(total)}` : ""}`), FanboxUI.h("strong", {}, percent === null ? "下載中" : `${percent.toFixed(1)}%`)), FanboxUI.h("progress", { max: total || 1, value: downloaded, "aria-label": "目前資源下載進度" })) : null);
    }
    function eventLog(events) {
        const rows = events.map(item => FanboxUI.h("li", { class: `event-${eventTone(item.kind)}` }, FanboxUI.h("span", { class: "event-mark", "aria-hidden": "true" }), FanboxUI.h("time", {}, FanboxUI.formatDate(item.timestamp)), FanboxUI.h("span", { class: "event-kind" }, item.kind === "plan_ready" ? "計畫"
            : ["warning", "profile_warning", "job_interrupted"].includes(item.kind) ? "警告" : item.kind === "job_failed" ? "錯誤" : "紀錄"), FanboxUI.h("span", { class: "event-message" }, eventLabel(item))));
        const details = FanboxUI.h("details", { class: "job-details" }, FanboxUI.h("summary", {}, FanboxUI.h("span", {}, "詳細執行紀錄"), FanboxUI.h("small", {}, `${events.length} 筆`)), FanboxUI.h("ol", { class: "event-log" }, rows.length ? rows : FanboxUI.h("li", { class: "event-neutral" }, "等待工作事件…")));
        details.addEventListener("toggle", () => {
            if (!details.open)
                return;
            const log = details.querySelector(".event-log");
            if (log)
                log.scrollTop = log.scrollHeight;
        });
        return details;
    }
    function jobPart(node, name) {
        node.dataset.jobPart = name;
        return node;
    }
    function updateJobPage(current, next, preserveHistory = false) {
        const currentParts = new Map([...current.children].map(node => [node.dataset.jobPart, node]));
        for (const item of [...next.children]) {
            const nextPart = item;
            const name = nextPart.dataset.jobPart;
            const currentPart = currentParts.get(name);
            if (!currentPart) {
                current.append(nextPart);
                continue;
            }
            if (name === "history" && preserveHistory) {
                currentParts.delete(name);
                continue;
            }
            if (name === "details") {
                const details = currentPart;
                const wasOpen = details.open;
                const log = details.querySelector(".event-log");
                const previousScrollTop = log?.scrollTop ?? 0;
                const nearBottom = log ? log.scrollHeight - log.scrollTop - log.clientHeight < 40 : true;
                currentPart.replaceChildren(...nextPart.childNodes);
                details.open = wasOpen;
                const updatedLog = details.querySelector(".event-log");
                if (wasOpen && updatedLog)
                    updatedLog.scrollTop = nearBottom ? updatedLog.scrollHeight : previousScrollTop;
            }
            else
                currentPart.replaceWith(nextPart);
            currentParts.delete(name);
        }
        for (const stale of currentParts.values())
            stale.remove();
    }
    FanboxUI.updateJobPage = updateJobPage;
    function jobModeLabel(job) {
        return ({ profile: "只拉取 Profile", fancard: "只拉取 Fan Card" })[job.request.mode ?? ""]
            || (job.request.dry_run ? "完整備份預覽" : "完整備份");
    }
    function jobHistory(jobs, selectedId, creators, filterValue, actions) {
        const active = jobs.find(isActiveJob);
        const filter = FanboxUI.customSelect({ id: "job-history-filter", label: "篩選工作狀態", value: filterValue, options: [
                { value: "all", label: "全部狀態" }, { value: "completed", label: "已完成" }, { value: "failed", label: "失敗" },
                { value: "interrupted", label: "已中斷" }, { value: "cancelled", label: "已取消" },
            ], onChange: actions.onFilter });
        const filtered = jobs.filter(item => filterValue === "all" || item.status === filterValue);
        const rows = filtered.map(item => FanboxUI.h("button", { type: "button", class: `history-row${item.job_id === selectedId ? " selected" : ""}`,
            disabled: Boolean(active && item.job_id !== active.job_id), onclick: () => actions.onShow(item.job_id) }, FanboxUI.h("span", { class: `history-status status-${item.status}` }, statusText(item.status)), FanboxUI.h("span", { class: "history-main" }, FanboxUI.h("strong", {}, jobModeLabel(item)), FanboxUI.h("small", {}, `${jobCreatorLabel(item, creators)} · ${FanboxUI.formatDate(item.created_at)}`)), FanboxUI.h("span", { class: "history-result" }, item.result
            ? `成功 ${item.result.success ?? 0} · 失敗 ${item.result.failure ?? 0}` : item.error ? "查看錯誤" : "查看詳情")));
        return FanboxUI.h("section", { class: "job-history" }, FanboxUI.h("div", { class: "history-heading" }, FanboxUI.h("div", {}, FanboxUI.h("p", { class: "eyebrow" }, "JOB HISTORY"), FanboxUI.h("h2", {}, "備份紀錄")), filter), active ? FanboxUI.h("p", { class: "history-notice" }, "工作執行期間會鎖定其他歷史項目，避免離開目前進度畫面。") : null, FanboxUI.h("div", { class: "history-list" }, rows.length ? rows : FanboxUI.h("p", { class: "empty compact" }, "沒有符合條件的工作紀錄。")));
    }
    function renderBackupJobPage(job, creators, jobs, filterValue, activeJob, actions) {
        const active = isActiveJob(job);
        const blocked = Boolean(activeJob && activeJob.job_id !== job.job_id);
        const plan = (job.events ?? []).find(item => item.kind === "plan_ready");
        const retryable = ["failed", "cancelled", "interrupted"].includes(job.status);
        const selectedCreators = requestCreators(job.request);
        const creatorNames = new Map(creators.map(item => [item.creator_id, item.name]));
        const controls = FanboxUI.h("div", { class: "job-actions" }, active ? FanboxUI.h("button", { type: "button", class: "danger", onclick: () => actions.onCancel(job.job_id) }, job.status === "cancelling" ? "正在安全停止…" : "安全停止") : null, retryable ? FanboxUI.h("button", { type: "button", class: "retry", disabled: blocked,
            onclick: () => actions.onRetry(job.job_id) }, "使用相同設定重試") : null, !active ? FanboxUI.h("button", { type: "button", disabled: blocked, onclick: actions.onNew }, "建立新工作") : null, FanboxUI.h("button", { type: "button", class: "secondary", disabled: active, onclick: actions.onHistory }, "工作歷史"));
        return FanboxUI.h("section", { class: "page backup-page", "data-job-id": job.job_id }, jobPart(FanboxUI.h("header", { class: "heading job-heading" }, FanboxUI.h("div", {}, FanboxUI.h("p", { class: "eyebrow" }, "BACKUP JOB"), FanboxUI.h("h1", {}, "備份工作"), FanboxUI.h("p", {}, jobModeLabel(job))), FanboxUI.h("span", { class: `job-status status-${job.status}` }, statusText(job.status))), "header"), jobPart(activeJobNotice(blocked ? activeJob : null) || FanboxUI.h("div", { hidden: true }), "global-active"), jobPart(FanboxUI.h("section", { class: "job-scope" }, FanboxUI.h("p", { class: "eyebrow" }, "BACKUP SCOPE"), FanboxUI.h("h2", {}, jobCreatorLabel(job, creators)), selectedCreators.length
            ? FanboxUI.h("ul", {}, selectedCreators.map(id => FanboxUI.h("li", {}, FanboxUI.h("strong", {}, creatorNames.get(id) || id), FanboxUI.h("span", {}, `@${id}`))))
            : FanboxUI.h("p", {}, "本次工作涵蓋全部支援中的創作者。")), "scope"), jobPart(planSummary(plan, creators) || FanboxUI.h("div", { hidden: true }), "plan"), jobPart(currentActivity(job), "activity"), jobPart(FanboxUI.h("p", { class: "job-error", hidden: !job.error }, FanboxUI.h("strong", {}, "錯誤："), job.error || ""), "error"), jobPart(FanboxUI.h("div", { class: "result-strip", hidden: !job.result }, job.result ? [
            FanboxUI.h("span", {}, "選取 ", FanboxUI.h("strong", {}, job.result.selected ?? 0)), FanboxUI.h("span", {}, "成功 ", FanboxUI.h("strong", {}, job.result.success ?? 0)),
            FanboxUI.h("span", {}, "未變 ", FanboxUI.h("strong", {}, job.result.unchanged ?? 0)), FanboxUI.h("span", {}, "失敗 ", FanboxUI.h("strong", {}, job.result.failure ?? 0)),
        ] : null), "result"), jobPart(controls, "actions"), jobPart(eventLog(job.events ?? []), "details"));
    }
    FanboxUI.renderBackupJobPage = renderBackupJobPage;
    function renderBackupFormPage(creators, defaults, activeJob, actions) {
        const blocked = Boolean(activeJob);
        const selected = [];
        const dryRun = FanboxUI.h("input", { id: "backup-dry-run", type: "checkbox", checked: defaults.dryRun });
        const includeProfile = FanboxUI.h("input", { id: "backup-include-profile", type: "checkbox", checked: defaults.includeProfile });
        const includeFancard = FanboxUI.h("input", { id: "backup-include-fancard", type: "checkbox", checked: defaults.includeFancard });
        const maxPosts = FanboxUI.h("input", { id: "backup-max-posts", type: "number", min: 1, max: 100, value: defaults.maxPosts });
        const selectedList = FanboxUI.h("div", { class: "selected-creator-list" });
        const count = FanboxUI.h("strong", {}, "已選 0 位");
        const input = FanboxUI.h("input", { type: "search", placeholder: "搜尋名稱或 Creator ID…", autocomplete: "off",
            role: "combobox", "aria-label": "搜尋並加入創作者", "aria-expanded": "false" });
        const menu = FanboxUI.h("div", { class: "creator-combobox-menu", role: "listbox", hidden: true });
        const combobox = FanboxUI.h("div", { class: "creator-combobox form-field" }, FanboxUI.h("span", {}, "加入創作者"), input, menu);
        let activeIndex = 0;
        let listeningOutside = false;
        const closeMenu = () => {
            menu.hidden = true;
            input.setAttribute("aria-expanded", "false");
            if (listeningOutside) {
                document.removeEventListener("pointerdown", handleOutsidePointer);
                listeningOutside = false;
            }
        };
        const handleOutsidePointer = (event) => {
            if (!combobox.isConnected || !combobox.contains(event.target))
                closeMenu();
        };
        const openMenu = () => {
            renderCandidates();
            menu.hidden = false;
            input.setAttribute("aria-expanded", "true");
            if (!listeningOutside) {
                document.addEventListener("pointerdown", handleOutsidePointer);
                listeningOutside = true;
            }
        };
        const renderSelected = () => {
            count.textContent = `已選 ${selected.length} 位`;
            selectedList.replaceChildren(...(selected.length ? selected.map(id => {
                const creator = creators.find(item => item.creator_id === id);
                return FanboxUI.h("div", { class: "selected-creator" }, FanboxUI.h("button", { type: "button", class: "remove-creator",
                    "aria-label": `移除 ${creator?.name || id} @${id}`, onclick: () => {
                        selected.splice(selected.indexOf(id), 1);
                        renderSelected();
                        renderCandidates();
                    } }, "×"), FanboxUI.h("span", {}, FanboxUI.h("strong", {}, creator?.name || id), FanboxUI.h("small", {}, `@${id}`)));
            }) : [FanboxUI.h("p", { class: "empty compact" }, "尚未指定創作者；將備份全部支援中的創作者")]));
        };
        const choose = (id) => {
            if (!selected.includes(id))
                selected.push(id);
            input.value = "";
            activeIndex = 0;
            renderSelected();
            renderCandidates();
            input.focus();
            closeMenu();
        };
        const renderCandidates = () => {
            const matches = filterBackupCreators(creators, input.value, selected);
            activeIndex = Math.min(activeIndex, Math.max(0, matches.length - 1));
            menu.replaceChildren(...(matches.length ? matches.map((item, index) => FanboxUI.h("button", { type: "button", role: "option",
                class: index === activeIndex ? "active" : "", "aria-selected": index === activeIndex ? "true" : "false",
                onclick: () => choose(item.creator_id) }, FanboxUI.h("strong", {}, item.name), FanboxUI.h("small", {}, `@${item.creator_id}`)))
                : [FanboxUI.h("p", { class: "empty compact" }, "沒有符合的創作者。")]));
        };
        input.addEventListener("focus", openMenu);
        input.addEventListener("click", () => { if (menu.hidden)
            openMenu(); });
        input.addEventListener("input", () => { activeIndex = 0; openMenu(); });
        input.addEventListener("keydown", event => {
            const matches = filterBackupCreators(creators, input.value, selected);
            if (event.key === "Escape") {
                closeMenu();
                return;
            }
            if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                event.preventDefault();
                activeIndex = Math.max(0, Math.min(matches.length - 1, activeIndex + (event.key === "ArrowDown" ? 1 : -1)));
                renderCandidates();
                return;
            }
            const candidate = matches[activeIndex];
            if (event.key === "Enter" && !menu.hidden && candidate) {
                event.preventDefault();
                choose(candidate.creator_id);
            }
        });
        renderSelected();
        const start = (mode, preview) => actions.onStart([...selected], preview, Number(maxPosts.value), mode, includeProfile.checked, includeFancard.checked);
        return FanboxUI.h("section", { class: "page backup-page" }, FanboxUI.h("header", { class: "heading" }, FanboxUI.h("div", {}, FanboxUI.h("p", { class: "eyebrow" }, "BACKUP CONTROL"), FanboxUI.h("h1", {}, "開始備份"), FanboxUI.h("p", {}, "選擇本次範圍與內容；未指定創作者時會備份全部支援中的創作者。")), FanboxUI.h("button", { type: "button", class: "primary", onclick: actions.onHistory }, "工作歷史")), activeJobNotice(activeJob), FanboxUI.h("form", { class: "backup-form", onsubmit: (event) => { event.preventDefault(); if (!blocked)
                start("full", dryRun.checked); } }, combobox, FanboxUI.h("section", { class: "selected-creators", "aria-live": "polite" }, FanboxUI.h("div", { class: "selected-creators-heading" }, FanboxUI.h("span", {}, "本次備份清單"), count), selectedList), FanboxUI.h("label", {}, FanboxUI.h("span", {}, "本次投稿上限"), maxPosts), FanboxUI.h("label", { class: "checkbox" }, dryRun, FanboxUI.h("span", {}, "完整備份只預覽，不下載")), FanboxUI.h("label", { class: "checkbox" }, includeProfile, FanboxUI.h("span", {}, "拉取個人資料")), FanboxUI.h("label", { class: "checkbox" }, includeFancard, FanboxUI.h("span", {}, "拉取粉絲卡")), FanboxUI.h("button", { type: "submit", class: "primary", disabled: blocked }, "開始完整備份"), FanboxUI.h("div", { class: "metadata-actions" }, FanboxUI.h("div", {}, FanboxUI.h("strong", {}, "單項拉取"), FanboxUI.h("small", {}, "立即寫入封存，不掃描或下載投稿。")), FanboxUI.h("div", { class: "metadata-buttons" }, FanboxUI.h("button", { type: "button", disabled: blocked,
            onclick: () => start("profile", false) }, "拉取個人資料"), FanboxUI.h("button", { type: "button", disabled: blocked, onclick: () => start("fancard", false) }, "拉取粉絲卡")))), FanboxUI.h("p", { class: "notice" }, "同一時間只允許一個備份工作；安全停止會在目前投稿處理完成後生效。"));
    }
    FanboxUI.renderBackupFormPage = renderBackupFormPage;
    function renderBackupHistoryPage(jobs, creators, filterValue, actions) {
        return FanboxUI.h("section", { class: "page backup-page" }, FanboxUI.h("header", { class: "heading" }, FanboxUI.h("div", {}, FanboxUI.h("p", { class: "eyebrow" }, "JOB HISTORY"), FanboxUI.h("h1", {}, "工作歷史"), FanboxUI.h("p", {}, "選擇一筆工作查看進度、結果與完整執行紀錄。")), FanboxUI.h("button", { type: "button", class: "primary", onclick: actions.onNew }, "建立新工作")), jobHistory(jobs, null, creators, filterValue, actions));
    }
    FanboxUI.renderBackupHistoryPage = renderBackupHistoryPage;
    function verificationHistory(jobs, selectedId, onShow) {
        const active = jobs.find(isActiveJob);
        const rows = jobs.map(item => FanboxUI.h("button", { type: "button", class: `history-row${item.job_id === selectedId ? " selected" : ""}`,
            disabled: Boolean(active && item.job_id !== active.job_id), onclick: () => onShow(item.job_id) }, FanboxUI.h("span", { class: `history-status status-${item.status}` }, statusText(item.status)), FanboxUI.h("span", { class: "history-main" }, FanboxUI.h("strong", {}, "封存完整性驗證"), FanboxUI.h("small", {}, FanboxUI.formatDate(item.created_at))), FanboxUI.h("span", { class: "history-result" }, item.result
            ? item.result.passed ? "驗證通過" : `${item.result.issue_count ?? 0} 個問題` : item.error ? "查看錯誤" : "查看進度")));
        return FanboxUI.h("section", { class: "job-history" }, FanboxUI.h("div", { class: "history-heading" }, FanboxUI.h("div", {}, FanboxUI.h("p", { class: "eyebrow" }, "VERIFY HISTORY"), FanboxUI.h("h2", {}, "驗證歷史"))), active ? FanboxUI.h("p", { class: "history-notice" }, "驗證執行期間會鎖定其他歷史項目。") : null, FanboxUI.h("div", { class: "history-list" }, rows.length ? rows : FanboxUI.h("p", { class: "empty compact" }, "尚無驗證紀錄。")));
    }
    function renderMaintenancePage(job, jobs, activeJob, actions) {
        const active = Boolean(activeJob);
        const result = job?.result;
        const issues = result?.issues ?? [];
        const issueRows = issues.map(item => FanboxUI.h("li", {}, FanboxUI.h("strong", {}, item.reason), FanboxUI.h("code", {}, item.path), item.post_id ? FanboxUI.h("small", {}, `Post ${item.post_id}`) : null));
        return FanboxUI.h("section", { class: "page maintenance-page" }, FanboxUI.h("header", { class: "heading" }, FanboxUI.h("div", {}, FanboxUI.h("p", { class: "eyebrow" }, "ARCHIVE MAINTENANCE"), FanboxUI.h("h1", {}, "封存驗證"), FanboxUI.h("p", {}, "檢查投稿、Profile、粉絲卡、歷史版本與資源的檔案大小及 SHA-256。")), job ? FanboxUI.h("span", { class: `job-status status-${job.status}` }, statusText(job.status)) : null), activeJobNotice(activeJob), FanboxUI.h("section", { class: "maintenance-action" }, FanboxUI.h("div", {}, FanboxUI.h("h2", {}, activeJob?.kind === "verify" ? "正在驗證封存…" : activeJob ? "其他工作執行中" : "完整性檢查"), FanboxUI.h("p", {}, "驗證可能需要一段時間；執行期間不能同時開始備份或修改設定。")), FanboxUI.h("button", { type: "button", class: "primary", disabled: active, onclick: actions.onStart }, activeJob?.kind === "verify" ? "驗證中…" : activeJob ? "目前無法驗證" : "開始驗證")), job?.error ? FanboxUI.h("p", { class: "job-error" }, FanboxUI.h("strong", {}, "錯誤："), job.error) : null, result ? FanboxUI.h("section", { class: `verification-result ${result.passed ? "passed" : "issues"}` }, FanboxUI.h("div", { class: "verification-summary" }, FanboxUI.h("strong", {}, result.passed ? "驗證通過" : `${result.issue_count ?? 0} 個問題`), FanboxUI.h("span", {}, result.passed ? "目前封存未發現完整性問題。" : "請檢查下列缺失或損毀項目。")), issueRows.length ? FanboxUI.h("ul", { class: "verification-issues" }, issueRows) : null, result.truncated ? FanboxUI.h("p", { class: "notice" }, "問題數量過多，目前只顯示前 500 項。") : null) : null, verificationHistory(jobs, job?.job_id ?? null, actions.onShow));
    }
    FanboxUI.renderMaintenancePage = renderMaintenancePage;
})(FanboxUI || (FanboxUI = {}));
var FanboxUI;
(function (FanboxUI) {
    function startApp() {
        const appElement = document.getElementById("app");
        const searchElement = document.getElementById("search");
        const navElement = document.getElementById("nav");
        const tokenMeta = document.querySelector('meta[name="fanbox-session-token"]');
        if (!(appElement instanceof HTMLElement) || !(searchElement instanceof HTMLInputElement)
            || !(navElement instanceof HTMLElement) || !tokenMeta) {
            throw new Error("GUI 缺少必要的頁面元素");
        }
        const app = appElement;
        const search = searchElement;
        const nav = navElement;
        const sessionToken = tokenMeta.content;
        const state = FanboxUI.createInitialState();
        let jobTimer;
        let searchTimer;
        let creatorRequest = 0;
        document.addEventListener("click", event => FanboxUI.closeDropdownsOutside(event.target));
        function errorView(error) {
            app.replaceChildren(FanboxUI.renderError(error, refreshView));
        }
        function setActiveNav(view) {
            FanboxUI.setActiveNavigation(nav, view);
        }
        function setSearch(view) {
            FanboxUI.setSearchState(search, view, state.creatorTab);
        }
        function setView(view) {
            if (jobTimer !== undefined)
                clearTimeout(jobTimer);
            state.view = view;
            state.current = null;
            state.page = 1;
            state.tag = "";
            if (view === "backup") {
                state.backupScreen = "form";
                state.backupJobId = null;
            }
            if (view !== "creator")
                state.creatorId = null;
            setActiveNav(view);
            setSearch(view);
            void refreshView();
        }
        function refreshView(showLoading = true) {
            if (state.view === "backup")
                return loadBackup(showLoading);
            if (state.view === "maintenance")
                return loadMaintenance(showLoading);
            if (state.view === "settings")
                return loadSettings("", showLoading);
            if (state.view === "creators")
                return loadCreators();
            if (state.view === "creator" && state.creatorId)
                return loadCreator(state.creatorId, state.creatorTab);
            return loadPosts();
        }
        function updateActiveJob(jobs) {
            state.activeJob = jobs.find(FanboxUI.isActiveJob) ?? null;
            return state.activeJob;
        }
        function scheduleJobRefresh() {
            if (jobTimer !== undefined)
                clearTimeout(jobTimer);
            if (state.activeJob && ["backup", "maintenance", "settings"].includes(state.view)) {
                jobTimer = window.setTimeout(() => void refreshView(false), 900);
            }
        }
        async function loadPosts() {
            state.current = null;
            app.replaceChildren(FanboxUI.h("p", { class: "empty" }, "正在讀取投稿…"));
            try {
                const params = new URLSearchParams({ page: String(state.page), page_size: "50" });
                if (state.q)
                    params.set("q", state.q);
                const data = await FanboxUI.getPosts(params);
                app.replaceChildren(FanboxUI.renderPostListPage(data, {
                    onOpen: postId => void loadPost(postId),
                    onPage: page => { state.page = page; void loadPosts(); },
                }));
            }
            catch (error) {
                errorView(error);
            }
        }
        async function loadPost(postId, version = null) {
            const creatorContent = state.view === "creator"
                ? app.querySelector(".creator-content") : null;
            const target = creatorContent ?? app;
            const creatorId = state.creatorId;
            const back = creatorContent && creatorId
                ? () => void loadCreator(creatorId, "posts") : () => void loadPosts();
            state.postNavigation = null;
            target.replaceChildren(FanboxUI.h("p", { class: "empty" }, "正在讀取投稿…"));
            try {
                const params = new URLSearchParams();
                if (version !== null)
                    params.set("version", String(version));
                if (creatorContent && creatorId)
                    params.set("creator", creatorId);
                if (state.q)
                    params.set("q", state.q);
                if (creatorContent && state.tag)
                    params.set("tag", state.tag);
                const post = await FanboxUI.getPost(postId, params);
                state.current = postId;
                state.postNavigation = post.navigation;
                const versionSelect = FanboxUI.customSelect({ id: "post-version", label: "版本", value: post.version,
                    options: post.versions.map(item => ({ value: item.number,
                        label: `v${String(item.number).padStart(4, "0")} · ${FanboxUI.formatDate(item.captured_at)}` })),
                    onChange: value => void loadPost(postId, Number(value)) });
                target.replaceChildren(FanboxUI.renderPostReader(post, {
                    onBack: back,
                    onOpenPost: nextPostId => void loadPost(nextPostId),
                    versionSelect,
                }));
            }
            catch (error) {
                errorView(error);
            }
        }
        async function loadCreators() {
            state.current = null;
            app.replaceChildren(FanboxUI.h("p", { class: "empty" }, "正在讀取創作者…"));
            try {
                const data = await FanboxUI.getCreators();
                app.replaceChildren(FanboxUI.renderCreatorsPage(data.items, state.q, creatorId => openCreator(creatorId)));
            }
            catch (error) {
                errorView(error);
            }
        }
        function openCreator(creatorId, tab = "profile") {
            state.view = "creator";
            state.creatorId = creatorId;
            state.creatorTab = tab;
            state.current = null;
            state.page = 1;
            state.q = "";
            state.tag = "";
            state.creator = null;
            state.creatorProfile = null;
            search.value = "";
            setActiveNav("creator");
            setSearch("creator");
            void loadCreator(creatorId, tab);
        }
        function switchCreatorTab(creatorId, tab) {
            state.creatorTab = tab;
            state.current = null;
            state.page = 1;
            state.q = "";
            state.tag = "";
            search.value = "";
            setSearch("creator");
            void loadCreator(creatorId, tab);
        }
        function creatorShell(creator, tab, content, profile = null) {
            return FanboxUI.renderCreatorShell(creator, tab, content, profile, {
                onBack: () => setView("creators"),
                onTab: nextTab => switchCreatorTab(creator.creator_id, nextTab),
            });
        }
        async function loadCreator(creatorId, tab = "profile", profileVersion = null) {
            state.creatorTab = tab;
            setSearch("creator");
            const requestNumber = ++creatorRequest;
            try {
                let creator = state.creator?.creator_id === creatorId ? state.creator : null;
                let heroProfile = state.creatorProfile;
                if (!creator) {
                    app.replaceChildren(FanboxUI.h("p", { class: "empty" }, "正在讀取創作者頁面…"));
                    creator = await FanboxUI.getCreator(creatorId);
                    heroProfile = creator.profile_available ? await FanboxUI.getCreatorProfile(creatorId) : null;
                    if (requestNumber !== creatorRequest || state.creatorId !== creatorId)
                        return;
                    state.creator = creator;
                    state.creatorProfile = heroProfile;
                    app.replaceChildren(creatorShell(creator, tab, FanboxUI.h("p", { class: "empty" }, "正在讀取內容…"), heroProfile));
                }
                let shell = app.querySelector(".creator-page");
                if (!shell || shell.dataset.creatorId !== creatorId) {
                    app.replaceChildren(creatorShell(creator, tab, FanboxUI.h("p", { class: "empty" }, "正在讀取內容…"), heroProfile));
                    shell = app.querySelector(".creator-page");
                }
                if (!shell)
                    return;
                for (const button of shell.querySelectorAll("[data-creator-tab]")) {
                    button.classList.toggle("active", button.dataset.creatorTab === tab);
                }
                const contentRoot = shell.querySelector(".creator-content");
                if (!contentRoot)
                    return;
                contentRoot.replaceChildren(FanboxUI.h("p", { class: "empty" }, "正在讀取內容…"));
                let content;
                if (tab === "posts") {
                    const params = new URLSearchParams({ creator: creatorId, page: String(state.page), page_size: "50" });
                    if (state.q)
                        params.set("q", state.q);
                    if (state.tag)
                        params.set("tag", state.tag);
                    const data = await FanboxUI.getPosts(params);
                    state.page = data.page;
                    content = FanboxUI.renderCreatorPostList(data, {
                        onOpen: postId => void loadPost(postId),
                        onPage: page => { state.page = page; void loadCreator(creatorId, "posts"); },
                        activeTag: state.tag,
                        onTag: tag => {
                            state.tag = tag;
                            state.page = 1;
                            history.pushState({ fanboxCreatorId: creatorId, fanboxCreatorTag: tag }, "", location.href);
                            void loadCreator(creatorId, "posts");
                        },
                    });
                }
                else if (tab === "fancards") {
                    const params = new URLSearchParams({ creator: creatorId });
                    if (state.q)
                        params.set("q", state.q);
                    const data = await FanboxUI.getFanCards(params);
                    content = FanboxUI.renderFanCardList(data, { onOpen: (id, month) => void loadFancard(id, month) });
                }
                else {
                    let profile = heroProfile;
                    if (creator.profile_available && profileVersion !== null) {
                        profile = await FanboxUI.getCreatorProfile(creatorId, profileVersion);
                    }
                    const versionSelect = profile ? FanboxUI.customSelect({ id: "profile-version", label: "Profile 版本", value: profile.version,
                        options: profile.versions.map(item => ({ value: item.number,
                            label: `v${String(item.number).padStart(4, "0")} · ${FanboxUI.formatDate(item.captured_at)}` })),
                        onChange: value => void loadCreator(creatorId, "profile", Number(value)) }) : null;
                    content = FanboxUI.renderCreatorProfile(creator, profile, versionSelect);
                }
                if (requestNumber !== creatorRequest || state.creatorId !== creatorId || state.creatorTab !== tab)
                    return;
                contentRoot.replaceChildren(content);
            }
            catch (error) {
                if (requestNumber !== creatorRequest || state.creatorId !== creatorId)
                    return;
                errorView(error);
            }
        }
        async function loadFancard(creatorId, month, version = null) {
            const creatorContent = state.view === "creator"
                ? app.querySelector(".creator-content") : null;
            const target = creatorContent ?? app;
            target.replaceChildren(FanboxUI.h("p", { class: "empty" }, "正在讀取粉絲卡…"));
            try {
                const card = await FanboxUI.getFanCard(creatorId, month, version);
                state.current = { type: "fancard", creatorId, month };
                const versionSelect = FanboxUI.customSelect({ id: "fancard-version", label: "版本", value: card.version,
                    options: card.versions.map(item => ({ value: item.number,
                        label: `v${String(item.number).padStart(4, "0")} · ${FanboxUI.formatDate(item.captured_at)}` })),
                    onChange: value => void loadFancard(creatorId, month, Number(value)) });
                target.replaceChildren(FanboxUI.renderFanCardReader(card, {
                    onBack: () => void loadCreator(creatorId, "fancards"), versionSelect,
                }));
            }
            catch (error) {
                errorView(error);
            }
        }
        async function showJob(jobId, creators, jobs) {
            try {
                state.backupScreen = "job";
                state.backupJobId = jobId;
                renderJob(await FanboxUI.getJob(jobId), creators, jobs);
            }
            catch (error) {
                errorView(error);
            }
        }
        function renderJob(job, creators, jobs = [job]) {
            if (jobTimer !== undefined)
                clearTimeout(jobTimer);
            const active = FanboxUI.isActiveJob(job);
            const page = FanboxUI.renderBackupJobPage(job, creators, jobs, state.jobFilter, state.activeJob, {
                onCancel: jobId => void cancelBackupJob(jobId),
                onRetry: jobId => void retryBackupJob(jobId),
                onNew: () => { state.backupScreen = "form"; state.backupJobId = null; void loadBackup(false); },
                onHistory: () => { state.backupScreen = "history"; state.backupJobId = null; void loadBackup(false); },
                onShow: jobId => void showJob(jobId, creators, jobs),
                onFilter: value => {
                    state.jobFilter = value;
                    void showJob(job.job_id, creators, jobs);
                },
            });
            const currentPage = app.querySelector(".backup-page[data-job-id]");
            if (currentPage?.dataset.jobId === job.job_id)
                FanboxUI.updateJobPage(currentPage, page, active);
            else
                app.replaceChildren(page);
            scheduleJobRefresh();
        }
        function renderBackupForm(creators, settings) {
            const value = settings.editable;
            app.replaceChildren(FanboxUI.renderBackupFormPage(creators, {
                dryRun: value.backup_defaults.dry_run,
                includeProfile: value.backup_defaults.include_profile,
                includeFancard: value.backup_defaults.include_fancard,
                maxPosts: value.sync.max_posts_per_run,
            }, state.activeJob, {
                onStart: (creators, dryRun, maxPosts, mode, includeProfile, includeFancard) => void startBackup(creators, dryRun, maxPosts, mode, includeProfile, includeFancard),
                onHistory: () => { state.backupScreen = "history"; void loadBackup(false); },
            }));
            scheduleJobRefresh();
        }
        function renderBackupHistory(creators, jobs) {
            app.replaceChildren(FanboxUI.renderBackupHistoryPage(jobs, creators, state.jobFilter, {
                onNew: () => { state.backupScreen = "form"; void loadBackup(false); },
                onShow: jobId => void showJob(jobId, creators, jobs),
                onFilter: value => { state.jobFilter = value; renderBackupHistory(creators, jobs); },
            }));
        }
        async function loadBackup(showLoading = true) {
            state.current = null;
            if (showLoading)
                app.replaceChildren(FanboxUI.h("p", { class: "empty" }, "正在讀取工作狀態…"));
            try {
                const [creatorData, jobData, settings] = await Promise.all([FanboxUI.getCreators(), FanboxUI.getJobs(), FanboxUI.getSettings()]);
                updateActiveJob(jobData.items);
                const backupJobs = jobData.items.filter(item => item.kind === "backup");
                const active = backupJobs.find(FanboxUI.isActiveJob);
                if (active) {
                    state.backupScreen = "job";
                    state.backupJobId = active.job_id;
                    renderJob(await FanboxUI.getJob(active.job_id), creatorData.items, backupJobs);
                }
                else if (state.backupScreen === "job" && state.backupJobId) {
                    const selected = backupJobs.find(item => item.job_id === state.backupJobId);
                    if (selected)
                        renderJob(await FanboxUI.getJob(selected.job_id), creatorData.items, backupJobs);
                    else {
                        state.backupScreen = "form";
                        state.backupJobId = null;
                        renderBackupForm(creatorData.items, settings);
                    }
                }
                else if (state.backupScreen === "history")
                    renderBackupHistory(creatorData.items, backupJobs);
                else
                    renderBackupForm(creatorData.items, settings);
            }
            catch (error) {
                errorView(error);
            }
        }
        async function startBackup(creators, dryRun, maxPosts, mode = "full", includeProfile = true, includeFancard = true) {
            try {
                const job = await FanboxUI.startBackupJob({ creators, dry_run: dryRun, max_posts: maxPosts, mode,
                    include_profile: includeProfile, include_fancard: includeFancard }, sessionToken);
                state.backupScreen = "job";
                state.backupJobId = job.job_id;
                const [creatorData, jobData] = await Promise.all([FanboxUI.getCreators(), FanboxUI.getJobs()]);
                updateActiveJob(jobData.items);
                renderJob(job, creatorData.items, jobData.items.filter(item => item.kind === "backup"));
            }
            catch (error) {
                errorView(error);
            }
        }
        async function cancelBackupJob(jobId) {
            try {
                const job = await FanboxUI.cancelJob(jobId, sessionToken);
                const [creatorData, jobData] = await Promise.all([FanboxUI.getCreators(), FanboxUI.getJobs()]);
                updateActiveJob(jobData.items);
                renderJob(job, creatorData.items, jobData.items.filter(item => item.kind === "backup"));
            }
            catch (error) {
                errorView(error);
            }
        }
        async function retryBackupJob(jobId) {
            try {
                const job = await FanboxUI.retryJob(jobId, sessionToken);
                const [creatorData, jobData] = await Promise.all([FanboxUI.getCreators(), FanboxUI.getJobs()]);
                updateActiveJob(jobData.items);
                renderJob(job, creatorData.items, jobData.items.filter(item => item.kind === "backup"));
            }
            catch (error) {
                errorView(error);
            }
        }
        function renderMaintenance(job = null, jobs = []) {
            if (jobTimer !== undefined)
                clearTimeout(jobTimer);
            app.replaceChildren(FanboxUI.renderMaintenancePage(job, jobs, state.activeJob, {
                onStart: () => void startVerification(),
                onShow: jobId => void showVerification(jobId, jobs),
            }));
            scheduleJobRefresh();
        }
        async function loadMaintenance(showLoading = true) {
            state.current = null;
            if (showLoading)
                app.replaceChildren(FanboxUI.h("p", { class: "empty" }, "正在讀取驗證狀態…"));
            try {
                const data = await FanboxUI.getJobs();
                updateActiveJob(data.items);
                const jobs = data.items.filter(item => item.kind === "verify");
                const selected = jobs.find(FanboxUI.isActiveJob) ?? jobs[0];
                renderMaintenance(selected ? await FanboxUI.getJob(selected.job_id) : null, jobs);
            }
            catch (error) {
                errorView(error);
            }
        }
        async function startVerification() {
            try {
                const job = await FanboxUI.startVerificationJob(sessionToken);
                const data = await FanboxUI.getJobs();
                updateActiveJob(data.items);
                renderMaintenance(job, data.items.filter(item => item.kind === "verify"));
            }
            catch (error) {
                errorView(error);
            }
        }
        async function showVerification(jobId, jobs) {
            try {
                renderMaintenance(await FanboxUI.getJob(jobId), jobs);
            }
            catch (error) {
                errorView(error);
            }
        }
        async function loadSettings(message = "", showLoading = true) {
            state.current = null;
            if (showLoading)
                app.replaceChildren(FanboxUI.h("p", { class: "empty" }, "正在讀取設定…"));
            try {
                const [data, jobData] = await Promise.all([FanboxUI.getSettings(), FanboxUI.getJobs()]);
                updateActiveJob(jobData.items);
                app.replaceChildren(FanboxUI.renderSettingsPage(data, message, state.activeJob, patch => saveSettingsForm(patch)));
                scheduleJobRefresh();
            }
            catch (error) {
                errorView(error);
            }
        }
        async function saveSettingsForm(patch) {
            try {
                await FanboxUI.saveSettings(patch, sessionToken);
                void loadSettings("設定已安全寫入；後續新工作會使用更新後的值。日誌處理器變更會在重新啟動後完整套用。");
                return null;
            }
            catch (error) {
                return error instanceof Error ? error.message : String(error);
            }
        }
        search.addEventListener("input", () => {
            if (searchTimer !== undefined)
                clearTimeout(searchTimer);
            searchTimer = window.setTimeout(() => {
                state.q = search.value.trim();
                state.page = 1;
                void refreshView();
            }, 180);
        });
        nav.addEventListener("click", event => {
            const target = event.target instanceof Element
                ? event.target.closest("button[data-view]") : null;
            const view = target?.dataset.view;
            if (!view || !["posts", "creators", "backup", "maintenance", "settings"].includes(view))
                return;
            state.q = "";
            search.value = "";
            setView(view);
        });
        window.addEventListener("popstate", event => {
            if (state.view !== "creator" || state.creatorTab !== "posts" || !state.creatorId)
                return;
            const historyState = event.state;
            if (historyState?.fanboxCreatorId && historyState.fanboxCreatorId !== state.creatorId)
                return;
            state.tag = historyState?.fanboxCreatorTag ?? "";
            state.page = 1;
            void loadCreator(state.creatorId, "posts");
        });
        window.addEventListener("keydown", event => {
            if (["ArrowLeft", "ArrowRight"].includes(event.key)
                && typeof state.current === "string" && state.postNavigation) {
                const target = event.target;
                const interactive = target instanceof Element && (target.matches("input,textarea,select,button,a,summary,[contenteditable='true']")
                    || target.closest(".custom-select,.page-jump"));
                if (!interactive && !event.altKey && !event.ctrlKey && !event.metaKey && !event.shiftKey) {
                    const neighbor = event.key === "ArrowLeft"
                        ? state.postNavigation.previous : state.postNavigation.next;
                    if (neighbor) {
                        event.preventDefault();
                        void loadPost(neighbor.post_id);
                    }
                    return;
                }
            }
            if (event.key !== "Escape")
                return;
            if (FanboxUI.closeDropdownsAndFocus())
                return;
            if (state.current)
                void refreshView();
        });
        setView("posts");
    }
    FanboxUI.startApp = startApp;
})(FanboxUI || (FanboxUI = {}));
if (typeof document !== "undefined" && document.getElementById("app"))
    FanboxUI.startApp();
var FanboxUI;
(function (FanboxUI) {
    function startDesktopOnboarding() {
        const root = document.getElementById("desktop-onboarding");
        const status = document.getElementById("desktop-status");
        if (!(root instanceof HTMLElement) || !(status instanceof HTMLElement))
            return;
        const bridge = window.__TAURI__;
        if (!bridge) {
            status.textContent = "此頁面必須由 FANBOX Archiver 桌面程式開啟。";
            status.classList.add("error");
            return;
        }
        const statusElement = status;
        const tauriCore = bridge.core;
        const buttons = [...root.querySelectorAll("button[data-command]")];
        async function launch(command) {
            for (const button of buttons)
                button.disabled = true;
            statusElement.textContent = command === "choose_existing_config"
                ? "請選擇既有的 config.yaml…"
                : command === "choose_archive_folder" ? "請選擇既有的 FANBOX 封存資料夾…"
                    : "正在建立新的本機資料…";
            statusElement.classList.remove("error");
            try {
                const result = await tauriCore.invoke(command);
                if (result === null) {
                    statusElement.textContent = "未選擇任何項目，你可以改用其他方式繼續。";
                    for (const button of buttons)
                        button.disabled = false;
                    return;
                }
                statusElement.textContent = `正在啟動本機伺服器：${result.config_path}`;
            }
            catch (error) {
                statusElement.textContent = error instanceof Error ? error.message : String(error);
                statusElement.classList.add("error");
                for (const button of buttons)
                    button.disabled = false;
            }
        }
        root.addEventListener("click", event => {
            const button = event.target instanceof Element
                ? event.target.closest("button[data-command]") : null;
            if (button?.dataset.command)
                void launch(button.dataset.command);
        });
    }
    if (typeof document !== "undefined" && document.getElementById("desktop-onboarding")) {
        startDesktopOnboarding();
    }
})(FanboxUI || (FanboxUI = {}));
