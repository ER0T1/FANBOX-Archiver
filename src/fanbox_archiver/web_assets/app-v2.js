(() => {
  "use strict";

  const app = document.getElementById("app");
  const search = document.getElementById("search");
  const nav = document.getElementById("nav");
  const sessionToken = document.querySelector('meta[name="fanbox-session-token"]').content;
  const ui = globalThis.FanboxUI;
  if (!ui) throw new Error("TypeScript web core was not loaded");
  const state = ui.createInitialState();
  const date = ui.formatDate;
  const humanBytes = ui.humanBytes;
  const feeLabel = ui.feeLabel;
  let jobTimer = null;
  let searchTimer = null;
  let creatorRequest = 0;

  const element = (tag, attrs = {}, ...children) => {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
      if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2), value);
      else if (value !== null && value !== undefined) node.setAttribute(key, String(value));
    }
    for (const child of children.flat()) {
      if (child === null || child === undefined) continue;
      node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return node;
  };

  function customSelect({id, label, value, options, onChange}) {
    const normalized = options.map(option => ({value: String(option.value), label: String(option.label)}));
    let selectedValue = String(value ?? normalized[0]?.value ?? "");
    const menuId = `${id || "select"}-menu-${Math.random().toString(36).slice(2, 9)}`;
    const summaryText = element("span", {class: "select-value"});
    const menu = element("div", {id: menuId, class: "select-menu", role: "listbox", "aria-label": label});
    const root = element("details", {class: "custom-select", id});
    const summary = element("summary", {role: "combobox", "aria-label": label, "aria-controls": menuId, "aria-expanded": "false", "aria-haspopup": "listbox"}, summaryText);

    const update = nextValue => {
      selectedValue = String(nextValue);
      const selected = normalized.find(option => option.value === selectedValue) || normalized[0];
      summaryText.textContent = selected?.label || "";
      for (const button of menu.querySelectorAll('[role="option"]')) {
        const active = button.dataset.value === selectedValue;
        button.setAttribute("aria-selected", active ? "true" : "false");
        button.tabIndex = active ? 0 : -1;
      }
    };

    for (const option of normalized) {
      menu.append(element("button", {type: "button", role: "option", "data-value": option.value, onclick: () => {
        const changed = selectedValue !== option.value;
        update(option.value);
        root.open = false;
        summary.focus();
        if (changed && onChange) onChange(option.value);
      }}, option.label));
    }

    summary.addEventListener("keydown", event => {
      if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      root.open = true;
      const choices = [...menu.querySelectorAll('[role="option"]')];
      const selectedIndex = Math.max(0, choices.findIndex(button => button.dataset.value === selectedValue));
      const targetIndex = event.key === "End" ? choices.length - 1 : event.key === "ArrowUp" ? Math.max(0, selectedIndex - 1) : event.key === "ArrowDown" ? Math.min(choices.length - 1, selectedIndex + 1) : 0;
      choices[targetIndex]?.focus();
    });
    menu.addEventListener("keydown", event => {
      const choices = [...menu.querySelectorAll('[role="option"]')];
      const index = choices.indexOf(document.activeElement);
      if (event.key === "Escape") {
        event.preventDefault(); root.open = false; summary.focus(); return;
      }
      if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const targetIndex = event.key === "Home" ? 0 : event.key === "End" ? choices.length - 1
        : event.key === "ArrowDown" ? Math.min(choices.length - 1, index + 1) : Math.max(0, index - 1);
      choices[targetIndex]?.focus();
    });
    root.addEventListener("toggle", () => {
      summary.setAttribute("aria-expanded", root.open ? "true" : "false");
      if (root.open) menu.querySelector('[aria-selected="true"]')?.scrollIntoView({block: "nearest"});
    });
    Object.defineProperty(root, "value", {get: () => selectedValue, set: update});
    root.append(summary, menu);
    update(selectedValue);
    return root;
  }

  document.addEventListener("click", event => {
    for (const dropdown of document.querySelectorAll(".custom-select[open], .page-jump[open]")) {
      if (!dropdown.contains(event.target)) dropdown.open = false;
    }
  });

  const request = async (url, options = {}) => {
    const response = await fetch(url, {...options, headers: {Accept: "application/json", ...(options.headers || {})}});
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || `HTTP ${response.status}`);
    }
    return response.json();
  };

  function errorView(error) {
    app.replaceChildren(element("section", {class: "panel error"},
      element("p", {class: "eyebrow"}, "ERROR"), element("h1", {}, "無法讀取封存"),
      element("p", {}, error.message), element("button", {type: "button", onclick: refreshView}, "重試")));
  }

  function setActiveNav(view) {
    const active = view === "creator" ? "creators" : view;
    for (const button of nav.querySelectorAll("button")) button.classList.toggle("active", button.dataset.view === active);
  }

  function setSearch(view) {
    search.disabled = ["backup", "maintenance", "settings"].includes(view) || (view === "creator" && state.creatorTab === "profile");
    search.placeholder = view === "posts" ? "搜尋標題、Post ID 或創作者…"
      : view === "creators" ? "搜尋創作者…"
      : view === "creator" && state.creatorTab === "fancards" ? "搜尋月份…"
      : view === "creator" && state.creatorTab === "posts" ? "搜尋此創作者的投稿…"
      : view === "backup" ? "備份執行期間可繼續閱讀封存"
      : view === "maintenance" ? "封存驗證與維護"
      : view === "settings" ? "本機設定" : "創作者個人資料";
  }

  function setView(view) {
    clearTimeout(jobTimer);
    state.view = view;
    state.current = null;
    state.page = 1;
    if (view !== "creator") state.creatorId = null;
    setActiveNav(view);
    setSearch(view);
    refreshView();
  }

  function refreshView() {
    if (state.view === "backup") return loadBackup();
    if (state.view === "maintenance") return loadMaintenance();
    if (state.view === "settings") return loadSettings();
    if (state.view === "creators") return loadCreators();
    if (state.view === "creator") return loadCreator(state.creatorId, state.creatorTab);
    return loadPosts();
  }

  function postCard(item, onOpen = () => loadPost(item.post_id)) {
    return element("button", {type: "button", class: `post-card${item.is_pinned ? " pinned" : ""}`, onclick: onOpen},
      item.cover_url
        ? element("img", {class: "post-cover", src: item.cover_url, alt: "", loading: "lazy"})
        : element("span", {class: "post-cover placeholder", "aria-hidden": "true"}, "POST"),
      element("span", {class: "post-main"},
        element("span", {class: "post-meta"}, date(item.published_at),
          item.is_pinned ? element("span", {class: "pin-badge"}, "置頂") : null,
          element("span", {class: "fee-badge"}, feeLabel(item.fee_required))),
        element("strong", {}, item.title),
        element("small", {}, `${item.creator_name} · Post ${item.post_id} · ${item.version_count} 個版本`)),
      element("span", {class: `badge status-${item.status}`}, item.status));
  }

  function pagination(data, onPage, label = "投稿分頁") {
    const previous = element("button", {type: "button", disabled: data.page <= 1 ? "" : null,
      onclick: () => onPage(data.page - 1)}, "← 上一頁");
    const next = element("button", {type: "button", disabled: data.page >= data.pages ? "" : null,
      onclick: () => onPage(data.page + 1)}, "下一頁 →");
    const pageJump = element("details", {class: "page-jump"},
      element("summary", {"aria-label": `目前第 ${data.page} 頁，共 ${data.pages} 頁`}, `${data.page} / ${data.pages}`),
      element("div", {class: "page-menu", role: "listbox", "aria-label": "跳至頁數"},
        ...Array.from({length: data.pages}, (_, index) => {
          const page = index + 1;
          return element("button", {type: "button", role: "option", "aria-selected": page === data.page ? "true" : "false", onclick: () => {
            pageJump.open = false;
            onPage(page);
          }}, String(page));
        })));
    return element("nav", {class: "pagination", "aria-label": label}, previous, pageJump, next);
  }

  async function loadPosts() {
    state.current = null;
    app.replaceChildren(element("p", {class: "empty"}, "正在讀取投稿…"));
    try {
      const params = new URLSearchParams({page: state.page, page_size: 50});
      if (state.q) params.set("q", state.q);
      const data = await request(`/api/posts?${params}`);
      const cards = data.items.map(item => postCard(item));
      app.replaceChildren(element("section", {class: "page"},
        element("header", {class: "heading"}, element("div", {},
          element("p", {class: "eyebrow"}, "POSTS"), element("h1", {}, "投稿"), element("p", {}, `${data.total} 篇備份`))),
        element("div", {class: "post-list"}, ...(cards.length ? cards : [element("p", {class: "empty"}, "沒有符合條件的投稿。")])),
        pagination(data, page => { state.page = page; loadPosts(); })));
    } catch (error) { errorView(error); }
  }

  function richText(block) {
    const fragment = document.createDocumentFragment();
    const text = block.text || "";
    const styles = [...(block.styles || [])].sort((a, b) => a.offset - b.offset);
    let position = 0;
    for (const style of styles) {
      const start = Math.max(position, style.offset);
      if (start > position) fragment.append(text.slice(position, start));
      const end = Math.min(text.length, style.offset + style.length);
      fragment.append(element("strong", {}, text.slice(start, end)));
      position = end;
    }
    if (position < text.length) fragment.append(text.slice(position));
    return fragment;
  }

  function embedView(block) {
    const preview = block.embed;
    if (!preview || preview.kind !== "fanbox.post") {
      if (!block.url) return null;
      return element("p", {class: "attachment"}, element("a", {href: block.url, target: "_blank", rel: "noreferrer"}, block.name || block.url));
    }
    const meta = [];
    if (preview.published_at) meta.push(element("span", {}, date(preview.published_at)));
    if (preview.fee_required !== null && preview.fee_required !== undefined) {
      meta.push(element("span", {class: "embed-fee"}, feeLabel(preview.fee_required)));
    }
    if (preview.creator_name) meta.push(element("span", {}, preview.creator_name));
    const attrs = preview.local_available
      ? {href: `#post-${preview.post_id}`, onclick: event => { event.preventDefault(); loadPost(preview.post_id); }}
      : {href: preview.fanbox_url, target: "_blank", rel: "noreferrer noopener"};
    return element("a", {class: "embed-card", ...attrs},
      element("span", {class: "embed-content"},
        element("span", {class: "embed-source"}, preview.local_available ? "FANBOX 投稿 · 本機備份" : "FANBOX 投稿"),
        element("strong", {}, preview.title),
        preview.excerpt ? element("span", {class: "embed-excerpt"}, preview.excerpt) : null,
        element("span", {class: "embed-meta"}, ...meta)),
      preview.cover_url
        ? element("img", {class: "embed-cover", src: preview.cover_url, alt: "", loading: "lazy"})
        : element("span", {class: "embed-cover placeholder", "aria-hidden": "true"}, "FANBOX"));
  }

  function blockView(block) {
    if (block.type === "image" && block.media_url) return element("figure", {},
      element("a", {href: block.media_url, target: "_blank"}, element("img", {src: block.media_url, loading: "lazy", alt: block.name || "投稿圖片"})));
    if (block.type === "file" && block.media_url) return element("p", {class: "attachment"}, element("a", {href: block.media_url}, block.name || block.filename || "下載附件"));
    if (block.type === "separator") return element("hr");
    if (block.type === "quote") return element("blockquote", {}, richText(block));
    if (block.type === "heading") return element(`h${Math.min(Math.max(block.level || 2, 2), 6)}`, {}, richText(block));
    if (block.type === "embed") return embedView(block);
    if (block.text) return element("p", {class: "body-text"}, richText(block));
    return null;
  }

  function postNavigationView(navigation, placement) {
    const previous = navigation?.previous;
    const next = navigation?.next;
    const control = (item, direction) => element("button", {
      type: "button", class: `post-nav-button ${direction}`, disabled: item ? null : "",
      onclick: () => item && loadPost(item.post_id),
      title: item?.title || (direction === "previous" ? "已是第一篇" : "已是最後一篇"),
    },
    element("span", {}, direction === "previous" ? "← 上一篇" : "下一篇 →"),
    element("strong", {}, item?.title || (direction === "previous" ? "沒有更前面的投稿" : "沒有更後面的投稿")));
    return element("nav", {class: `post-navigation ${placement}`, "aria-label": placement === "top" ? "文章頂端導覽" : "文章底部導覽"},
      control(previous, "previous"),
      element("span", {class: "post-position"}, navigation?.position ? `${navigation.position} / ${navigation.total}` : "—"),
      control(next, "next"));
  }

  async function loadPost(postId, version = null) {
    const creatorContent = state.view === "creator" ? app.querySelector(".creator-content") : null;
    const target = creatorContent || app;
    const back = creatorContent ? () => loadCreator(state.creatorId, "posts") : loadPosts;
    state.postNavigation = null;
    target.replaceChildren(element("p", {class: "empty"}, "正在讀取投稿…"));
    try {
      const params = new URLSearchParams();
      if (version) params.set("version", version);
      if (creatorContent && state.creatorId) params.set("creator", state.creatorId);
      if (state.q) params.set("q", state.q);
      const query = params.toString();
      const post = await request(`/api/posts/${postId}${query ? `?${query}` : ""}`);
      state.current = postId;
      state.postNavigation = post.navigation;
      const versionSelect = customSelect({id: "post-version", label: "版本", value: post.version,
        options: post.versions.map(item => ({value: item.number, label: `v${String(item.number).padStart(4, "0")} · ${date(item.captured_at)}`})),
        onChange: value => loadPost(postId, Number(value))});
      const body = post.blocks.map(blockView).filter(Boolean);
      target.replaceChildren(element("article", {class: "reader"},
        element("button", {type: "button", class: "back", onclick: back}, "← 回到投稿"),
        postNavigationView(post.navigation, "top"),
        post.cover_url ? element("a", {href: post.cover_url, target: "_blank"}, element("img", {class: "cover", src: post.cover_url, alt: "投稿封面"})) : null,
        element("header", {class: "reader-heading"}, element("p", {class: "eyebrow"}, `${post.creator_name} · POST ${post.post_id}`),
          element("h1", {}, post.title), element("div", {class: "reader-meta"},
            post.is_pinned ? element("span", {class: "pin-badge"}, "置頂投稿") : null,
            element("span", {class: "fee-badge"}, feeLabel(post.fee_required)), element("span", {}, `發布 ${date(post.published_at)}`), element("span", {}, `更新 ${date(post.updated_at)}`)), versionSelect),
        element("section", {class: "content"}, ...(body.length ? body : [element("p", {class: "empty"}, "此版本沒有可顯示的正文。")])),
        postNavigationView(post.navigation, "bottom"),
        element("footer", {}, element("a", {href: post.url, target: "_blank", rel: "noreferrer"}, "開啟 FANBOX 原文 ↗"))));
    } catch (error) { errorView(error); }
  }

  async function loadCreators() {
    state.current = null;
    app.replaceChildren(element("p", {class: "empty"}, "正在讀取創作者…"));
    try {
      const data = await request("/api/creators");
      const term = state.q.toLocaleLowerCase();
      const items = data.items.filter(item => `${item.name} ${item.creator_id}`.toLocaleLowerCase().includes(term));
      const cards = items.map(item => element("button", {type: "button", class: "creator-card", onclick: () => openCreator(item.creator_id)},
        item.avatar_url ? element("img", {src: item.avatar_url, alt: "", loading: "lazy"}) : element("span", {class: "avatar"}, item.name.slice(0, 1)),
        element("span", {class: "post-main"}, element("strong", {}, item.name), element("small", {}, `${item.creator_id} · ${item.post_count} 篇投稿`)),
        element("span", {class: `badge status-${item.status}`}, item.status)));
      app.replaceChildren(element("section", {class: "page"},
        element("header", {class: "heading"}, element("div", {}, element("p", {class: "eyebrow"}, "CREATORS"), element("h1", {}, "創作者"), element("p", {}, `${items.length} 位符合目前條件`))),
        element("div", {class: "creator-grid"}, ...(cards.length ? cards : [element("p", {class: "empty"}, "沒有符合條件的創作者。")]))));
    } catch (error) { errorView(error); }
  }

  function openCreator(creatorId, tab = "profile") {
    state.view = "creator";
    state.creatorId = creatorId;
    state.creatorTab = tab;
    state.current = null;
    state.page = 1;
    state.q = "";
    state.creator = null;
    state.creatorProfile = null;
    search.value = "";
    setActiveNav("creator");
    setSearch("creator");
    loadCreator(creatorId, tab);
  }

  function switchCreatorTab(creatorId, tab) {
    state.creatorTab = tab;
    state.current = null;
    state.page = 1;
    state.q = "";
    search.value = "";
    setSearch("creator");
    loadCreator(creatorId, tab);
  }

  function creatorShell(creator, tab, content, profile = null) {
    const tabs = [["profile", "個人資料", "PROFILE"], ["posts", "投稿", "POSTS"], ["fancards", "粉絲卡", "FAN CARD"]];
    return element("section", {class: "page creator-page", "data-creator-id": creator.creator_id},
      element("button", {type: "button", class: "back", onclick: () => setView("creators")}, "← 回到創作者"),
      element("header", {class: `creator-hero${profile?.cover_url ? " has-cover" : ""}`},
        profile?.cover_url ? element("img", {class: "creator-cover", src: profile.cover_url, alt: ""}) : null,
        creator.avatar_url ? element("img", {src: creator.avatar_url, alt: ""}) : element("span", {class: "avatar large"}, creator.name.slice(0, 1)),
        element("div", {}, element("p", {class: "eyebrow"}, `@${creator.creator_id}`), element("h1", {}, creator.name),
          element("p", {}, `${creator.post_count} 篇投稿 · ${creator.fancard_count} 張粉絲卡`)),
        element("a", {class: "external-button", href: creator.fanbox_url, target: "_blank", rel: "noreferrer"}, "開啟 FANBOX ↗")),
      element("nav", {class: "subnav", "aria-label": "創作者頁面"}, ...tabs.map(([key, zh, en]) => element("button", {
        type: "button", class: key === tab ? "active" : "", "data-creator-tab": key, onclick: () => switchCreatorTab(creator.creator_id, key)
      }, element("strong", {}, zh), element("small", {}, en)))),
      element("div", {class: "creator-content", "aria-live": "polite"}, content));
  }

  async function loadCreator(creatorId, tab = "profile", profileVersion = null) {
    state.creatorTab = tab;
    setSearch("creator");
    const requestNumber = ++creatorRequest;
    try {
      let creator = state.creator?.creator_id === creatorId ? state.creator : null;
      let heroProfile = state.creatorProfile;
      if (!creator) {
        app.replaceChildren(element("p", {class: "empty"}, "正在讀取創作者頁面…"));
        creator = await request(`/api/creators/${encodeURIComponent(creatorId)}`);
        heroProfile = creator.profile_available ? await request(`/api/creators/${encodeURIComponent(creatorId)}/profile`) : null;
        if (requestNumber !== creatorRequest || state.creatorId !== creatorId) return;
        state.creator = creator;
        state.creatorProfile = heroProfile;
        app.replaceChildren(creatorShell(creator, tab, element("p", {class: "empty"}, "正在讀取內容…"), heroProfile));
      }
      let shell = app.querySelector(".creator-page");
      if (!shell || shell.dataset.creatorId !== creatorId) {
        app.replaceChildren(creatorShell(creator, tab, element("p", {class: "empty"}, "正在讀取內容…"), heroProfile));
        shell = app.querySelector(".creator-page");
      }
      if (!shell) return;
      for (const button of shell.querySelectorAll("[data-creator-tab]")) button.classList.toggle("active", button.dataset.creatorTab === tab);
      const contentRoot = shell.querySelector(".creator-content");
      contentRoot.replaceChildren(element("p", {class: "empty"}, "正在讀取內容…"));
      let content;
      if (tab === "posts") {
        const params = new URLSearchParams({creator: creatorId, page: state.page, page_size: 50});
        if (state.q) params.set("q", state.q);
        const data = await request(`/api/posts?${params}`);
        const cards = data.items.map(item => postCard(item, () => loadPost(item.post_id)));
        content = element("div", {class: "creator-posts"},
          element("div", {class: "post-list"}, ...(cards.length ? cards : [element("p", {class: "empty"}, "沒有符合條件的投稿。")])),
          pagination(data, page => { state.page = page; loadCreator(creatorId, "posts"); }, "創作者投稿分頁"));
      } else if (tab === "fancards") {
        const params = new URLSearchParams({creator: creatorId});
        if (state.q) params.set("q", state.q);
        const data = await request(`/api/fancards?${params}`);
        const cards = data.items.map(item => element("button", {type: "button", class: "fancard-card", onclick: () => loadFancard(item.creator_id, item.target_month)},
          item.image_url ? element("img", {src: item.image_url, alt: `${item.creator_name} 粉絲卡`, loading: "lazy"}) : element("div", {class: "card-placeholder"}, "無卡面"),
          element("span", {class: "post-main"}, element("span", {class: "eyebrow"}, item.target_month), element("strong", {}, item.plan_title || "方案未命名"),
            element("small", {}, `${feeLabel(item.fee)}/月 · ${item.version_count} 個版本`))));
        content = element("div", {class: "fancard-grid"}, ...(cards.length ? cards : [element("p", {class: "empty"}, "尚未備份粉絲卡。")]));
      } else {
        let profile = heroProfile;
        if (creator.profile_available && profileVersion) profile = await request(`/api/creators/${encodeURIComponent(creatorId)}/profile?version=${profileVersion}`);
        const safeLinks = (profile?.profile_items || []).filter(item => item.url?.startsWith("https://"));
        const profileImages = (profile?.profile_items || []).filter(item => item.image_url);
        const versionSelect = profile ? customSelect({id: "profile-version", label: "Profile 版本", value: profile.version,
          options: profile.versions.map(item => ({value: item.number, label: `v${String(item.number).padStart(4, "0")} · ${date(item.captured_at)}`})),
          onChange: value => loadCreator(creatorId, "profile", Number(value))}) : null;
        content = element("div", {class: "profile-layout"},
          !profile ? element("section", {class: "profile-empty"}, element("p", {class: "eyebrow"}, "PROFILE ARCHIVE"), element("h2", {}, "尚未備份個人資料"), element("p", {}, "執行新版備份後，這裡會顯示離線可讀的自我介紹、連結與歷史版本。")) : null,
          profile ? element("section", {class: "info-panel profile-about"}, element("p", {class: "eyebrow"}, "ABOUT"), element("h2", {}, "關於創作者"),
            profileImages.length ? element("div", {class: "profile-gallery", "aria-label": "創作者 Profile 圖片"}, ...profileImages.map((item, index) =>
              element("a", {href: item.image_url, target: "_blank"}, element("img", {src: item.image_url, alt: item.label || `Profile 圖片 ${index + 1}`, loading: "lazy"})))) : null,
            profile.description ? element("p", {class: "body-text"}, profile.description) : element("p", {class: "profile-about-empty"}, "這位創作者尚未提供文字或圖片形式的個人介紹。")) : null,
          safeLinks.length ? element("section", {class: "info-panel profile-links"}, element("p", {class: "eyebrow"}, "LINKS"), element("h2", {}, "公開連結"), element("div", {class: "link-grid"}, ...safeLinks.map(item => element("a", {href: item.url, target: "_blank", rel: "noreferrer"}, element("strong", {}, item.label || item.type || "外部連結"), item.description ? element("span", {}, item.description) : null)))) : null,
          profile ? element("section", {class: "info-panel profile-meta"}, element("p", {class: "eyebrow"}, "ARCHIVE METADATA"), element("h2", {}, "狀態與版本"),
            element("div", {class: "status-list"},
              profile.has_adult_content ? element("span", {class: "profile-flag adult"}, "成人內容") : element("span", {class: "profile-flag"}, "一般內容"),
              element("span", {class: "profile-flag"}, profile.is_accepting_request ? "開放委託" : "未開放委託"),
              profile.is_stopped ? element("span", {class: "profile-flag danger"}, "已停止活動") : element("span", {class: "profile-flag"}, "持續活動")),
            element("dl", {}, element("div", {}, element("dt", {}, "捕捉時間"), element("dd", {}, date(profile.captured_at))), element("div", {}, element("dt", {}, "版本"), element("dd", {}, versionSelect)))) : null,
          element("section", {class: "profile-stats"},
            element("div", {}, element("strong", {}, creator.post_count), element("span", {}, "投稿")),
            element("div", {}, element("strong", {}, creator.completed_count), element("span", {}, "完整備份")),
            element("div", {}, element("strong", {}, creator.fancard_count), element("span", {}, "粉絲卡"))));
      }
      if (requestNumber !== creatorRequest || state.creatorId !== creatorId || state.creatorTab !== tab) return;
      contentRoot.replaceChildren(content);
    } catch (error) {
      if (requestNumber !== creatorRequest || state.creatorId !== creatorId) return;
      errorView(error);
    }
  }

  async function loadFancard(creatorId, month, version = null) {
    const creatorContent = state.view === "creator" ? app.querySelector(".creator-content") : null;
    const target = creatorContent || app;
    target.replaceChildren(element("p", {class: "empty"}, "正在讀取粉絲卡…"));
    try {
      const card = await request(`/api/fancards/${encodeURIComponent(creatorId)}/${month}${version ? `?version=${version}` : ""}`);
      state.current = {type: "fancard", creatorId, month};
      const versionSelect = customSelect({id: "fancard-version", label: "版本", value: card.version,
        options: card.versions.map(item => ({value: item.number, label: `v${String(item.number).padStart(4, "0")} · ${date(item.captured_at)}`})),
        onChange: value => loadFancard(creatorId, month, Number(value))});
      target.replaceChildren(element("article", {class: "reader fancard-reader"},
        element("button", {type: "button", class: "back", onclick: () => loadCreator(creatorId, "fancards")}, "← 回到粉絲卡"),
        card.image_url ? element("a", {href: card.image_url, target: "_blank"}, element("img", {class: "card-image", src: card.image_url, alt: `${card.creator_name} 粉絲卡`})) : element("div", {class: "card-placeholder large"}, "本月未提供自訂卡面"),
        element("header", {class: "reader-heading"}, element("p", {class: "eyebrow"}, `${card.target_month} · ${card.creator_id}`), element("h1", {}, card.creator_name),
          element("p", {}, `${card.plan_title || "方案未命名"} · ${feeLabel(card.fee)}/月`), versionSelect),
        element("section", {class: "content"}, element("h2", {}, "方案資訊"), element("p", {class: "body-text"}, card.description || "（無方案說明）"),
          card.support_start ? element("p", {}, `支援開始：${date(card.support_start)}`) : null,
          card.support_months.length ? element("p", {}, `保存月份：${card.support_months.join("、")}`) : null,
          card.perks.length ? element("pre", {}, JSON.stringify(card.perks, null, 2)) : null)));
    } catch (error) { errorView(error); }
  }

  function eventLabel(event) {
    const data = event.data || {};
    if (event.kind === "job_started") return `工作開始（${data.scope}）`;
    if (event.kind === "plan_ready") return `計畫：新增 ${data.new}、更新 ${data.updated}、重試 ${data.retried}、略過 ${data.skipped}`;
    if (event.kind === "fancard_finished") return `粉絲卡 ${data.creator_id}：${data.status}`;
    if (event.kind === "profile_started") return `正在備份 @${data.creator_id} 的個人資料`;
    if (event.kind === "profile_finished") return `個人資料 ${data.creator_id}：${data.status}（v${String(data.version || 0).padStart(4, "0")}）`;
    if (event.kind === "profile_warning") return `個人資料警告：${data.creator_id}：${data.message}`;
    if (event.kind === "asset_progress") return `${data.name}：${humanBytes(data.downloaded)}${data.total ? ` / ${humanBytes(data.total)}` : ""}`;
    if (event.kind === "item_finished") return `Post ${data.post_id}：${data.unchanged ? "內容未變" : data.error || data.status}`;
    if (event.kind === "warning") return `警告：${data.creator_id ? `${data.creator_id}：` : ""}${data.message}`;
    if (event.kind === "job_finished") return data.dry_run ? "預覽完成" : `完成：成功 ${data.success}、未完成 ${data.failure}`;
    if (event.kind === "job_failed") return `錯誤：${data.error}`;
    if (event.kind === "job_cancelled") return "工作已取消";
    if (event.kind === "job_interrupted") return "伺服器曾重新啟動，工作已中斷且未自動重跑";
    return event.kind;
  }

  function eventTone(kind) {
    if (kind === "warning" || kind === "profile_warning" || kind === "job_interrupted") return "warning";
    if (kind === "job_failed") return "error";
    if (kind === "plan_ready") return "plan";
    if (kind === "job_finished") return "success";
    return "neutral";
  }

  function planSummary(event, creators) {
    if (!event) return null;
    const data = event.data || {};
    const creatorNames = new Map(creators.map(item => [item.creator_id, item.name]));
    const metrics = [["新增", data.new, "new"], ["更新", data.updated, "updated"], ["重試", data.retried, "retry"], ["略過", data.skipped, "skipped"]];
    const rows = (data.scans || []).map(scan => element("tr", {},
      element("th", {scope: "row"}, element("strong", {}, creatorNames.get(scan.creator_id) || scan.creator_id), element("small", {}, scan.creator_id)),
      element("td", {class: "number new"}, scan.new), element("td", {class: "number updated"}, scan.updated),
      element("td", {class: "number retry"}, scan.retry), element("td", {class: "number skipped"}, scan.skipped),
      element("td", {class: "number"}, scan.discovered), element("td", {class: `profile-result ${scan.profile || "none"}`}, scan.profile || "—")));
    const creatorCount = Array.isArray(data.creators) ? data.creators.length : Number(data.creators ?? rows.length);
    return element("section", {class: "plan-panel"},
      element("div", {class: "section-title"}, element("div", {}, element("p", {class: "eyebrow"}, "BACKUP PLAN"), element("h2", {}, "本次備份摘要")),
        element("span", {class: "plan-creators"}, `${creatorCount} 位創作者`)),
      element("div", {class: "metric-grid"}, ...metrics.map(([label, value, tone]) => element("div", {class: `metric ${tone}`}, element("strong", {}, value ?? 0), element("span", {}, label)))),
      rows.length ? element("div", {class: "table-scroll"}, element("table", {class: "plan-table"},
        element("thead", {}, element("tr", {}, element("th", {}, "創作者"), element("th", {}, "新增"), element("th", {}, "更新"), element("th", {}, "重試"), element("th", {}, "略過"), element("th", {}, "發現"), element("th", {}, "Profile"))),
        element("tbody", {}, ...rows))) : null);
  }

  function currentActivity(job) {
    const events = job.events || [];
    const event = [...events].reverse().find(item => ["asset_progress", "item_finished", "fancard_finished", "profile_started", "profile_finished", "profile_warning", "warning", "job_failed", "job_finished", "job_cancelled", "job_interrupted", "job_started"].includes(item.kind));
    if (!event) return element("section", {class: "current-activity"}, element("p", {class: "eyebrow"}, "CURRENT"), element("h2", {}, "正在準備備份…"));
    const data = event.data || {};
    const isAsset = event.kind === "asset_progress";
    const total = Number(data.total || 0);
    const downloaded = Number(data.downloaded || 0);
    const percent = total > 0 ? Math.min(100, Math.max(0, downloaded / total * 100)) : null;
    return element("section", {class: `current-activity tone-${eventTone(event.kind)}`},
      element("div", {class: "activity-top"}, element("div", {}, element("p", {class: "eyebrow"}, isAsset ? "CURRENT DOWNLOAD" : "CURRENT STATUS"),
        element("h2", {}, isAsset ? data.name || "下載資源" : eventLabel(event))),
        element("time", {}, date(event.timestamp))),
      isAsset ? element("div", {class: "progress-area"},
        element("div", {class: "progress-label"}, element("span", {}, `${humanBytes(downloaded)}${total ? ` / ${humanBytes(total)}` : ""}`), element("strong", {}, percent === null ? "下載中" : `${percent.toFixed(1)}%`)),
        element("progress", {max: total || 1, value: downloaded, "aria-label": "目前資源下載進度"})) : null);
  }

  function eventLog(events) {
    const rows = events.map(item => element("li", {class: `event-${eventTone(item.kind)}`},
      element("span", {class: "event-mark", "aria-hidden": "true"}), element("time", {}, date(item.timestamp)),
      element("span", {class: "event-kind"}, item.kind === "plan_ready" ? "計畫" : ["warning", "profile_warning", "job_interrupted"].includes(item.kind) ? "警告" : item.kind === "job_failed" ? "錯誤" : "紀錄"),
      element("span", {class: "event-message"}, eventLabel(item))));
    const details = element("details", {class: "job-details"},
      element("summary", {}, element("span", {}, "詳細執行紀錄"), element("small", {}, `${events.length} 筆`)),
      element("ol", {class: "event-log"}, ...(rows.length ? rows : [element("li", {class: "event-neutral"}, "等待工作事件…")])));
    details.addEventListener("toggle", () => {
      if (!details.open) return;
      const log = details.querySelector(".event-log");
      log.scrollTop = log.scrollHeight;
    });
    return details;
  }

  function jobPart(node, name) {
    node.dataset.jobPart = name;
    return node;
  }

  function updateJobPage(current, next, {preserveHistory = false} = {}) {
    const currentParts = new Map([...current.children].map(node => [node.dataset.jobPart, node]));
    for (const nextPart of [...next.children]) {
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
        const wasOpen = currentPart.open;
        const log = currentPart.querySelector(".event-log");
        const previousScrollTop = log?.scrollTop || 0;
        const nearBottom = log ? log.scrollHeight - log.scrollTop - log.clientHeight < 40 : true;
        currentPart.replaceChildren(...nextPart.childNodes);
        currentPart.open = wasOpen;
        const updatedLog = currentPart.querySelector(".event-log");
        if (wasOpen && updatedLog) updatedLog.scrollTop = nearBottom ? updatedLog.scrollHeight : previousScrollTop;
      } else {
        currentPart.replaceWith(nextPart);
      }
      currentParts.delete(name);
    }
    for (const stale of currentParts.values()) stale.remove();
  }

  function statusText(status) {
    return ({queued: "等待中", running: "執行中", cancelling: "停止中", completed: "已完成", failed: "失敗", cancelled: "已取消", interrupted: "已中斷"})[status] || status;
  }

  function jobModeLabel(job) {
    return ({profile: "只拉取 Profile", fancard: "只拉取 Fan Card"})[job.request.mode]
      || (job.request.dry_run ? "完整備份預覽" : "完整備份");
  }

  function jobHistory(jobs, selectedId, creators) {
    const active = jobs.find(item => ["queued", "running", "cancelling"].includes(item.status));
    const filter = customSelect({id: "job-history-filter", label: "篩選工作狀態", value: state.jobFilter, options: [
      {value: "all", label: "全部狀態"}, {value: "completed", label: "已完成"},
      {value: "failed", label: "失敗"}, {value: "interrupted", label: "已中斷"},
      {value: "cancelled", label: "已取消"},
    ], onChange: value => {
      state.jobFilter = value;
      if (selectedId) showJob(selectedId, creators, jobs);
      else renderBackupForm(creators, jobs);
    }});
    const filtered = jobs.filter(item => state.jobFilter === "all" || item.status === state.jobFilter);
    const rows = filtered.map(item => element("button", {
      type: "button", class: `history-row${item.job_id === selectedId ? " selected" : ""}`,
      disabled: active && item.job_id !== active.job_id ? "" : null,
      onclick: () => showJob(item.job_id, creators, jobs),
    },
    element("span", {class: `history-status status-${item.status}`}, statusText(item.status)),
    element("span", {class: "history-main"}, element("strong", {}, jobModeLabel(item)),
      element("small", {}, `${item.request.creator ? `@${item.request.creator}` : "全部創作者"} · ${date(item.created_at)}`)),
    element("span", {class: "history-result"}, item.result
      ? `成功 ${item.result.success} · 失敗 ${item.result.failure}`
      : item.error ? "查看錯誤" : "查看詳情")));
    return element("section", {class: "job-history"},
      element("div", {class: "history-heading"}, element("div", {}, element("p", {class: "eyebrow"}, "JOB HISTORY"), element("h2", {}, "工作歷史")), filter),
      active ? element("p", {class: "history-notice"}, "工作執行期間會鎖定其他歷史項目，避免離開目前進度畫面。") : null,
      element("div", {class: "history-list"}, ...(rows.length ? rows : [element("p", {class: "empty compact"}, "沒有符合條件的工作紀錄。")])))
  }

  async function showJob(jobId, creators, jobs) {
    try { renderJob(await request(`/api/jobs/${jobId}`), creators, jobs); }
    catch (error) { errorView(error); }
  }

  function renderJob(job, creators, jobs = [job]) {
    clearTimeout(jobTimer);
    const active = ["queued", "running", "cancelling"].includes(job.status);
    const plan = (job.events || []).find(item => item.kind === "plan_ready");
    const retryable = ["failed", "cancelled", "interrupted"].includes(job.status);
    const controls = element("div", {class: "job-actions"},
      active ? element("button", {type: "button", class: "danger", onclick: () => cancelJob(job.job_id)}, job.status === "cancelling" ? "正在安全停止…" : "安全停止") : null,
      retryable ? element("button", {type: "button", class: "retry", onclick: () => retryJob(job.job_id)}, "使用相同設定重試") : null,
      !active ? element("button", {type: "button", onclick: () => renderBackupForm(creators, jobs)}, "建立新工作") : null);
    const modeLabel = jobModeLabel(job);
    const page = element("section", {class: "page backup-page", "data-job-id": job.job_id},
      jobPart(element("header", {class: "heading job-heading"}, element("div", {}, element("p", {class: "eyebrow"}, "BACKUP JOB"), element("h1", {}, "備份工作"),
        element("p", {}, modeLabel)), element("span", {class: `job-status status-${job.status}`}, statusText(job.status))),
        "header"),
      jobPart(planSummary(plan, creators) || element("div", {hidden: ""}), "plan"),
      jobPart(currentActivity(job), "activity"),
      jobPart(element("p", {class: "job-error", hidden: job.error ? null : ""}, element("strong", {}, "錯誤："), job.error || ""), "error"),
      jobPart(element("div", {class: "result-strip", hidden: job.result ? null : ""},
        job.result ? [element("span", {}, "選取 ", element("strong", {}, job.result.selected)), element("span", {}, "成功 ", element("strong", {}, job.result.success)),
          element("span", {}, "未變 ", element("strong", {}, job.result.unchanged)), element("span", {}, "失敗 ", element("strong", {}, job.result.failure))] : null), "result"),
      jobPart(controls, "actions"), jobPart(eventLog(job.events || []), "details"),
      jobPart(jobHistory(jobs, job.job_id, creators), "history"));
    const currentPage = app.querySelector(".backup-page[data-job-id]");
    if (currentPage?.dataset.jobId === job.job_id) updateJobPage(currentPage, page, {preserveHistory: active});
    else app.replaceChildren(page);
    if (active) jobTimer = setTimeout(() => pollJob(job.job_id, creators), 900);
  }

  function renderBackupForm(creators, jobs = []) {
    const creatorSelect = customSelect({id: "backup-creator", label: "備份範圍", value: "", options: [
      {value: "", label: "全部支援中的創作者"}, ...creators.map(item => ({value: item.creator_id, label: `${item.name}（${item.creator_id}）`}))
    ]});
    const dryRun = element("input", {id: "backup-dry-run", type: "checkbox", checked: ""});
    const maxPosts = element("input", {id: "backup-max-posts", type: "number", min: 1, max: 100, value: 20});
    app.replaceChildren(element("section", {class: "page backup-page"},
      element("header", {class: "heading"}, element("div", {}, element("p", {class: "eyebrow"}, "BACKUP CONTROL"), element("h1", {}, "開始備份"),
        element("p", {}, "先預覽本次變更，再執行正式備份。"))),
      element("form", {class: "backup-form", onsubmit: event => { event.preventDefault(); startBackup(creatorSelect.value, dryRun.checked, Number(maxPosts.value), "full"); }},
        element("label", {}, element("span", {}, "創作者"), creatorSelect), element("label", {}, element("span", {}, "本次投稿上限"), maxPosts),
        element("label", {class: "checkbox"}, dryRun, element("span", {}, "完整備份只預覽，不下載")), element("button", {type: "submit", class: "primary"}, "開始完整備份"),
        element("div", {class: "metadata-actions"},
          element("div", {}, element("strong", {}, "單項拉取"), element("small", {}, "立即寫入封存，不掃描或下載投稿。")),
          element("div", {class: "metadata-buttons"},
            element("button", {type: "button", onclick: () => startBackup(creatorSelect.value, false, Number(maxPosts.value), "profile")}, "拉取個人資料"),
            element("button", {type: "button", onclick: () => startBackup(creatorSelect.value, false, Number(maxPosts.value), "fancard")}, "拉取粉絲卡")))),
      element("p", {class: "notice"}, "同一時間只允許一個備份工作；安全停止會在目前投稿處理完成後生效。"),
      jobs.length ? jobHistory(jobs, null, creators) : null));
  }

  async function loadBackup() {
    state.current = null;
    app.replaceChildren(element("p", {class: "empty"}, "正在讀取工作狀態…"));
    try {
      const [creatorData, jobData] = await Promise.all([request("/api/creators"), request("/api/jobs")]);
      const backupJobs = jobData.items.filter(item => item.kind === "backup");
      const active = backupJobs.find(item => ["queued", "running", "cancelling"].includes(item.status));
      const latest = backupJobs[0];
      const selected = active || latest;
      if (selected) renderJob(await request(`/api/jobs/${selected.job_id}`), creatorData.items, backupJobs);
      else renderBackupForm(creatorData.items);
    } catch (error) { errorView(error); }
  }

  async function startBackup(creator, dryRun, maxPosts, mode = "full") {
    try {
      const job = await request("/api/jobs/backup", {method: "POST", headers: {"Content-Type": "application/json", "X-Fanbox-Token": sessionToken},
        body: JSON.stringify({creator: creator || null, dry_run: dryRun, max_posts: maxPosts, mode})});
      const [creatorData, jobData] = await Promise.all([request("/api/creators"), request("/api/jobs")]);
      renderJob(job, creatorData.items, jobData.items.filter(item => item.kind === "backup"));
    } catch (error) { errorView(error); }
  }

  async function pollJob(jobId, creators) {
    if (state.view !== "backup") return;
    try {
      const [job, jobData] = await Promise.all([request(`/api/jobs/${jobId}`), request("/api/jobs")]);
      renderJob(job, creators, jobData.items.filter(item => item.kind === "backup"));
    } catch (error) { errorView(error); }
  }

  async function cancelJob(jobId) {
    try {
      const job = await request(`/api/jobs/${jobId}/cancel`, {method: "POST", headers: {"X-Fanbox-Token": sessionToken}});
      const [creatorData, jobData] = await Promise.all([request("/api/creators"), request("/api/jobs")]);
      renderJob(job, creatorData.items, jobData.items.filter(item => item.kind === "backup"));
    } catch (error) { errorView(error); }
  }

  async function retryJob(jobId) {
    try {
      const job = await request(`/api/jobs/${jobId}/retry`, {method: "POST", headers: {"X-Fanbox-Token": sessionToken}});
      const [creatorData, jobData] = await Promise.all([request("/api/creators"), request("/api/jobs")]);
      renderJob(job, creatorData.items, jobData.items.filter(item => item.kind === "backup"));
    } catch (error) { errorView(error); }
  }

  function verificationHistory(jobs, selectedId) {
    const active = jobs.find(item => ["queued", "running", "cancelling"].includes(item.status));
    const rows = jobs.map(item => element("button", {
      type: "button", class: `history-row${item.job_id === selectedId ? " selected" : ""}`,
      disabled: active && item.job_id !== active.job_id ? "" : null,
      onclick: () => showVerification(item.job_id, jobs),
    }, element("span", {class: `history-status status-${item.status}`}, statusText(item.status)),
    element("span", {class: "history-main"}, element("strong", {}, "封存完整性驗證"), element("small", {}, date(item.created_at))),
    element("span", {class: "history-result"}, item.result
      ? item.result.passed ? "驗證通過" : `${item.result.issue_count} 個問題`
      : item.error ? "查看錯誤" : "查看進度")));
    return element("section", {class: "job-history"},
      element("div", {class: "history-heading"}, element("div", {}, element("p", {class: "eyebrow"}, "VERIFY HISTORY"), element("h2", {}, "驗證歷史"))),
      active ? element("p", {class: "history-notice"}, "驗證執行期間會鎖定其他歷史項目。") : null,
      element("div", {class: "history-list"}, ...(rows.length ? rows : [element("p", {class: "empty compact"}, "尚無驗證紀錄。")])));
  }

  function renderMaintenance(job = null, jobs = []) {
    clearTimeout(jobTimer);
    const active = job && ["queued", "running", "cancelling"].includes(job.status);
    const issues = job?.result?.issues || [];
    const result = job?.result;
    const issueRows = issues.map(item => element("li", {},
      element("strong", {}, item.reason), element("code", {}, item.path),
      item.post_id ? element("small", {}, `Post ${item.post_id}`) : null));
    app.replaceChildren(element("section", {class: "page maintenance-page"},
      element("header", {class: "heading"}, element("div", {}, element("p", {class: "eyebrow"}, "ARCHIVE MAINTENANCE"), element("h1", {}, "封存驗證"),
        element("p", {}, "檢查投稿、Profile、粉絲卡、歷史版本與資源的檔案大小及 SHA-256。")),
        job ? element("span", {class: `job-status status-${job.status}`}, statusText(job.status)) : null),
      element("section", {class: "maintenance-action"},
        element("div", {}, element("h2", {}, active ? "正在驗證封存…" : "完整性檢查"),
          element("p", {}, "驗證可能需要一段時間；執行期間不能同時開始備份或修改設定。")),
        element("button", {type: "button", class: "primary", disabled: active ? "" : null, onclick: startVerification}, active ? "驗證中…" : "開始驗證")),
      job?.error ? element("p", {class: "job-error"}, element("strong", {}, "錯誤："), job.error) : null,
      result ? element("section", {class: `verification-result ${result.passed ? "passed" : "issues"}`},
        element("div", {class: "verification-summary"}, element("strong", {}, result.passed ? "驗證通過" : `${result.issue_count} 個問題`),
          element("span", {}, result.passed ? "目前封存未發現完整性問題。" : "請檢查下列缺失或損毀項目。")),
        issueRows.length ? element("ul", {class: "verification-issues"}, ...issueRows) : null,
        result.truncated ? element("p", {class: "notice"}, "問題數量過多，目前只顯示前 500 項。") : null) : null,
      verificationHistory(jobs, job?.job_id || null)));
    if (active) jobTimer = setTimeout(() => pollVerification(job.job_id), 900);
  }

  async function loadMaintenance() {
    state.current = null;
    app.replaceChildren(element("p", {class: "empty"}, "正在讀取驗證狀態…"));
    try {
      const data = await request("/api/jobs");
      const jobs = data.items.filter(item => item.kind === "verify");
      const active = jobs.find(item => ["queued", "running", "cancelling"].includes(item.status));
      const selected = active || jobs[0];
      renderMaintenance(selected ? await request(`/api/jobs/${selected.job_id}`) : null, jobs);
    } catch (error) { errorView(error); }
  }

  async function startVerification() {
    try {
      const job = await request("/api/jobs/verify", {method: "POST", headers: {"X-Fanbox-Token": sessionToken}});
      const data = await request("/api/jobs");
      renderMaintenance(job, data.items.filter(item => item.kind === "verify"));
    } catch (error) { errorView(error); }
  }

  async function pollVerification(jobId) {
    if (state.view !== "maintenance") return;
    try {
      const [job, data] = await Promise.all([request(`/api/jobs/${jobId}`), request("/api/jobs")]);
      renderMaintenance(job, data.items.filter(item => item.kind === "verify"));
    } catch (error) { errorView(error); }
  }

  async function showVerification(jobId, jobs) {
    try { renderMaintenance(await request(`/api/jobs/${jobId}`), jobs); }
    catch (error) { errorView(error); }
  }

  const settingCheckbox = (label, checked) => {
    const input = element("input", {type: "checkbox", checked: checked ? "" : null});
    return {input, node: element("label", {class: "setting-toggle"}, input, element("span", {}, label))};
  };

  const settingNumber = (label, value, min, max, step = 1, hint = null) => {
    const input = element("input", {type: "number", value, min, max, step});
    return {input, node: element("label", {class: "setting-field"}, element("span", {}, label), input, hint ? element("small", {}, hint) : null)};
  };

  async function loadSettings(message = "") {
    state.current = null;
    app.replaceChildren(element("p", {class: "empty"}, "正在讀取設定…"));
    try {
      const data = await request("/api/config");
      renderSettings(data, message);
    } catch (error) { errorView(error); }
  }

  function renderSettings(data, message = "") {
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
    const maxPosts = settingNumber("每次投稿上限", value.sync.max_posts_per_run, 1, 100);
    const unchangedStop = settingNumber("連續未變時停止回補", value.sync.recent_unchanged_stop_count, 1, 500);
    const markdown = settingCheckbox("產生 Markdown", value.markdown.enabled);
    const frontMatter = settingCheckbox("加入 YAML front matter", value.markdown.yaml_front_matter);
    const relativePaths = settingCheckbox("Markdown 使用相對圖片路徑", value.markdown.relative_image_paths);
    const preserveOrder = settingCheckbox("保留原始內容順序", value.markdown.preserve_original_order);
    const fileLogs = settingCheckbox("寫入檔案日誌", value.logging.write_to_file);
    const keepDays = settingNumber("日誌保留天數", value.logging.keep_days, 1, 365);
    const logLevel = customSelect({id: "log-level", label: "日誌等級", value: value.logging.level,
      options: ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"].map(item => ({value: item, label: item}))});
    const form = element("form", {class: "settings-form", onsubmit: event => {
      event.preventDefault();
      saveSettings({download: {
        original_images: originalImages.input.checked, download_attachments: attachments.input.checked,
        download_cover: covers.input.checked, resume: resume.input.checked, verify_sha256: hashes.input.checked,
        retry_count: Number(retries.input.value), request_interval_seconds: Number(interval.input.value), timeout_seconds: Number(timeout.input.value),
      }, sync: {
        skip_completed: skipCompleted.input.checked, check_updates: checkUpdates.input.checked,
        preserve_deleted_posts: preserveDeleted.input.checked, rotate_creators: rotate.input.checked,
        max_posts_per_run: Number(maxPosts.input.value), recent_unchanged_stop_count: Number(unchangedStop.input.value),
      }, markdown: {
        enabled: markdown.input.checked, yaml_front_matter: frontMatter.input.checked,
        relative_image_paths: relativePaths.input.checked, preserve_original_order: preserveOrder.input.checked,
      }, logging: {level: logLevel.value, write_to_file: fileLogs.input.checked, keep_days: Number(keepDays.input.value)}});
    }},
    element("section", {class: "settings-card"}, element("p", {class: "eyebrow"}, "DOWNLOAD"), element("h2", {}, "下載"),
      element("div", {class: "settings-grid"}, retries.node, interval.node, timeout.node),
      element("div", {class: "setting-toggles"}, originalImages.node, attachments.node, covers.node, resume.node, hashes.node)),
    element("section", {class: "settings-card"}, element("p", {class: "eyebrow"}, "SYNC"), element("h2", {}, "同步"),
      element("div", {class: "settings-grid"}, maxPosts.node, unchangedStop.node),
      element("div", {class: "setting-toggles"}, skipCompleted.node, checkUpdates.node, preserveDeleted.node, rotate.node)),
    element("section", {class: "settings-card"}, element("p", {class: "eyebrow"}, "OUTPUT"), element("h2", {}, "Markdown 與日誌"),
      element("div", {class: "settings-grid"}, element("label", {class: "setting-field"}, element("span", {}, "日誌等級"), logLevel), keepDays.node),
      element("div", {class: "setting-toggles"}, markdown.node, frontMatter.node, relativePaths.node, preserveOrder.node, fileLogs.node)),
    element("div", {class: "settings-actions"}, element("button", {type: "submit", class: "primary", disabled: data.writable ? null : ""}, "儲存設定"),
      !data.writable ? element("span", {class: "notice"}, "目前伺服器未指定可寫入的設定檔。") : null));
    app.replaceChildren(element("section", {class: "page settings-page"},
      element("header", {class: "heading"}, element("div", {}, element("p", {class: "eyebrow"}, "LOCAL SETTINGS"), element("h1", {}, "設定"),
        element("p", {}, "只顯示安全的一般選項；儲存與認證路徑維持唯讀。"))),
      message ? element("p", {class: "settings-saved", role: "status"}, message) : null,
      element("section", {class: "settings-paths"}, element("div", {}, element("span", {}, "封存目錄"), element("code", {}, data.storage.output_dir)),
        element("div", {}, element("span", {}, "資料庫"), element("code", {}, data.storage.database)),
        element("div", {}, element("span", {}, "設定檔"), element("code", {}, data.config_path || "未指定"))), form));
  }

  async function saveSettings(patch) {
    try {
      await request("/api/config", {method: "PATCH", headers: {"Content-Type": "application/json", "X-Fanbox-Token": sessionToken}, body: JSON.stringify(patch)});
      loadSettings("設定已安全寫入；後續新工作會使用更新後的值。日誌處理器變更會在重新啟動後完整套用。");
    } catch (error) { errorView(error); }
  }

  search.addEventListener("input", event => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => { state.q = event.target.value.trim(); state.page = 1; refreshView(); }, 180);
  });
  nav.addEventListener("click", event => {
    if (!event.target.dataset.view) return;
    state.q = "";
    search.value = "";
    setView(event.target.dataset.view);
  });
  window.addEventListener("keydown", event => {
    if (["ArrowLeft", "ArrowRight"].includes(event.key) && typeof state.current === "string" && state.postNavigation) {
      const target = event.target;
      const interactive = target instanceof Element && (
        target.matches("input,textarea,select,button,a,summary,[contenteditable='true']")
        || target.closest(".custom-select,.page-jump")
      );
      if (!interactive && !event.altKey && !event.ctrlKey && !event.metaKey && !event.shiftKey) {
        const neighbor = event.key === "ArrowLeft" ? state.postNavigation.previous : state.postNavigation.next;
        if (neighbor) {
          event.preventDefault();
          loadPost(neighbor.post_id);
        }
        return;
      }
    }
    if (event.key !== "Escape") return;
    const openDropdowns = [...document.querySelectorAll(".custom-select[open], .page-jump[open]")];
    if (openDropdowns.length) {
      for (const dropdown of openDropdowns) {
        dropdown.open = false;
        dropdown.querySelector("summary")?.focus();
      }
      return;
    }
    if (state.current) refreshView();
  });
  setView("posts");
})();
