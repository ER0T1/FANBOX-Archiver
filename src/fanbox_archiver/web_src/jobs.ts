namespace FanboxUI {
  const activeStatuses = new Set<JobStatus>(["queued", "running", "cancelling"]);

  export interface BackupViewActions {
    onCancel(jobId: string): void;
    onRetry(jobId: string): void;
    onNew(): void;
    onHistory(): void;
    onShow(jobId: string): void;
    onFilter(value: string): void;
  }

  export interface BackupFormActions {
    onStart(
      creators: string[], dryRun: boolean, maxPosts: number,
      mode: "full" | "profile" | "fancard", includeProfile: boolean, includeFancard: boolean,
    ): void;
    onHistory(): void;
  }

  export interface BackupFormDefaults {
    dryRun: boolean;
    includeProfile: boolean;
    includeFancard: boolean;
    maxPosts: number;
  }

  export interface MaintenanceActions {
    onStart(): void;
    onShow(jobId: string): void;
  }

  export function jobLabel(job: WebJob): string {
    if (job.kind === "verify") return "封存完整性驗證";
    return ({profile: "個人資料拉取", fancard: "粉絲卡拉取"})[job.request.mode ?? ""]
      || (job.request.dry_run ? "完整備份預覽" : "完整備份");
  }

  export function activeJobNotice(job: WebJob | null): HTMLElement | null {
    if (!job) return null;
    return h("p", {class: "global-job-notice", role: "status"},
      h("strong", {}, `目前工作：${jobLabel(job)}`), `（${statusText(job.status)}）`,
      h("span", {}, "同一時間只允許一項寫入或維護操作；完成、失敗或取消後會自動解鎖。"));
  }

  function valueNumber(data: Record<string, unknown>, key: string): number {
    const value = Number(data[key] ?? 0);
    return Number.isFinite(value) ? value : 0;
  }

  function valueString(data: Record<string, unknown>, key: string): string {
    const value = data[key];
    return value === null || value === undefined ? "" : String(value);
  }

  function isRecord(value: unknown): value is Record<string, unknown> {
    return Boolean(value) && typeof value === "object" && !Array.isArray(value);
  }

  export function stopReasonLabel(reason: string): string {
    return ({limit_reached: "已達下載上限", remote_exhausted: "遠端頁面已掃描完畢",
      backfill_completed: "歷史回補已完成", unchanged_threshold: "已達連續未變停止門檻",
      eligible_exhausted: "其餘投稿不需下載"} as Record<string, string>)[reason] || "掃描完成";
  }

  export function isActiveJob(job: WebJob | null | undefined): boolean {
    return Boolean(job && activeStatuses.has(job.status));
  }

  export function requestCreators(request: WebJob["request"]): string[] {
    if (Array.isArray(request.creators)) return [...new Set(request.creators.filter(Boolean))];
    return request.creator ? [request.creator] : [];
  }

  export function filterBackupCreators(
    creators: CreatorSummary[], query: string, selected: string[],
  ): CreatorSummary[] {
    const term = query.trim().toLocaleLowerCase();
    const chosen = new Set(selected);
    return creators.filter(item => !chosen.has(item.creator_id)
      && (!term || `${item.name} ${item.creator_id}`.toLocaleLowerCase().includes(term)));
  }

  export function jobCreatorLabel(job: WebJob, creators: CreatorSummary[]): string {
    const selected = requestCreators(job.request);
    if (!selected.length) return "全部創作者";
    if (selected.length > 1) return `${selected.length} 位創作者`;
    const item = creators.find(creator => creator.creator_id === selected[0]);
    return item ? `${item.name}（@${item.creator_id}）` : `@${selected[0]}`;
  }

  export function statusText(status: JobStatus): string {
    return ({queued: "等待中", running: "執行中", cancelling: "停止中", completed: "已完成",
      failed: "失敗", cancelled: "已取消", interrupted: "已中斷"})[status];
  }

  function eventLabel(event: WebJobEvent): string {
    const data = event.data;
    if (event.kind === "job_started") return `工作開始（${valueString(data, "scope")}）`;
    if (event.kind === "plan_ready") return `計畫：上限 ${valueNumber(data, "requested_max_posts")}、發現 ${valueNumber(data, "discovered")}、符合 ${valueNumber(data, "eligible")}、選取 ${valueNumber(data, "selected")}、略過 ${valueNumber(data, "skipped")}（${stopReasonLabel(valueString(data, "stop_reason"))}）`;
    if (event.kind === "fancard_finished") return `粉絲卡 ${valueString(data, "creator_id")}：${valueString(data, "status")}`;
    if (event.kind === "profile_started") return `正在備份 @${valueString(data, "creator_id")} 的個人資料`;
    if (event.kind === "profile_finished") return `個人資料 ${valueString(data, "creator_id")}：${valueString(data, "status")}（v${String(valueNumber(data, "version")).padStart(4, "0")}）`;
    if (event.kind === "profile_warning") return `個人資料警告：${valueString(data, "creator_id")}：${valueString(data, "message")}`;
    if (event.kind === "asset_progress") {
      const total = valueNumber(data, "total");
      return `${valueString(data, "name")}：${humanBytes(valueNumber(data, "downloaded"))}${total ? ` / ${humanBytes(total)}` : ""}`;
    }
    if (event.kind === "item_finished") return `Post ${valueString(data, "post_id")}：${data.unchanged ? "內容未變" : valueString(data, "error") || valueString(data, "status")}`;
    if (event.kind === "warning") return `警告：${data.creator_id ? `${valueString(data, "creator_id")}：` : ""}${valueString(data, "message")}`;
    if (event.kind === "job_finished") return data.dry_run ? "預覽完成" : `完成：成功 ${valueNumber(data, "success")}、未完成 ${valueNumber(data, "failure")}`;
    if (event.kind === "job_failed") return `錯誤：${valueString(data, "error")}`;
    if (event.kind === "job_cancelled") return "工作已取消";
    if (event.kind === "job_interrupted") return "伺服器曾重新啟動，工作已中斷且未自動重跑";
    return event.kind;
  }

  function eventTone(kind: string): string {
    if (["warning", "profile_warning", "job_interrupted"].includes(kind)) return "warning";
    if (kind === "job_failed") return "error";
    if (kind === "plan_ready") return "plan";
    if (kind === "job_finished") return "success";
    return "neutral";
  }

  function planSummary(event: WebJobEvent | undefined, creators: CreatorSummary[]): HTMLElement | null {
    if (!event) return null;
    const data = event.data;
    const creatorNames = new Map(creators.map(item => [item.creator_id, item.name]));
    const metrics: Array<[string, number, string]> = [["新增", valueNumber(data, "new"), "new"],
      ["更新", valueNumber(data, "updated"), "updated"], ["重試", valueNumber(data, "retried"), "retry"],
      ["略過", valueNumber(data, "skipped"), "skipped"]];
    const scans = Array.isArray(data.scans) ? data.scans.filter(isRecord) : [];
    const rows = scans.map(scan => {
      const creatorId = valueString(scan, "creator_id");
      const profile = valueString(scan, "profile");
      return h("tr", {}, h("th", {scope: "row"}, h("strong", {}, creatorNames.get(creatorId) || creatorId), h("small", {}, creatorId)),
        h("td", {class: "number new"}, valueNumber(scan, "new")), h("td", {class: "number updated"}, valueNumber(scan, "updated")),
        h("td", {class: "number retry"}, valueNumber(scan, "retry")), h("td", {class: "number skipped"}, valueNumber(scan, "skipped")),
        h("td", {class: "number"}, valueNumber(scan, "discovered")),
        h("td", {class: `profile-result ${profile || "none"}`}, profile || "—"));
    });
    const creatorCount = Array.isArray(data.creators) ? data.creators.length : valueNumber(data, "creators") || rows.length;
    const requested = valueNumber(data, "requested_max_posts");
    const selected = valueNumber(data, "selected");
    const reason = stopReasonLabel(valueString(data, "stop_reason"));
    return h("section", {class: "plan-panel"},
      h("div", {class: "section-title"}, h("div", {}, h("p", {class: "eyebrow"}, "BACKUP PLAN"), h("h2", {}, "本次備份摘要")),
        h("span", {class: "plan-creators"}, `${creatorCount} 位創作者`)),
      h("p", {class: "plan-capacity"}, `上限 ${requested}／發現 ${valueNumber(data, "discovered")}／符合 ${valueNumber(data, "eligible")}／選取 ${selected}／略過 ${valueNumber(data, "skipped")}`,
        selected < requested ? h("strong", {}, reason) : null),
      h("div", {class: "metric-grid"}, metrics.map(([label, value, tone]) => h("div", {class: `metric ${tone}`}, h("strong", {}, value), h("span", {}, label)))),
      rows.length ? h("div", {class: "table-scroll"}, h("table", {class: "plan-table"},
        h("thead", {}, h("tr", {}, h("th", {}, "創作者"), h("th", {}, "新增"), h("th", {}, "更新"), h("th", {}, "重試"), h("th", {}, "略過"), h("th", {}, "發現"), h("th", {}, "Profile"))),
        h("tbody", {}, rows))) : null);
  }

  function currentActivity(job: WebJob): HTMLElement {
    const event = [...(job.events ?? [])].reverse().find(item => ["asset_progress", "item_finished", "fancard_finished",
      "profile_started", "profile_finished", "profile_warning", "warning", "job_failed", "job_finished",
      "job_cancelled", "job_interrupted", "job_started"].includes(item.kind));
    if (!event) return h("section", {class: "current-activity"}, h("p", {class: "eyebrow"}, "CURRENT"), h("h2", {}, "正在準備備份…"));
    const isAsset = event.kind === "asset_progress";
    const total = valueNumber(event.data, "total");
    const downloaded = valueNumber(event.data, "downloaded");
    const percent = total > 0 ? Math.min(100, Math.max(0, downloaded / total * 100)) : null;
    return h("section", {class: `current-activity tone-${eventTone(event.kind)}`},
      h("div", {class: "activity-top"}, h("div", {}, h("p", {class: "eyebrow"}, isAsset ? "CURRENT DOWNLOAD" : "CURRENT STATUS"),
        h("h2", {}, isAsset ? valueString(event.data, "name") || "下載資源" : eventLabel(event))), h("time", {}, formatDate(event.timestamp))),
      isAsset ? h("div", {class: "progress-area"},
        h("div", {class: "progress-label"}, h("span", {}, `${humanBytes(downloaded)}${total ? ` / ${humanBytes(total)}` : ""}`),
          h("strong", {}, percent === null ? "下載中" : `${percent.toFixed(1)}%`)),
        h("progress", {max: total || 1, value: downloaded, "aria-label": "目前資源下載進度"})) : null);
  }

  function eventLog(events: WebJobEvent[]): HTMLDetailsElement {
    const rows = events.map(item => h("li", {class: `event-${eventTone(item.kind)}`},
      h("span", {class: "event-mark", "aria-hidden": "true"}), h("time", {}, formatDate(item.timestamp)),
      h("span", {class: "event-kind"}, item.kind === "plan_ready" ? "計畫"
        : ["warning", "profile_warning", "job_interrupted"].includes(item.kind) ? "警告" : item.kind === "job_failed" ? "錯誤" : "紀錄"),
      h("span", {class: "event-message"}, eventLabel(item))));
    const details = h("details", {class: "job-details"},
      h("summary", {}, h("span", {}, "詳細執行紀錄"), h("small", {}, `${events.length} 筆`)),
      h("ol", {class: "event-log"}, rows.length ? rows : h("li", {class: "event-neutral"}, "等待工作事件…"))) as HTMLDetailsElement;
    details.addEventListener("toggle", () => {
      if (!details.open) return;
      const log = details.querySelector<HTMLElement>(".event-log");
      if (log) log.scrollTop = log.scrollHeight;
    });
    return details;
  }

  function jobPart<T extends HTMLElement>(node: T, name: string): T {
    node.dataset.jobPart = name;
    return node;
  }

  export function updateJobPage(current: HTMLElement, next: HTMLElement, preserveHistory = false): void {
    const currentParts = new Map([...current.children].map(node => [(node as HTMLElement).dataset.jobPart, node as HTMLElement]));
    for (const item of [...next.children]) {
      const nextPart = item as HTMLElement;
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
        const details = currentPart as HTMLDetailsElement;
        const wasOpen = details.open;
        const log = details.querySelector<HTMLElement>(".event-log");
        const previousScrollTop = log?.scrollTop ?? 0;
        const nearBottom = log ? log.scrollHeight - log.scrollTop - log.clientHeight < 40 : true;
        currentPart.replaceChildren(...nextPart.childNodes);
        details.open = wasOpen;
        const updatedLog = details.querySelector<HTMLElement>(".event-log");
        if (wasOpen && updatedLog) updatedLog.scrollTop = nearBottom ? updatedLog.scrollHeight : previousScrollTop;
      } else currentPart.replaceWith(nextPart);
      currentParts.delete(name);
    }
    for (const stale of currentParts.values()) stale.remove();
  }

  function jobModeLabel(job: WebJob): string {
    return ({profile: "只拉取 Profile", fancard: "只拉取 Fan Card"})[job.request.mode ?? ""]
      || (job.request.dry_run ? "完整備份預覽" : "完整備份");
  }

  function jobHistory(
    jobs: WebJob[], selectedId: string | null, creators: CreatorSummary[], filterValue: string,
    actions: Pick<BackupViewActions, "onShow" | "onFilter">,
  ): HTMLElement {
    const active = jobs.find(isActiveJob);
    const filter = customSelect({id: "job-history-filter", label: "篩選工作狀態", value: filterValue, options: [
      {value: "all", label: "全部狀態"}, {value: "completed", label: "已完成"}, {value: "failed", label: "失敗"},
      {value: "interrupted", label: "已中斷"}, {value: "cancelled", label: "已取消"},
    ], onChange: actions.onFilter});
    const filtered = jobs.filter(item => filterValue === "all" || item.status === filterValue);
    const rows = filtered.map(item => h("button", {type: "button", class: `history-row${item.job_id === selectedId ? " selected" : ""}`,
      disabled: Boolean(active && item.job_id !== active.job_id), onclick: () => actions.onShow(item.job_id)},
    h("span", {class: `history-status status-${item.status}`}, statusText(item.status)),
    h("span", {class: "history-main"}, h("strong", {}, jobModeLabel(item)),
      h("small", {}, `${jobCreatorLabel(item, creators)} · ${formatDate(item.created_at)}`)),
    h("span", {class: "history-result"}, item.result
      ? `成功 ${item.result.success ?? 0} · 失敗 ${item.result.failure ?? 0}` : item.error ? "查看錯誤" : "查看詳情")));
    return h("section", {class: "job-history"}, h("div", {class: "history-heading"},
      h("div", {}, h("p", {class: "eyebrow"}, "JOB HISTORY"), h("h2", {}, "備份紀錄")), filter),
      active ? h("p", {class: "history-notice"}, "工作執行期間會鎖定其他歷史項目，避免離開目前進度畫面。") : null,
      h("div", {class: "history-list"}, rows.length ? rows : h("p", {class: "empty compact"}, "沒有符合條件的工作紀錄。")));
  }

  export function renderBackupJobPage(
    job: WebJob, creators: CreatorSummary[], jobs: WebJob[], filterValue: string,
    activeJob: WebJob | null, actions: BackupViewActions,
  ): HTMLElement {
    const active = isActiveJob(job);
    const blocked = Boolean(activeJob && activeJob.job_id !== job.job_id);
    const plan = (job.events ?? []).find(item => item.kind === "plan_ready");
    const retryable = ["failed", "cancelled", "interrupted"].includes(job.status);
    const selectedCreators = requestCreators(job.request);
    const creatorNames = new Map(creators.map(item => [item.creator_id, item.name]));
    const controls = h("div", {class: "job-actions"},
      active ? h("button", {type: "button", class: "danger", onclick: () => actions.onCancel(job.job_id)},
        job.status === "cancelling" ? "正在安全停止…" : "安全停止") : null,
      retryable ? h("button", {type: "button", class: "retry", disabled: blocked,
        onclick: () => actions.onRetry(job.job_id)}, "使用相同設定重試") : null,
      !active ? h("button", {type: "button", disabled: blocked, onclick: actions.onNew}, "建立新工作") : null,
      h("button", {type: "button", class: "secondary", disabled: active, onclick: actions.onHistory}, "工作歷史"));
    return h("section", {class: "page backup-page", "data-job-id": job.job_id},
      jobPart(h("header", {class: "heading job-heading"}, h("div", {}, h("p", {class: "eyebrow"}, "BACKUP JOB"),
        h("h1", {}, "備份工作"), h("p", {}, jobModeLabel(job))),
      h("span", {class: `job-status status-${job.status}`}, statusText(job.status))), "header"),
      jobPart(activeJobNotice(blocked ? activeJob : null) || h("div", {hidden: true}), "global-active"),
      jobPart(h("section", {class: "job-scope"}, h("p", {class: "eyebrow"}, "BACKUP SCOPE"),
        h("h2", {}, jobCreatorLabel(job, creators)), selectedCreators.length
          ? h("ul", {}, selectedCreators.map(id => h("li", {}, h("strong", {}, creatorNames.get(id) || id), h("span", {}, `@${id}`))))
          : h("p", {}, "本次工作涵蓋全部支援中的創作者。")), "scope"),
      jobPart(planSummary(plan, creators) || h("div", {hidden: true}), "plan"),
      jobPart(currentActivity(job), "activity"),
      jobPart(h("p", {class: "job-error", hidden: !job.error}, h("strong", {}, "錯誤："), job.error || ""), "error"),
      jobPart(h("div", {class: "result-strip", hidden: !job.result}, job.result ? [
        h("span", {}, "選取 ", h("strong", {}, job.result.selected ?? 0)), h("span", {}, "成功 ", h("strong", {}, job.result.success ?? 0)),
        h("span", {}, "未變 ", h("strong", {}, job.result.unchanged ?? 0)), h("span", {}, "失敗 ", h("strong", {}, job.result.failure ?? 0)),
      ] : null), "result"), jobPart(controls, "actions"), jobPart(eventLog(job.events ?? []), "details"));
  }

  export function renderBackupFormPage(
    creators: CreatorSummary[], defaults: BackupFormDefaults,
    activeJob: WebJob | null, actions: BackupFormActions,
  ): HTMLElement {
    const blocked = Boolean(activeJob);
    const selected: string[] = [];
    const dryRun = h("input", {id: "backup-dry-run", type: "checkbox", checked: defaults.dryRun}) as HTMLInputElement;
    const includeProfile = h("input", {id: "backup-include-profile", type: "checkbox", checked: defaults.includeProfile}) as HTMLInputElement;
    const includeFancard = h("input", {id: "backup-include-fancard", type: "checkbox", checked: defaults.includeFancard}) as HTMLInputElement;
    const maxPosts = h("input", {id: "backup-max-posts", type: "number", min: 1, max: 100, value: defaults.maxPosts}) as HTMLInputElement;
    const selectedList = h("div", {class: "selected-creator-list"});
    const count = h("strong", {}, "已選 0 位");
    const input = h("input", {type: "search", placeholder: "搜尋名稱或 Creator ID…", autocomplete: "off",
      role: "combobox", "aria-label": "搜尋並加入創作者", "aria-expanded": "false"}) as HTMLInputElement;
    const menu = h("div", {class: "creator-combobox-menu", role: "listbox", hidden: true});
    const combobox = h("div", {class: "creator-combobox form-field"}, h("span", {}, "加入創作者"), input, menu);
    let activeIndex = 0;
    let listeningOutside = false;
    const closeMenu = (): void => {
      menu.hidden = true;
      input.setAttribute("aria-expanded", "false");
      if (listeningOutside) {
        document.removeEventListener("pointerdown", handleOutsidePointer);
        listeningOutside = false;
      }
    };
    const handleOutsidePointer = (event: PointerEvent): void => {
      if (!combobox.isConnected || !combobox.contains(event.target as Node)) closeMenu();
    };
    const openMenu = (): void => {
      renderCandidates();
      menu.hidden = false;
      input.setAttribute("aria-expanded", "true");
      if (!listeningOutside) {
        document.addEventListener("pointerdown", handleOutsidePointer);
        listeningOutside = true;
      }
    };
    const renderSelected = (): void => {
      count.textContent = `已選 ${selected.length} 位`;
      selectedList.replaceChildren(...(selected.length ? selected.map(id => {
        const creator = creators.find(item => item.creator_id === id);
        return h("div", {class: "selected-creator"}, h("button", {type: "button", class: "remove-creator",
          "aria-label": `移除 ${creator?.name || id} @${id}`, onclick: () => {
            selected.splice(selected.indexOf(id), 1); renderSelected(); renderCandidates();
          }}, "×"), h("span", {}, h("strong", {}, creator?.name || id), h("small", {}, `@${id}`)));
      }) : [h("p", {class: "empty compact"}, "尚未指定創作者；將備份全部支援中的創作者")]))
    };
    const choose = (id: string): void => {
      if (!selected.includes(id)) selected.push(id);
      input.value = ""; activeIndex = 0; renderSelected(); renderCandidates();
      input.focus(); closeMenu();
    };
    const renderCandidates = (): void => {
      const matches = filterBackupCreators(creators, input.value, selected);
      activeIndex = Math.min(activeIndex, Math.max(0, matches.length - 1));
      menu.replaceChildren(...(matches.length ? matches.map((item, index) => h("button", {type: "button", role: "option",
        class: index === activeIndex ? "active" : "", "aria-selected": index === activeIndex ? "true" : "false",
        onclick: () => choose(item.creator_id)}, h("strong", {}, item.name), h("small", {}, `@${item.creator_id}`)))
        : [h("p", {class: "empty compact"}, "沒有符合的創作者。")]))
    };
    input.addEventListener("focus", openMenu);
    input.addEventListener("click", () => { if (menu.hidden) openMenu(); });
    input.addEventListener("input", () => { activeIndex = 0; openMenu(); });
    input.addEventListener("keydown", event => {
      const matches = filterBackupCreators(creators, input.value, selected);
      if (event.key === "Escape") { closeMenu(); return; }
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault(); activeIndex = Math.max(0, Math.min(matches.length - 1,
          activeIndex + (event.key === "ArrowDown" ? 1 : -1))); renderCandidates(); return;
      }
      const candidate = matches[activeIndex];
      if (event.key === "Enter" && !menu.hidden && candidate) {
        event.preventDefault(); choose(candidate.creator_id);
      }
    });
    renderSelected();
    const start = (mode: "full" | "profile" | "fancard", preview: boolean): void =>
      actions.onStart([...selected], preview, Number(maxPosts.value), mode, includeProfile.checked, includeFancard.checked);
    return h("section", {class: "page backup-page"}, h("header", {class: "heading"}, h("div", {},
      h("p", {class: "eyebrow"}, "BACKUP CONTROL"), h("h1", {}, "開始備份"), h("p", {}, "選擇本次範圍與內容；未指定創作者時會備份全部支援中的創作者。")),
      h("button", {type: "button", class: "primary", onclick: actions.onHistory}, "工作歷史")),
    activeJobNotice(activeJob),
    h("form", {class: "backup-form", onsubmit: (event: Event) => { event.preventDefault(); if (!blocked) start("full", dryRun.checked); }},
      combobox,
      h("section", {class: "selected-creators", "aria-live": "polite"}, h("div", {class: "selected-creators-heading"},
        h("span", {}, "本次備份清單"), count), selectedList),
      h("label", {}, h("span", {}, "本次投稿上限"), maxPosts),
      h("label", {class: "checkbox"}, dryRun, h("span", {}, "完整備份只預覽，不下載")),
      h("label", {class: "checkbox"}, includeProfile, h("span", {}, "拉取個人資料")),
      h("label", {class: "checkbox"}, includeFancard, h("span", {}, "拉取粉絲卡")),
      h("button", {type: "submit", class: "primary", disabled: blocked}, "開始完整備份"),
      h("div", {class: "metadata-actions"}, h("div", {}, h("strong", {}, "單項拉取"), h("small", {}, "立即寫入封存，不掃描或下載投稿。")),
        h("div", {class: "metadata-buttons"}, h("button", {type: "button", disabled: blocked,
          onclick: () => start("profile", false)}, "拉取個人資料"),
          h("button", {type: "button", disabled: blocked, onclick: () => start("fancard", false)}, "拉取粉絲卡")))),
    h("p", {class: "notice"}, "同一時間只允許一個備份工作；安全停止會在目前投稿處理完成後生效。"));
  }

  export function renderBackupHistoryPage(
    jobs: WebJob[], creators: CreatorSummary[], filterValue: string,
    actions: Pick<BackupViewActions, "onShow" | "onFilter" | "onNew">,
  ): HTMLElement {
    return h("section", {class: "page backup-page"}, h("header", {class: "heading"}, h("div", {},
      h("p", {class: "eyebrow"}, "JOB HISTORY"), h("h1", {}, "工作歷史"),
      h("p", {}, "選擇一筆工作查看進度、結果與完整執行紀錄。")),
      h("button", {type: "button", class: "primary", onclick: actions.onNew}, "建立新工作")),
    jobHistory(jobs, null, creators, filterValue, actions));
  }

  function verificationHistory(jobs: WebJob[], selectedId: string | null, onShow: (jobId: string) => void): HTMLElement {
    const active = jobs.find(isActiveJob);
    const rows = jobs.map(item => h("button", {type: "button", class: `history-row${item.job_id === selectedId ? " selected" : ""}`,
      disabled: Boolean(active && item.job_id !== active.job_id), onclick: () => onShow(item.job_id)},
    h("span", {class: `history-status status-${item.status}`}, statusText(item.status)),
    h("span", {class: "history-main"}, h("strong", {}, "封存完整性驗證"), h("small", {}, formatDate(item.created_at))),
    h("span", {class: "history-result"}, item.result
      ? item.result.passed ? "驗證通過" : `${item.result.issue_count ?? 0} 個問題` : item.error ? "查看錯誤" : "查看進度")));
    return h("section", {class: "job-history"}, h("div", {class: "history-heading"},
      h("div", {}, h("p", {class: "eyebrow"}, "VERIFY HISTORY"), h("h2", {}, "驗證歷史"))),
      active ? h("p", {class: "history-notice"}, "驗證執行期間會鎖定其他歷史項目。") : null,
      h("div", {class: "history-list"}, rows.length ? rows : h("p", {class: "empty compact"}, "尚無驗證紀錄。")));
  }

  export function renderMaintenancePage(
    job: WebJob | null, jobs: WebJob[], activeJob: WebJob | null, actions: MaintenanceActions,
  ): HTMLElement {
    const active = Boolean(activeJob);
    const result = job?.result;
    const issues = result?.issues ?? [];
    const issueRows = issues.map(item => h("li", {}, h("strong", {}, item.reason), h("code", {}, item.path),
      item.post_id ? h("small", {}, `Post ${item.post_id}`) : null));
    return h("section", {class: "page maintenance-page"}, h("header", {class: "heading"}, h("div", {},
      h("p", {class: "eyebrow"}, "ARCHIVE MAINTENANCE"), h("h1", {}, "封存驗證"),
      h("p", {}, "檢查投稿、Profile、粉絲卡、歷史版本與資源的檔案大小及 SHA-256。")),
      job ? h("span", {class: `job-status status-${job.status}`}, statusText(job.status)) : null),
    activeJobNotice(activeJob),
    h("section", {class: "maintenance-action"}, h("div", {}, h("h2", {},
      activeJob?.kind === "verify" ? "正在驗證封存…" : activeJob ? "其他工作執行中" : "完整性檢查"),
      h("p", {}, "驗證可能需要一段時間；執行期間不能同時開始備份或修改設定。")),
      h("button", {type: "button", class: "primary", disabled: active, onclick: actions.onStart},
        activeJob?.kind === "verify" ? "驗證中…" : activeJob ? "目前無法驗證" : "開始驗證")),
    job?.error ? h("p", {class: "job-error"}, h("strong", {}, "錯誤："), job.error) : null,
    result ? h("section", {class: `verification-result ${result.passed ? "passed" : "issues"}`},
      h("div", {class: "verification-summary"}, h("strong", {}, result.passed ? "驗證通過" : `${result.issue_count ?? 0} 個問題`),
        h("span", {}, result.passed ? "目前封存未發現完整性問題。" : "請檢查下列缺失或損毀項目。")),
      issueRows.length ? h("ul", {class: "verification-issues"}, issueRows) : null,
      result.truncated ? h("p", {class: "notice"}, "問題數量過多，目前只顯示前 500 項。") : null) : null,
    verificationHistory(jobs, job?.job_id ?? null, actions.onShow));
  }
}
