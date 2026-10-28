(() => {
  "use strict";
  const app = document.getElementById("app");
  const search = document.getElementById("search");
  const nav = document.getElementById("nav");
  const sessionToken = document.querySelector('meta[name="fanbox-session-token"]').content;
  const state = {view: "posts", page: 1, q: "", current: null};
  let jobTimer = null;

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

  const request = async (url, options = {}) => {
    const response = await fetch(url, {...options, headers: {Accept: "application/json", ...(options.headers || {})}});
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || `HTTP ${response.status}`);
    }
    return response.json();
  };

  const date = value => value ? new Intl.DateTimeFormat("zh-TW", {
    timeZone: "Asia/Taipei", dateStyle: "medium", timeStyle: "short"
  }).format(new Date(value)) : "—";

  function errorView(error) {
    app.replaceChildren(element("section", {class: "panel error"},
      element("h1", {}, "無法讀取封存"), element("p", {}, error.message),
      element("button", {type: "button", onclick: refreshView}, "重試")));
  }

  function setView(view) {
    clearTimeout(jobTimer);
    state.view = view;
    state.current = null;
    state.page = 1;
    for (const button of nav.querySelectorAll("button")) button.classList.toggle("active", button.dataset.view === view);
    search.disabled = view === "backup";
    search.placeholder = view === "posts" ? "搜尋標題、Post ID 或創作者…" : view === "fancards" ? "搜尋創作者或月份…" : view === "backup" ? "備份執行期間可繼續閱讀封存" : "搜尋創作者…";
    refreshView();
  }

  function refreshView() {
    if (state.view === "backup") return loadBackup();
    if (state.view === "creators") return loadCreators();
    if (state.view === "fancards") return loadFancards();
    return loadPosts();
  }

  async function loadPosts() {
    state.current = null;
    app.replaceChildren(element("p", {class: "empty"}, "正在讀取文章…"));
    try {
      const params = new URLSearchParams({page: state.page, page_size: 50});
      if (state.q) params.set("q", state.q);
      const data = await request(`/api/posts?${params}`);
      const cards = data.items.map(item => element("button", {
        type: "button", class: "post-card", onclick: () => loadPost(item.post_id)
      }, element("span", {class: "post-main"},
        element("span", {class: "eyebrow"}, `${item.creator_name} · ${date(item.published_at)}`),
        element("strong", {}, item.title),
        element("small", {}, `Post ${item.post_id} · ${item.version_count} 個版本`)),
        element("span", {class: `badge status-${item.status}`}, item.status)));
      const previous = element("button", {type: "button", disabled: data.page <= 1 ? "" : null,
        onclick: () => { state.page--; loadPosts(); }}, "← 上一頁");
      const next = element("button", {type: "button", disabled: data.page >= data.pages ? "" : null,
        onclick: () => { state.page++; loadPosts(); }}, "下一頁 →");
      app.replaceChildren(element("section", {class: "page"},
        element("header", {class: "heading"}, element("div", {},
          element("p", {class: "eyebrow"}, "DYNAMIC LOCAL READER"),
          element("h1", {}, "文章"), element("p", {}, `${data.total} 篇封存，不需建立索引`))),
        element("div", {class: "post-list"}, ...(cards.length ? cards : [element("p", {class: "empty"}, "沒有符合條件的文章。")])),
        element("nav", {class: "pagination"}, previous, element("span", {}, `${data.page} / ${data.pages}`), next)));
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

  function blockView(block) {
    if (block.type === "image" && block.media_url) return element("figure", {},
      element("a", {href: block.media_url, target: "_blank"}, element("img", {src: block.media_url, loading: "lazy", alt: block.name || "文章圖片"})));
    if (block.type === "file" && block.media_url) return element("p", {class: "attachment"}, element("a", {href: block.media_url}, block.name || block.filename || "下載附件"));
    if (block.type === "separator") return element("hr");
    if (block.type === "quote") return element("blockquote", {}, richText(block));
    if (block.type === "heading") return element(`h${Math.min(Math.max(block.level || 2, 2), 6)}`, {}, richText(block));
    if (block.type === "embed" && block.url) return element("p", {class: "attachment"}, element("a", {href: block.url, target: "_blank", rel: "noreferrer"}, block.name || block.url));
    if (block.text) return element("p", {class: "body-text"}, richText(block));
    return null;
  }

  async function loadPost(postId, version = null) {
    app.replaceChildren(element("p", {class: "empty"}, "正在讀取文章…"));
    try {
      const post = await request(`/api/posts/${postId}${version ? `?version=${version}` : ""}`);
      state.current = postId;
      const versionSelect = element("select", {"aria-label": "版本", onchange: event => loadPost(postId, Number(event.target.value))},
        ...post.versions.map(item => element("option", {value: item.number}, `v${String(item.number).padStart(4, "0")} · ${date(item.captured_at)}`)));
      versionSelect.value = String(post.version);
      const body = post.blocks.map(blockView).filter(Boolean);
      app.replaceChildren(element("article", {class: "reader"},
        element("button", {type: "button", class: "back", onclick: loadPosts}, "← 回到文章列表"),
        post.cover_url ? element("a", {href: post.cover_url, target: "_blank"}, element("img", {class: "cover", src: post.cover_url, alt: "文章封面"})) : null,
        element("header", {class: "reader-heading"}, element("p", {class: "eyebrow"}, `${post.creator_name} · Post ${post.post_id}`),
          element("h1", {}, post.title), element("p", {}, `發布 ${date(post.published_at)} · 更新 ${date(post.updated_at)}`), versionSelect),
        element("section", {class: "content"}, ...(body.length ? body : [element("p", {class: "empty"}, "此版本沒有可顯示的正文。")])),
        element("footer", {}, element("a", {href: post.url, target: "_blank", rel: "noreferrer"}, "開啟 FANBOX 原文"))));
    } catch (error) { errorView(error); }
  }

  async function loadCreators() {
    state.current = null;
    app.replaceChildren(element("p", {class: "empty"}, "正在讀取創作者…"));
    try {
      const data = await request("/api/creators");
      const term = state.q.toLocaleLowerCase();
      const items = data.items.filter(item => `${item.name} ${item.creator_id}`.toLocaleLowerCase().includes(term));
      const cards = items.map(item => element("button", {type: "button", class: "creator-card", onclick: () => {
        state.q = item.creator_id; search.value = state.q; setView("posts");
      }}, item.avatar_url ? element("img", {src: item.avatar_url, alt: "", loading: "lazy"}) : element("span", {class: "avatar"}, item.name.slice(0, 1)),
      element("span", {class: "post-main"}, element("strong", {}, item.name), element("small", {}, `${item.creator_id} · ${item.post_count} 篇文章`)),
      element("span", {class: `badge status-${item.status}`}, item.status)));
      app.replaceChildren(element("section", {class: "page"},
        element("header", {class: "heading"}, element("div", {}, element("p", {class: "eyebrow"}, "CREATORS"), element("h1", {}, "創作者"), element("p", {}, `${items.length} 位符合目前條件`))),
        element("div", {class: "creator-grid"}, ...(cards.length ? cards : [element("p", {class: "empty"}, "沒有符合條件的創作者。")]))));
    } catch (error) { errorView(error); }
  }

  async function loadFancards() {
    state.current = null;
    app.replaceChildren(element("p", {class: "empty"}, "正在讀取 Fan Card…"));
    try {
      const params = new URLSearchParams();
      if (state.q) params.set("q", state.q);
      const data = await request(`/api/fancards?${params}`);
      const cards = data.items.map(item => element("button", {type: "button", class: "fancard-card", onclick: () => loadFancard(item.creator_id, item.target_month)},
        item.image_url ? element("img", {src: item.image_url, alt: `${item.creator_name} Fan Card`, loading: "lazy"}) : element("div", {class: "card-placeholder"}, "無卡面"),
        element("span", {class: "post-main"}, element("span", {class: "eyebrow"}, item.target_month), element("strong", {}, item.creator_name),
          element("small", {}, `${item.plan_title || "方案未命名"} · ¥${Number(item.fee || 0).toLocaleString()}/月 · ${item.version_count} 個版本`))));
      app.replaceChildren(element("section", {class: "page"},
        element("header", {class: "heading"}, element("div", {}, element("p", {class: "eyebrow"}, "SUPPORT HISTORY"), element("h1", {}, "Fan Card"), element("p", {}, `${data.items.length} 張卡片`))),
        element("div", {class: "fancard-grid"}, ...(cards.length ? cards : [element("p", {class: "empty"}, "沒有符合條件的 Fan Card。")]))));
    } catch (error) { errorView(error); }
  }

  async function loadFancard(creatorId, month, version = null) {
    app.replaceChildren(element("p", {class: "empty"}, "正在讀取 Fan Card…"));
    try {
      const card = await request(`/api/fancards/${encodeURIComponent(creatorId)}/${month}${version ? `?version=${version}` : ""}`);
      state.current = {type: "fancard", creatorId, month};
      const versionSelect = element("select", {"aria-label": "版本", onchange: event => loadFancard(creatorId, month, Number(event.target.value))},
        ...card.versions.map(item => element("option", {value: item.number}, `v${String(item.number).padStart(4, "0")} · ${date(item.captured_at)}`)));
      versionSelect.value = String(card.version);
      app.replaceChildren(element("article", {class: "reader fancard-reader"},
        element("button", {type: "button", class: "back", onclick: loadFancards}, "← 回到 Fan Card"),
        card.image_url ? element("a", {href: card.image_url, target: "_blank"}, element("img", {class: "card-image", src: card.image_url, alt: `${card.creator_name} Fan Card`})) : element("div", {class: "card-placeholder large"}, "本月未提供自訂卡面"),
        element("header", {class: "reader-heading"}, element("p", {class: "eyebrow"}, `${card.target_month} · ${card.creator_id}`), element("h1", {}, card.creator_name),
          element("p", {}, `${card.plan_title || "方案未命名"} · ¥${Number(card.fee || 0).toLocaleString()}/月`), versionSelect),
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
    if (event.kind === "fancard_finished") return `Fan Card ${data.creator_id}：${data.status}`;
    if (event.kind === "asset_progress") return `${data.name}：${Number(data.downloaded || 0).toLocaleString()}${data.total ? ` / ${Number(data.total).toLocaleString()}` : ""} bytes`;
    if (event.kind === "item_finished") return `Post ${data.post_id}：${data.unchanged ? "內容未變" : data.error || data.status}`;
    if (event.kind === "warning") return `警告：${data.creator_id ? `${data.creator_id}：` : ""}${data.message}`;
    if (event.kind === "job_finished") return data.dry_run ? "預覽完成" : `完成：成功 ${data.success}、未完成 ${data.failure}`;
    if (event.kind === "job_failed") return `失敗：${data.error}`;
    if (event.kind === "job_cancelled") return "工作已取消";
    return event.kind;
  }

  function renderJob(job, creators) {
    clearTimeout(jobTimer);
    const active = ["queued", "running", "cancelling"].includes(job.status);
    const events = job.events.slice(-100).map(item => element("li", {},
      element("time", {}, date(item.timestamp)), element("span", {}, eventLabel(item))));
    const controls = element("div", {class: "job-actions"},
      active ? element("button", {type: "button", class: "danger", onclick: () => cancelJob(job.job_id)}, job.status === "cancelling" ? "正在安全停止…" : "安全停止") : null,
      !active ? element("button", {type: "button", onclick: () => renderBackupForm(creators)}, "建立新工作") : null);
    app.replaceChildren(element("section", {class: "page"},
      element("header", {class: "heading"}, element("div", {}, element("p", {class: "eyebrow"}, "BACKGROUND JOB"), element("h1", {}, "備份工作"),
        element("p", {}, job.request.dry_run ? "預覽模式，不會下載資源" : "正式備份")), element("span", {class: `job-status status-${job.status}`}, job.status)),
      job.error ? element("p", {class: "job-error"}, job.error) : null,
      job.result ? element("div", {class: "job-summary"},
        element("span", {}, `選取 ${job.result.selected}`), element("span", {}, `成功 ${job.result.success}`),
        element("span", {}, `未變 ${job.result.unchanged}`), element("span", {}, `失敗 ${job.result.failure}`)) : null,
      controls,
      element("ol", {class: "event-log"}, ...(events.length ? events : [element("li", {}, "等待工作事件…")]))));
    if (active) jobTimer = setTimeout(() => pollJob(job.job_id, creators), 900);
  }

  function renderBackupForm(creators) {
    const creatorSelect = element("select", {id: "backup-creator", "aria-label": "備份範圍"},
      element("option", {value: ""}, "全部支援中的創作者"),
      ...creators.map(item => element("option", {value: item.creator_id}, `${item.name}（${item.creator_id}）`)));
    const dryRun = element("input", {id: "backup-dry-run", type: "checkbox", checked: ""});
    const maxPosts = element("input", {id: "backup-max-posts", type: "number", min: 1, max: 100, value: 20});
    app.replaceChildren(element("section", {class: "page backup-page"},
      element("header", {class: "heading"}, element("div", {}, element("p", {class: "eyebrow"}, "BACKUP CONTROL"), element("h1", {}, "開始備份"),
        element("p", {}, "先以預覽確認範圍，再取消勾選預覽模式執行正式備份。"))),
      element("form", {class: "backup-form", onsubmit: event => { event.preventDefault(); startBackup(creatorSelect.value, dryRun.checked, Number(maxPosts.value)); }},
        element("label", {}, element("span", {}, "創作者"), creatorSelect),
        element("label", {}, element("span", {}, "本次文章上限"), maxPosts),
        element("label", {class: "checkbox"}, dryRun, element("span", {}, "只預覽，不下載")),
        element("button", {type: "submit", class: "primary"}, "開始工作")),
      element("p", {class: "notice"}, "同一時間只允許一個備份工作。安全停止會在目前文章處理完成後生效。")));
  }

  async function loadBackup() {
    state.current = null;
    app.replaceChildren(element("p", {class: "empty"}, "正在讀取工作狀態…"));
    try {
      const [creatorData, jobData] = await Promise.all([request("/api/creators"), request("/api/jobs")]);
      const active = jobData.items.find(item => ["queued", "running", "cancelling"].includes(item.status));
      if (active) renderJob(active, creatorData.items);
      else renderBackupForm(creatorData.items);
    } catch (error) { errorView(error); }
  }

  async function startBackup(creator, dryRun, maxPosts) {
    try {
      const job = await request("/api/jobs/backup", {
        method: "POST",
        headers: {"Content-Type": "application/json", "X-Fanbox-Token": sessionToken},
        body: JSON.stringify({creator: creator || null, dry_run: dryRun, max_posts: maxPosts}),
      });
      const creators = (await request("/api/creators")).items;
      renderJob(job, creators);
    } catch (error) { errorView(error); }
  }

  async function pollJob(jobId, creators) {
    if (state.view !== "backup") return;
    try { renderJob(await request(`/api/jobs/${jobId}`), creators); }
    catch (error) { errorView(error); }
  }

  async function cancelJob(jobId) {
    try {
      const job = await request(`/api/jobs/${jobId}/cancel`, {
        method: "POST", headers: {"X-Fanbox-Token": sessionToken},
      });
      const creators = (await request("/api/creators")).items;
      renderJob(job, creators);
    } catch (error) { errorView(error); }
  }

  let searchTimer;
  search.addEventListener("input", event => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => { state.q = event.target.value.trim(); state.page = 1; refreshView(); }, 180);
  });
  nav.addEventListener("click", event => { if (event.target.dataset.view) setView(event.target.dataset.view); });
  window.addEventListener("keydown", event => { if (event.key === "Escape" && state.current) refreshView(); });
  setView("posts");
})();
