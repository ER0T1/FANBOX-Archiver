(() => {
  "use strict";
  const data = window.__FANBOX_ARCHIVE_DATA__ || {stats:{}, creators:[], posts:[], fancards:[], warnings:[]};
  const root = document.getElementById("app");
  const state = {view:"overview", q:"", creator:"", tag:"", status:"", year:"", versioned:"", sort:"published", order:"desc", page:1};
  const PAGE_SIZE = 20;
  const GITHUB_URL = "https://github.com/ER0T1/FANBOX-Archiver";
  // Octicons mark-github (MIT), inlined so the offline site never loads a remote icon.
  const GITHUB_MARK = "M8 0c4.42 0 8 3.58 8 8a8.013 8.013 0 0 1-5.45 7.59c-.4.08-.55-.17-.55-.38 0-.27.01-1.13.01-2.2 0-.75-.25-1.23-.54-1.48 1.78-.2 3.65-.88 3.65-3.95 0-.88-.31-1.59-.82-2.15.08-.2.36-1.02-.08-2.12 0 0-.67-.22-2.2.82-.64-.18-1.32-.27-2-.27-.68 0-1.36.09-2 .27-1.53-1.03-2.2-.82-2.2-.82-.44 1.1-.16 1.92-.08 2.12-.51.56-.82 1.28-.82 2.15 0 3.06 1.86 3.75 3.64 3.95-.23.2-.44.55-.51 1.07-.46.21-1.61.55-2.33-.66-.15-.24-.6-.83-1.23-.82-.67.01-.27.38.01.53.34.19.73.9.82 1.13.16.45.68 1.31 2.69.94 0 .67.01 1.3.01 1.49 0 .21-.15.45-.55.38A7.995 7.995 0 0 1 0 8c0-4.42 3.58-8 8-8Z";
  const TIME_SORTS = new Set(["published", "updated"]);
  // Hashes written before v1.3.31 combined key and direction, e.g. "published-desc".
  const LEGACY_SORTS = {"published-desc":["published"], "updated-desc":["updated"], "title-asc":["title"], "versions-desc":["versions"]};

  // Interface text comes from assets/i18n.js, written next to this file at export time; the
  // site never loads translations from the network. A missing key shows as the key itself.
  const i18n = window.FanboxI18n || {locale:"zh-Hant", intl:"zh-Hant", messages:{}};
  const numberFormat = new Intl.NumberFormat(i18n.intl || "zh-Hant");
  const pluralRules = new Intl.PluralRules(i18n.intl || "zh-Hant");
  function t(key, params = {}) {
    let message = i18n.messages[key];
    if (message === undefined) return key;
    if (typeof message !== "string") message = message[pluralRules.select(Number(params.count || 0))] || message.other || key;
    return message.replace(/\{([a-z_][a-z0-9_]*)\}/g, (match, name) => {
      const value = params[name];
      if (value === undefined) return match;
      return typeof value === "number" ? numberFormat.format(value) : String(value);
    });
  }

  function node(tag, attrs = {}, ...children) {
    const element = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
      if (key === "class") element.className = value;
      else if (key.startsWith("on") && typeof value === "function") element.addEventListener(key.slice(2), value);
      else if (value !== null && value !== undefined) element.setAttribute(key, String(value));
    }
    for (const child of children.flat()) {
      if (child === null || child === undefined) continue;
      element.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return element;
  }

  const normalise = value => String(value || "").normalize("NFKC").toLocaleLowerCase().replace(/\s+/g, " ").trim();
  // The zone in effect when the archive was exported, so every computer shows the same dates.
  const displayTimeZone = data.timezone || "Asia/Taipei";
  const dateTimeFormatter = new Intl.DateTimeFormat("en-CA", {
    timeZone:displayTimeZone, year:"numeric", month:"2-digit", day:"2-digit",
    hour:"2-digit", minute:"2-digit", hourCycle:"h23",
  });
  const explicitOffset = /(?:Z|[+-]\d{2}:?\d{2})$/i;
  const formatDate = value => {
    if (!value) return "—";
    const text = String(value).trim();
    if (!explicitOffset.test(text)) return `${text}（時區未標示）`;
    const date = new Date(text);
    if (Number.isNaN(date.valueOf())) return String(value);
    const parts = Object.fromEntries(dateTimeFormatter.formatToParts(date).map(part => [part.type, part.value]));
    return `${parts.year}年${parts.month}月${parts.day}日 ${parts.hour}:${parts.minute}`;
  };
  const displayYear = value => /^\d{4}/.exec(formatDate(value))?.[0] || "";

  function readHash() {
    const params = new URLSearchParams(location.hash.replace(/^#/, ""));
    state.view = params.get("view") || "overview";
    state.q = params.get("q") || "";
    state.creator = params.get("creator") || "";
    state.tag = params.get("tag") || "";
    state.status = params.get("status") || "";
    state.year = params.get("year") || "";
    state.versioned = params.get("versioned") || "";
    const legacySort = LEGACY_SORTS[params.get("sort")]?.[0];
    state.sort = legacySort || (["published","updated","title","versions"].includes(params.get("sort")) ? params.get("sort") : "published");
    state.order = params.get("order") === "asc" ? "asc" : "desc";
    state.page = Math.max(1, Number.parseInt(params.get("page") || "1", 10) || 1);
  }
  function writeHash(push = false) {
    const params = new URLSearchParams();
    if (state.view !== "overview") params.set("view", state.view);
    if (state.q) params.set("q", state.q);
    if (state.creator) params.set("creator", state.creator);
    if (state.tag) params.set("tag", state.tag);
    if (state.status) params.set("status", state.status);
    if (state.year) params.set("year", state.year);
    if (state.versioned) params.set("versioned", state.versioned);
    if (state.sort !== "published") params.set("sort", state.sort);
    if (state.order !== "desc" && TIME_SORTS.has(state.sort)) params.set("order", state.order);
    if (state.page > 1) params.set("page", state.page);
    const url = params.size ? `${location.pathname}${location.search}#${params}` : `${location.pathname}${location.search}`;
    history[push ? "pushState" : "replaceState"](null, "", url);
  }
  function navButton(label, view, count) {
    return node("button", {
      class:`nav-item ${state.view === view ? "active" : ""}`,
      type:"button", onclick:() => { state.view = view; state.page = 1; state.tag = ""; writeHash(); render(); },
      "aria-current":state.view === view ? "page" : null,
    }, node("span", {}, label), node("span", {class:"nav-count"}, count));
  }

  function githubLink() {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 16 16");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", GITHUB_MARK);
    svg.append(path);
    return node("a", {class:"github-link", href:GITHUB_URL, target:"_blank", rel:"noopener noreferrer",
      "aria-label":t("header.github_label"), title:t("header.github_title")}, svg, node("span", {class:"github-label"}, "GitHub"));
  }

  function shell(content) {
    const search = node("input", {type:"search", value:state.q, placeholder:t("static.search_placeholder"), "aria-label":t("static.search_label")});
    search.addEventListener("input", event => { state.q = event.target.value; state.page = 1; writeHash(); renderMain(); });
    const theme = node("button", {class:"icon-button", type:"button", "data-theme-toggle":""}, window.FanboxTheme.current() === "dark" ? "☾" : window.FanboxTheme.current() === "light" ? "☀" : "◐");
    const menu = node("button", {class:"menu-button", type:"button", "aria-label":t("static.open_menu"), "aria-expanded":document.body.classList.contains("menu-open"), onclick:() => document.body.classList.toggle("menu-open")}, "☰");
    const topbar = node("header", {class:"topbar"}, menu, node("a", {class:"brand", href:"index.html"}, "FANBOX Archive"), search, githubLink(), theme);
    const sidebar = node("aside", {class:"sidebar"},
      node("nav", {"aria-label":t("static.nav_label")},
        navButton(t("static.nav_overview"), "overview", ""), navButton(t("static.nav_posts"), "posts", data.stats.posts || 0),
        navButton(t("static.nav_creators"), "creators", data.stats.creators || 0), navButton(t("static.nav_fancards"), "fancards", data.stats.fancards || 0),
        navButton(t("static.nav_issues"), "issues", data.stats.issues || 0)),
      node("div", {class:"sidebar-creators"}, node("h2", {}, t("static.sidebar_creators")), ...data.creators.map(creator =>
        node("button", {type:"button", onclick:() => {state.creator=creator.creator_id; state.tag=""; state.view="posts"; writeHash(); render();}},
          creator.avatar ? node("img", {class:"creator-avatar small", src:creator.avatar, alt:""}) : node("span", {class:"avatar-fallback small"}, creator.name.slice(0,1)),
          node("span", {}, creator.name), node("small", {}, creator.post_count))))
    );
    return node("div", {class:"app-shell"}, topbar, sidebar, node("main", {id:"main", class:"main", tabindex:"-1"}, content));
  }

  function heading(title, subtitle) {
    return node("header", {class:"page-heading"}, node("div", {}, node("p", {class:"eyebrow"}, "PRIVATE LOCAL ARCHIVE"), node("h1", {}, title), node("p", {class:"muted"}, subtitle)));
  }
  function stat(label, value, tone="") { return node("div", {class:`stat ${tone}`}, node("strong", {}, value), node("span", {}, label)); }
  function badge(status) { return node("span", {class:`badge status-${status}`}, status); }
  function feeLabel(value) {
    if (value === null || value === undefined) return "檔位未知";
    return Number(value) <= 0 ? "全體公開" : `¥${new Intl.NumberFormat().format(value)}`;
  }

  function matchesPost(post) {
    if (state.creator && post.creator_id !== state.creator) return false;
    if (state.tag && !(post.tags || []).includes(state.tag)) return false;
    if (state.status && post.status !== state.status) return false;
    if (state.year && displayYear(post.published_at) !== state.year) return false;
    if (state.versioned === "yes" && post.version_count < 2) return false;
    const haystack = normalise([post.title, post.post_id, post.creator_id, ...(post.tags || [])].join(" "));
    return normalise(state.q).split(" ").every(term => !term || haystack.includes(term));
  }

  function controls() {
    const resetPage = () => { state.page = 1; writeHash(); renderMain(); };
    const creatorSelect = node("select", {"aria-label":t("static.filter_creator"), onchange:event => {state.creator=event.target.value; state.tag=""; resetPage();}},
      node("option", {value:""}, t("static.filter_creator_all")), ...data.creators.map(item => node("option", {value:item.creator_id}, item.name)));
    creatorSelect.value = state.creator;
    const statusSelect = node("select", {"aria-label":t("static.filter_status"), onchange:event => {state.status=event.target.value; resetPage();}},
      node("option", {value:""}, t("static.filter_status_all")), ...["completed","partial","failed","restricted","unavailable","missing"].map(value => node("option", {value}, value)));
    statusSelect.value = state.status;
    const years = [...new Set(data.posts.map(post => displayYear(post.published_at)).filter(value => /^\d{4}$/.test(value)))].sort().reverse();
    const yearSelect = node("select", {"aria-label":t("static.filter_year"), onchange:event => {state.year=event.target.value; resetPage();}},
      node("option", {value:""}, t("static.filter_year_all")), ...years.map(value => node("option", {value}, value)));
    yearSelect.value = state.year;
    const versionSelect = node("select", {"aria-label":t("static.filter_versions"), onchange:event => {state.versioned=event.target.value; resetPage();}},
      node("option", {value:""}, t("static.filter_versions_all")), node("option", {value:"yes"}, t("static.filter_versions_multi")));
    versionSelect.value = state.versioned;
    const sortSelect = node("select", {"aria-label":t("static.sort_by"), onchange:event => {state.sort=event.target.value; resetPage();}},
      node("option", {value:"published"}, t("static.sort_published")), node("option", {value:"updated"}, t("static.sort_updated")),
      node("option", {value:"title"}, t("static.sort_title")), node("option", {value:"versions"}, t("static.sort_versions")));
    sortSelect.value = state.sort;
    const timeSort = TIME_SORTS.has(state.sort);
    const orderLabel = state.order === "desc" ? t("common.sort_desc") : t("common.sort_asc");
    const orderToggle = node("button", {class:"sort-toggle", type:"button", "data-order":state.order,
      disabled:timeSort ? null : "", "aria-label":timeSort ? t("common.sort_label", {label:t("common.sort_time"), order:orderLabel}) : t("static.sort_time_disabled"),
      onclick:() => {state.order = state.order === "desc" ? "asc" : "desc"; resetPage();}}, state.order === "desc" ? t("common.sort_desc_button") : t("common.sort_asc_button"));
    const clear = node("button", {class:"secondary", type:"button", onclick:() => {state.creator=""; state.tag=""; state.status=""; state.year=""; state.versioned=""; state.q=""; state.sort="published"; state.order="desc"; state.page=1; writeHash(); render();}}, t("static.clear_filters"));
    return node("div", {class:"controls"}, creatorSelect, statusSelect, yearSelect, versionSelect, sortSelect, orderToggle, clear);
  }

  function sortedPosts(items) {
    const result = [...items];
    const byTime = key => (a, b) => {
      const value = String(a[key] || "").localeCompare(String(b[key] || "")) || a.post_id.localeCompare(b.post_id);
      return state.order === "asc" ? value : -value;
    };
    if (state.sort === "updated") result.sort(byTime("updated_at"));
    else if (state.sort === "title") result.sort((a,b) => a.title.localeCompare(b.title));
    else if (state.sort === "versions") result.sort((a,b) => b.version_count - a.version_count || byTime("published_at")(a,b));
    else result.sort(byTime("published_at"));
    // A creator's pinned posts stay on top whichever way the list is sorted.
    if (state.creator) result.sort((a, b) => Number(Boolean(b.is_pinned)) - Number(Boolean(a.is_pinned)));
    return result;
  }

  function pagination(total, pageSize=PAGE_SIZE) {
    const pages = Math.max(1, Math.ceil(total / pageSize));
    state.page = Math.min(state.page, pages);
    if (pages === 1) return null;
    return node("nav", {class:"pagination", "aria-label":t("static.pagination")},
      node("button", {class:"secondary", type:"button", disabled:state.page === 1 ? "" : null, onclick:() => {state.page--; writeHash(); renderMain();}}, t("common.previous_page")),
      node("span", {}, t("static.page_position", {page:state.page, pages})),
      node("button", {class:"secondary", type:"button", disabled:state.page === pages ? "" : null, onclick:() => {state.page++; writeHash(); renderMain();}}, t("common.next_page")));
  }

  function postCard(post) {
    const link = post.latest_path || "#";
    return node("a", {class:`post-card ${post.latest_path ? "" : "disabled"}`, href:link, "aria-label":`${post.title}，${post.version_count} 版`},
      post.cover ? node("img", {class:"post-card-cover", src:post.cover, alt:"", loading:"lazy"}) : node("div", {class:"post-card-cover placeholder", "aria-hidden":"true"}, "無封面"),
      node("div", {class:"post-card-main"},
        node("div", {class:"post-meta"}, node("span", {}, formatDate(post.published_at)), node("span", {class:"fee-badge"}, feeLabel(post.fee_required)), badge(post.status)),
        node("h2", {}, post.title),
        node("p", {class:"muted"}, `${post.creator_id} · Post ${post.post_id}`),
        node("div", {class:"tag-row"}, ...(post.tags || []).slice(0, 5).map(tag => node("span", {class:"tag"}, tag)))),
      node("div", {class:"post-card-side"}, node("strong", {}, `${post.version_count} 版`),
        node("span", {class:"card-chevron", "aria-hidden":"true"}, post.latest_path ? "›" : "—")));
  }

  function overview() {
    const recent = data.posts.filter(matchesPost).slice(0, 8);
    return node("div", {}, heading("本機備份", `建置於 ${formatDate(data.built_at)} · 完全離線`),
      node("section", {class:"stats-grid", "aria-label":"備份統計"}, stat("文章", data.stats.posts || 0), stat("版本", data.stats.versions || 0), stat("Fan Card", data.stats.fancards || 0, "amber"), stat("異常", data.stats.issues || 0, data.stats.issues ? "danger" : "")),
      node("section", {class:"section"}, node("div", {class:"section-title"}, node("h2", {}, "最近文章"), node("button", {class:"text-button", onclick:() => {state.view="posts"; writeHash(); render();}}, "查看全部")),
        node("div", {class:"post-list"}, ...(recent.length ? recent.map(postCard) : [node("p", {class:"empty"}, "尚無文章。")]))));
  }

  function postsView() {
    const items = sortedPosts(data.posts.filter(matchesPost));
    const pageSize = PAGE_SIZE;
    const pageItems = items.slice((state.page - 1) * pageSize, state.page * pageSize);
    const creatorPosts = state.creator ? data.posts.filter(post => post.creator_id === state.creator) : [];
    const counts = new Map();
    for (const post of creatorPosts) for (const tag of new Set(post.tags || [])) counts.set(tag, (counts.get(tag) || 0) + 1);
    const facets = [...counts.entries()].sort((a,b) => b[1] - a[1] || a[0].localeCompare(b[0], "zh-Hant"));
    const tagFilter = state.creator ? node("section", {class:"tag-filter", "aria-label":"依標籤篩選投稿"},
      node("div", {class:"tag-filter-title"}, node("strong", {}, "標籤篩選"), node("span", {class:"muted"}, state.tag ? `目前：${state.tag}` : "顯示全部文章")),
      node("div", {class:"tag-filter-options"},
        node("button", {type:"button", class:state.tag ? "" : "active", "aria-pressed":state.tag ? "false" : "true", onclick:() => {state.tag=""; state.page=1; writeHash(true); renderMain();}}, `全部 ${creatorPosts.length}`),
        ...(facets.length ? facets.map(([tag,count]) => node("button", {type:"button", class:state.tag === tag ? "active" : "", "aria-pressed":state.tag === tag ? "true" : "false", onclick:() => {state.tag=tag; state.page=1; writeHash(true); renderMain();}}, `${tag} ${count}`)) : [node("span", {class:"muted"}, "尚無已保存的投稿標籤")]))) : null;
    return node("div", {}, heading(t("static.posts_title"), t("static.posts_matching", {count:items.length})), controls(), tagFilter, node("div", {class:"post-list"}, ...(pageItems.length ? pageItems.map(postCard) : [node("p", {class:"empty"}, t("static.posts_empty"))])), pagination(items.length, pageSize));
  }

  function creatorsView() {
    const terms = normalise(state.q).split(" ").filter(Boolean);
    const creators = data.creators
      .filter(item => terms.every(term => normalise(`${item.name} ${item.creator_id}`).includes(term)))
      .sort((a, b) => a.name.localeCompare(b.name, "zh-Hant"));
    const cards = creators.map(item => node("article", {class:"creator-card"},
      item.avatar
        ? node("img", {class:"creator-avatar", src:item.avatar, alt:`${item.name} 頭像`, loading:"lazy"})
        : node("div", {class:"avatar-fallback"}, item.name.slice(0,1)),
      node("div", {},
        node("h2", {}, item.name),
        node("code", {}, item.creator_id),
        node("p", {class:"muted"}, `${item.post_count} 篇文章 · ${item.fancard_months || 0} 個 Fan Card 月份 · ${item.profile_version_count || 0} 版 Profile`),
        node("div", {class:"creator-actions"},
          item.profile_latest_path ? node("a", {class:"secondary", href:item.profile_latest_path}, "Creator Profile") : null,
          node("button", {class:"text-button", onclick:() => {
            state.creator = item.creator_id;
            state.tag = "";
            state.view = "posts";
            writeHash();
            render();
          }}, "查看文章 →")))));
    return node("div", {}, heading("創作者", `${creators.length} 位符合目前條件`),
      node("div", {class:"creator-grid"}, ...(cards.length ? cards : [node("p", {class:"empty"}, "沒有符合條件的創作者。")])));
  }

  function fancardsView() {
    const term = normalise(state.q);
    const cards = data.fancards
      .filter(card => (!state.creator || card.creator_id === state.creator) && (!term || normalise(`${card.creator_id} ${card.target_month} ${card.plan_title}`).includes(term)))
      .sort((a, b) => String(b.target_month || "").localeCompare(String(a.target_month || "")) || a.creator_id.localeCompare(b.creator_id));
    return node("div", {}, heading("Fan Card", "卡面與方案資訊只保存在本機"), controls(), node("div", {class:"fancard-grid"}, ...(cards.length ? cards.map(card =>
      node("article", {class:"fancard-card"}, card.thumbnail ? node("img", {src:card.thumbnail, alt:`${card.creator_id} ${card.target_month} Fan Card`, loading:"lazy"}) : node("div", {class:"image-placeholder"}, "無卡面"),
        node("div", {class:"fancard-body"}, node("p", {class:"eyebrow"}, card.target_month), node("h2", {}, card.creator_id), node("p", {}, card.plan_title),
          node("p", {class:"muted"}, `¥${card.fee || 0}/月 · ${card.version_count} 版`), node("a", {class:"primary amber", href:card.latest_path}, "查看 Fan Card →")))) : [node("p", {class:"empty"}, "沒有符合條件的 Fan Card。")])));
  }

  function issuesView() {
    const problematic = data.posts.filter(post => post.status !== "completed");
    return node("div", {}, heading("異常項目", "此頁只提供診斷，不會修改備份"),
      node("section", {class:"section"}, node("h2", {}, "文章狀態"), node("div", {class:"post-list"}, ...(problematic.length ? problematic.map(postCard) : [node("p", {class:"empty"}, "沒有異常文章。")]))),
      node("section", {class:"section"}, node("h2", {}, "建置警告"), node("ul", {class:"warning-list"}, ...(data.warnings.length ? data.warnings.map(value => node("li", {}, value)) : [node("li", {}, "沒有建置警告。")]))));
  }

  function currentView() {
    if (state.view === "posts") return postsView();
    if (state.view === "creators") return creatorsView();
    if (state.view === "fancards") return fancardsView();
    if (state.view === "issues") return issuesView();
    return overview();
  }
  function renderMain() {
    const main = document.getElementById("main");
    if (main) main.replaceChildren(currentView());
  }
  function render() { root.replaceChildren(shell(currentView())); document.body.classList.remove("menu-open"); window.FanboxTheme.bindAll(); }
  window.addEventListener("hashchange", () => { readHash(); render(); });
  window.addEventListener("popstate", () => { readHash(); render(); });
  window.addEventListener("keydown", event => { if (event.key === "Escape") document.body.classList.remove("menu-open"); });
  readHash(); render();
})();
