(() => {
  "use strict";
  const data = window.__FANBOX_ARCHIVE_DATA__ || {stats:{}, creators:[], posts:[], fancards:[], warnings:[]};
  const root = document.getElementById("app");
  const state = {view:"overview", q:"", creator:"", status:"", year:"", versioned:"", sort:"published-desc", page:1};

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
  const taipeiDateTime = new Intl.DateTimeFormat("en-CA", {
    timeZone:"Asia/Taipei", year:"numeric", month:"2-digit", day:"2-digit",
    hour:"2-digit", minute:"2-digit", hourCycle:"h23",
  });
  const formatDate = value => {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.valueOf())) return String(value);
    const parts = Object.fromEntries(taipeiDateTime.formatToParts(date).map(part => [part.type, part.value]));
    return `${parts.year}年${parts.month}月${parts.day}日 ${parts.hour}:${parts.minute}`;
  };
  const taipeiYear = value => /^\d{4}/.exec(formatDate(value))?.[0] || "";

  function readHash() {
    const params = new URLSearchParams(location.hash.replace(/^#/, ""));
    state.view = params.get("view") || "overview";
    state.q = params.get("q") || "";
    state.creator = params.get("creator") || "";
    state.status = params.get("status") || "";
    state.year = params.get("year") || "";
    state.versioned = params.get("versioned") || "";
    state.sort = params.get("sort") || "published-desc";
    state.page = Math.max(1, Number.parseInt(params.get("page") || "1", 10) || 1);
  }
  function writeHash() {
    const params = new URLSearchParams();
    if (state.view !== "overview") params.set("view", state.view);
    if (state.q) params.set("q", state.q);
    if (state.creator) params.set("creator", state.creator);
    if (state.status) params.set("status", state.status);
    if (state.year) params.set("year", state.year);
    if (state.versioned) params.set("versioned", state.versioned);
    if (state.sort !== "published-desc") params.set("sort", state.sort);
    if (state.page > 1) params.set("page", state.page);
    history.replaceState(null, "", params.size ? `${location.pathname}${location.search}#${params}` : `${location.pathname}${location.search}`);
  }
  function navButton(label, view, count) {
    return node("button", {
      class:`nav-item ${state.view === view ? "active" : ""}`,
      type:"button", onclick:() => { state.view = view; state.page = 1; writeHash(); render(); },
      "aria-current":state.view === view ? "page" : null,
    }, node("span", {}, label), node("span", {class:"nav-count"}, count));
  }

  function shell(content) {
    const search = node("input", {type:"search", value:state.q, placeholder:"搜尋標題、ID、創作者、標籤…", "aria-label":"搜尋"});
    search.addEventListener("input", event => { state.q = event.target.value; state.page = 1; writeHash(); renderMain(); });
    const theme = node("button", {class:"icon-button", type:"button", "data-theme-toggle":""}, window.FanboxTheme.current() === "dark" ? "☾" : window.FanboxTheme.current() === "light" ? "☀" : "◐");
    const menu = node("button", {class:"menu-button", type:"button", "aria-label":"開啟導覽", "aria-expanded":document.body.classList.contains("menu-open"), onclick:() => document.body.classList.toggle("menu-open")}, "☰");
    const topbar = node("header", {class:"topbar"}, menu, node("a", {class:"brand", href:"index.html"}, "FANBOX Archive"), search, theme);
    const sidebar = node("aside", {class:"sidebar"},
      node("nav", {"aria-label":"主要導覽"},
        navButton("總覽", "overview", ""), navButton("文章", "posts", data.stats.posts || 0),
        navButton("創作者", "creators", data.stats.creators || 0), navButton("Fan Card", "fancards", data.stats.fancards || 0),
        navButton("異常項目", "issues", data.stats.issues || 0)),
      node("div", {class:"sidebar-creators"}, node("h2", {}, "創作者"), ...data.creators.map(creator =>
        node("button", {type:"button", onclick:() => {state.creator=creator.creator_id; state.view="posts"; writeHash(); render();}},
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
    if (state.status && post.status !== state.status) return false;
    if (state.year && taipeiYear(post.published_at) !== state.year) return false;
    if (state.versioned === "yes" && post.version_count < 2) return false;
    const haystack = normalise([post.title, post.post_id, post.creator_id, ...(post.tags || [])].join(" "));
    return normalise(state.q).split(" ").every(term => !term || haystack.includes(term));
  }

  function controls() {
    const resetPage = () => { state.page = 1; writeHash(); renderMain(); };
    const creatorSelect = node("select", {"aria-label":"依創作者篩選", onchange:event => {state.creator=event.target.value; resetPage();}},
      node("option", {value:""}, "全部創作者"), ...data.creators.map(item => node("option", {value:item.creator_id}, item.name)));
    creatorSelect.value = state.creator;
    const statusSelect = node("select", {"aria-label":"依狀態篩選", onchange:event => {state.status=event.target.value; resetPage();}},
      node("option", {value:""}, "全部狀態"), ...["completed","partial","failed","restricted","unavailable","missing"].map(value => node("option", {value}, value)));
    statusSelect.value = state.status;
    const years = [...new Set(data.posts.map(post => taipeiYear(post.published_at)).filter(value => /^\d{4}$/.test(value)))].sort().reverse();
    const yearSelect = node("select", {"aria-label":"依年份篩選", onchange:event => {state.year=event.target.value; resetPage();}},
      node("option", {value:""}, "全部年份"), ...years.map(value => node("option", {value}, value)));
    yearSelect.value = state.year;
    const versionSelect = node("select", {"aria-label":"依版本數篩選", onchange:event => {state.versioned=event.target.value; resetPage();}},
      node("option", {value:""}, "全部版本"), node("option", {value:"yes"}, "多版本文章"));
    versionSelect.value = state.versioned;
    const sortSelect = node("select", {"aria-label":"排序方式", onchange:event => {state.sort=event.target.value; resetPage();}},
      node("option", {value:"published-desc"}, "發布時間（新到舊）"), node("option", {value:"updated-desc"}, "更新時間（新到舊）"),
      node("option", {value:"title-asc"}, "標題（A–Z）"), node("option", {value:"versions-desc"}, "版本數（多到少）"));
    sortSelect.value = state.sort;
    const clear = node("button", {class:"secondary", type:"button", onclick:() => {state.creator=""; state.status=""; state.year=""; state.versioned=""; state.q=""; state.sort="published-desc"; state.page=1; writeHash(); render();}}, "清除篩選");
    return node("div", {class:"controls"}, creatorSelect, statusSelect, yearSelect, versionSelect, sortSelect, clear);
  }

  function sortedPosts(items) {
    const result = [...items];
    const newest = key => (a, b) => String(b[key] || "").localeCompare(String(a[key] || ""));
    if (state.sort === "updated-desc") result.sort(newest("updated_at"));
    else if (state.sort === "title-asc") result.sort((a,b) => a.title.localeCompare(b.title));
    else if (state.sort === "versions-desc") result.sort((a,b) => b.version_count - a.version_count || newest("published_at")(a,b));
    else result.sort(newest("published_at"));
    return result;
  }

  function pagination(total, pageSize=50) {
    const pages = Math.max(1, Math.ceil(total / pageSize));
    state.page = Math.min(state.page, pages);
    if (pages === 1) return null;
    return node("nav", {class:"pagination", "aria-label":"文章分頁"},
      node("button", {class:"secondary", type:"button", disabled:state.page === 1 ? "" : null, onclick:() => {state.page--; writeHash(); renderMain();}}, "← 上一頁"),
      node("span", {}, `第 ${state.page} / ${pages} 頁`),
      node("button", {class:"secondary", type:"button", disabled:state.page === pages ? "" : null, onclick:() => {state.page++; writeHash(); renderMain();}}, "下一頁 →"));
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
    const pageSize = 50;
    const pageItems = items.slice((state.page - 1) * pageSize, state.page * pageSize);
    return node("div", {}, heading("文章", `${items.length} 筆符合目前條件`), controls(), node("div", {class:"post-list"}, ...(pageItems.length ? pageItems.map(postCard) : [node("p", {class:"empty"}, "沒有符合條件的文章。")])), pagination(items.length, pageSize));
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
  window.addEventListener("keydown", event => { if (event.key === "Escape") document.body.classList.remove("menu-open"); });
  readHash(); render();
})();
