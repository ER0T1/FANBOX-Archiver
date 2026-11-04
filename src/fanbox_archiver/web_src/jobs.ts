namespace FanboxUI {
  const activeStatuses = new Set<JobStatus>(["queued", "running", "cancelling"]);

  export interface BackupViewActions {
    onCancel(jobId: string): void;
    onRetry(jobId: string): void;
    onNew(): void;
    onHistory(): void;
  }

  export interface HistoryActions {
    onShow(jobId: string): void;
    onOrder(order: SortOrder): void;
    onPage(page: number): void;
  }

  export interface BackupHistoryActions extends HistoryActions {
    onNew(): void;
    onFilter(value: string): void;
  }

  export interface BackupFormActions {
    onStart(
      creators: string[], dryRun: boolean, maxPosts: number,
      mode: "full" | "profile" | "fancard", includeProfile: boolean, includeFancard: boolean,
    ): void;
    onHistory(): void;
    onSignIn(): void;
  }

  export interface BackupFormDefaults {
    dryRun: boolean;
    includeProfile: boolean;
    includeFancard: boolean;
    maxPosts: number;
  }

  export interface MaintenanceActions extends HistoryActions {
    onStart(): void;
  }

  export function jobLabel(job: WebJob): string {
    if (job.kind === "verify") return t("jobs.kind_verify");
    if (job.request.trigger === "schedule") return t("jobs.kind_schedule");
    return ({profile: t("jobs.kind_profile"), fancard: t("jobs.kind_fancard")} as Record<string, string>)[job.request.mode ?? ""]
      || (job.request.dry_run ? t("jobs.kind_preview") : t("jobs.kind_full"));
  }

  export function activeJobNotice(job: WebJob | null): HTMLElement | null {
    if (!job) return null;
    return h("p", {class: "global-job-notice", role: "status"},
      h("strong", {}, t("jobs.current_job", {label: jobLabel(job)})),
      t("jobs.current_state", {state: job.external ? t("jobs.running_in_background") : statusText(job.status)}),
      h("span", {}, job.external ? t("jobs.background_notice") : t("jobs.single_job_notice")));
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
    const known = ["limit_reached", "remote_exhausted", "backfill_completed", "unchanged_threshold", "eligible_exhausted"];
    return known.includes(reason) ? t(`jobs.stop_${reason}`) : t("jobs.stop_default");
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
    if (!selected.length) return t("jobs.all_creators");
    if (selected.length > 1) return t("jobs.creator_count", {count: selected.length});
    const item = creators.find(creator => creator.creator_id === selected[0]);
    return item ? t("jobs.creator_named", {name: item.name, creator_id: item.creator_id}) : `@${selected[0]}`;
  }

  export function statusText(status: JobStatus): string {
    return t(`jobs.status_${status}`);
  }

  function eventLabel(event: WebJobEvent): string {
    const data = event.data;
    if (event.kind === "job_started") return t("jobs.event_started", {scope: valueString(data, "scope")});
    if (event.kind === "plan_ready") return t("jobs.event_plan", {
      requested: valueNumber(data, "requested_max_posts"), discovered: valueNumber(data, "discovered"),
      eligible: valueNumber(data, "eligible"), selected: valueNumber(data, "selected"),
      skipped: valueNumber(data, "skipped"), reason: stopReasonLabel(valueString(data, "stop_reason"))});
    if (event.kind === "fancard_finished") return t("jobs.event_fancard", {
      creator_id: valueString(data, "creator_id"), status: valueString(data, "status")});
    if (event.kind === "profile_started") return t("jobs.event_profile_started", {creator_id: valueString(data, "creator_id")});
    if (event.kind === "profile_finished") return t("jobs.event_profile_finished", {
      creator_id: valueString(data, "creator_id"), status: valueString(data, "status"),
      version: String(valueNumber(data, "version")).padStart(4, "0")});
    if (event.kind === "profile_warning") return t("jobs.event_profile_warning", {
      creator_id: valueString(data, "creator_id"), message: valueString(data, "message")});
    if (event.kind === "asset_progress") {
      const total = valueNumber(data, "total");
      return t("jobs.event_asset", {name: valueString(data, "name"),
        progress: `${humanBytes(valueNumber(data, "downloaded"))}${total ? ` / ${humanBytes(total)}` : ""}`});
    }
    if (event.kind === "item_started") return t("jobs.event_item_started", {
      index: valueNumber(data, "index"), total: valueNumber(data, "total"), post_id: valueString(data, "post_id")});
    if (event.kind === "item_finished") return t("jobs.event_item_finished", {post_id: valueString(data, "post_id"),
      result: data.unchanged ? t("jobs.event_unchanged") : valueString(data, "error") || valueString(data, "status")});
    if (event.kind === "verify_progress") return t("jobs.event_verify", {
      phase: verificationPhaseLabel(valueString(data, "phase")), item: valueString(data, "item")});
    if (event.kind === "warning") return data.creator_id
      ? t("jobs.event_warning_creator", {creator_id: valueString(data, "creator_id"), message: valueString(data, "message")})
      : t("jobs.event_warning", {message: valueString(data, "message")});
    if (event.kind === "job_finished") return data.dry_run ? t("jobs.event_preview_done")
      : t("jobs.event_done", {success: valueNumber(data, "success"), failure: valueNumber(data, "failure")});
    if (event.kind === "job_failed") return t("jobs.event_failed", {error: valueString(data, "error")});
    if (event.kind === "job_cancelled") return t("jobs.event_cancelled");
    if (event.kind === "job_interrupted") return t("jobs.event_interrupted");
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
    const metrics: Array<[string, number, string]> = [[t("jobs.metric_new"), valueNumber(data, "new"), "new"],
      [t("jobs.metric_updated"), valueNumber(data, "updated"), "updated"], [t("jobs.metric_retry"), valueNumber(data, "retried"), "retry"],
      [t("jobs.metric_skipped"), valueNumber(data, "skipped"), "skipped"]];
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
      h("div", {class: "section-title"}, h("div", {}, h("p", {class: "eyebrow"}, "BACKUP PLAN"), h("h2", {}, t("jobs.plan_title"))),
        h("span", {class: "plan-creators"}, t("jobs.creator_count", {count: creatorCount}))),
      h("p", {class: "plan-capacity"}, t("jobs.plan_capacity", {requested, discovered: valueNumber(data, "discovered"),
        eligible: valueNumber(data, "eligible"), selected, skipped: valueNumber(data, "skipped")}),
        selected < requested ? h("strong", {}, reason) : null),
      h("div", {class: "metric-grid"}, metrics.map(([label, value, tone]) => h("div", {class: `metric ${tone}`}, h("strong", {}, value), h("span", {}, label)))),
      rows.length ? h("div", {class: "table-scroll"}, h("table", {class: "plan-table"},
        h("thead", {}, h("tr", {}, h("th", {}, t("jobs.column_creator")), h("th", {}, t("jobs.metric_new")), h("th", {}, t("jobs.metric_updated")),
          h("th", {}, t("jobs.metric_retry")), h("th", {}, t("jobs.metric_skipped")), h("th", {}, t("jobs.metric_discovered")), h("th", {}, "Profile"))),
        h("tbody", {}, rows))) : null);
  }

  function currentActivity(job: WebJob): HTMLElement {
    const events = job.events ?? [];
    const event = [...events].reverse().find(item => ["asset_progress", "item_started", "item_finished", "fancard_finished",
      "profile_started", "profile_finished", "profile_warning", "warning", "job_failed", "job_finished",
      "job_cancelled", "job_interrupted", "job_started"].includes(item.kind));
    if (!event) return h("section", {class: "current-activity"}, h("p", {class: "eyebrow"}, "CURRENT"), h("h2", {}, t("jobs.preparing")));
    const postEvent = [...events].reverse().find(item =>
      ["item_started", "item_finished", "asset_progress"].includes(item.kind)
      && valueNumber(item.data, "index") > 0 && valueNumber(item.data, "total") > 0);
    const isAsset = event.kind === "asset_progress";
    const total = valueNumber(event.data, "total");
    const downloaded = valueNumber(event.data, "downloaded");
    const percent = total > 0 ? Math.min(100, Math.max(0, downloaded / total * 100)) : null;
    return h("section", {class: `current-activity tone-${eventTone(event.kind)}`},
      h("div", {class: "activity-top"}, h("div", {}, h("p", {class: "eyebrow"}, isAsset ? "CURRENT DOWNLOAD" : "CURRENT STATUS"),
        h("h2", {}, isAsset ? valueString(event.data, "name") || t("jobs.download_asset") : eventLabel(event))), h("time", {}, formatDate(event.timestamp))),
      postEvent ? h("div", {class: "progress-area post-progress", role: "status", "aria-live": "polite", "aria-atomic": "true"},
        h("div", {class: "progress-label"},
          h("span", {}, t("jobs.post_progress", {index: valueNumber(postEvent.data, "index"), total: valueNumber(postEvent.data, "total")})),
          h("strong", {}, `Post ${valueString(postEvent.data, "post_id")}`)),
        h("progress", {max: valueNumber(postEvent.data, "total"),
          value: Math.min(valueNumber(postEvent.data, "index"), valueNumber(postEvent.data, "total")),
          "aria-label": t("jobs.post_progress_label")})) : null,
      isAsset ? h("div", {class: "progress-area"},
        h("div", {class: "progress-label"}, h("span", {}, `${humanBytes(downloaded)}${total ? ` / ${humanBytes(total)}` : ""}`),
          h("strong", {}, percent === null ? t("jobs.downloading") : `${percent.toFixed(1)}%`)),
        h("progress", {max: total || 1, value: downloaded, "aria-label": t("jobs.asset_progress_label")})) : null);
  }

  export function verificationPhaseLabel(phase: string): string {
    const known = ["scan", "posts", "versions", "fancards", "profiles", "consistency", "history"];
    return known.includes(phase) ? t(`jobs.phase_${phase}`) : t("jobs.phase_default");
  }

  function verificationProgress(job: WebJob | null): HTMLElement | null {
    const event = [...(job?.events ?? [])].reverse().find(item => item.kind === "verify_progress");
    if (!event || job?.result) return null;
    const totalValue = event.data.total;
    const total = totalValue === null || totalValue === undefined ? null : valueNumber(event.data, "total");
    const current = valueNumber(event.data, "current");
    const percent = total === null ? null : Math.min(100, Math.max(0, valueNumber(event.data, "percent")));
    return h("section", {class: "verification-progress", role: "status", "aria-live": "polite", "aria-atomic": "true"},
      h("div", {class: "verification-progress-heading"}, h("div", {},
        h("p", {class: "eyebrow"}, "VERIFY PROGRESS"),
        h("h2", {}, verificationPhaseLabel(valueString(event.data, "phase")))),
        h("strong", {}, percent === null ? t("jobs.scanning") : `${percent.toFixed(1)}%`)),
      h("p", {class: "verification-item"}, valueString(event.data, "item")),
      h("div", {class: "progress-label"},
        h("span", {}, total === null ? t("jobs.building_checklist") : `${current} / ${total}`),
        h("span", {}, t("jobs.issues_found", {count: valueNumber(event.data, "issue_count")}))),
      h("progress", {max: total ?? undefined, value: total === null ? undefined : current,
        "aria-label": total === null ? t("jobs.verify_scan_label") : t("jobs.verify_progress_label")}));
  }

  function eventLog(events: WebJobEvent[]): HTMLDetailsElement {
    const rows = events.map(item => h("li", {class: `event-${eventTone(item.kind)}`},
      h("span", {class: "event-mark", "aria-hidden": "true"}), h("time", {}, formatDate(item.timestamp)),
      h("span", {class: "event-kind"}, item.kind === "plan_ready" ? t("jobs.log_plan")
        : ["warning", "profile_warning", "job_interrupted"].includes(item.kind) ? t("jobs.log_warning")
        : item.kind === "job_failed" ? t("jobs.log_error") : t("jobs.log_record")),
      h("span", {class: "event-message"}, eventLabel(item))));
    const details = h("details", {class: "job-details"},
      h("summary", {}, h("span", {}, t("jobs.log_title")), h("small", {}, t("jobs.log_count", {count: events.length}))),
      h("ol", {class: "event-log"}, rows.length ? rows : h("li", {class: "event-neutral"}, t("jobs.log_waiting")))) as HTMLDetailsElement;
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
    if (job.request.trigger === "schedule") return t("jobs.kind_schedule");
    return ({profile: t("jobs.mode_profile"), fancard: t("jobs.mode_fancard")} as Record<string, string>)[job.request.mode ?? ""]
      || (job.request.dry_run ? t("jobs.kind_preview") : t("jobs.kind_full"));
  }

  function jobHistory(
    data: JobPage, selectedId: string | null, creators: CreatorSummary[], filterValue: string,
    order: SortOrder, actions: BackupHistoryActions,
  ): HTMLElement {
    const active = data.active;
    const filter = customSelect({id: "job-history-filter", label: t("jobs.filter_label"), value: filterValue, options: [
      {value: "all", label: t("jobs.filter_all")},
      ...(["completed", "failed", "interrupted", "cancelled"] as JobStatus[]).map(value => ({value, label: statusText(value)})),
    ], onChange: actions.onFilter});
    const rows = data.items.map(item => h("button", {type: "button", class: `history-row${item.job_id === selectedId ? " selected" : ""}`,
      disabled: Boolean(active && item.job_id !== active.job_id), onclick: () => actions.onShow(item.job_id)},
    h("span", {class: `history-status status-${item.status}`}, statusText(item.status)),
    h("span", {class: "history-main"}, h("strong", {}, jobModeLabel(item)),
      h("small", {}, `${jobCreatorLabel(item, creators)} · ${formatDate(item.created_at)}`)),
    h("span", {class: "history-result"}, item.result
      ? t("jobs.history_result", {success: item.result.success ?? 0, failure: item.result.failure ?? 0})
      : item.error ? t("jobs.view_error") : t("jobs.view_details"))));
    return h("section", {class: "job-history"}, h("div", {class: "history-heading"},
      h("div", {}, h("p", {class: "eyebrow"}, "JOB HISTORY"), h("h2", {}, t("jobs.history_title"))),
      h("div", {class: "history-controls"}, filter, sortToggle(order, actions.onOrder, t("jobs.history_sort")))),
      active ? h("p", {class: "history-notice"}, t("jobs.history_locked")) : null,
      h("div", {class: "history-list"}, rows.length ? rows : h("p", {class: "empty compact"}, t("jobs.history_empty"))),
      renderPagination(data, actions.onPage, t("jobs.history_pagination")));
  }

  export function renderBackupJobPage(
    job: WebJob, creators: CreatorSummary[], activeJob: WebJob | null, actions: BackupViewActions,
  ): HTMLElement {
    const active = isActiveJob(job);
    const blocked = Boolean(activeJob && activeJob.job_id !== job.job_id);
    const plan = (job.events ?? []).find(item => item.kind === "plan_ready");
    const retryable = ["failed", "cancelled", "interrupted"].includes(job.status);
    const selectedCreators = requestCreators(job.request);
    const creatorNames = new Map(creators.map(item => [item.creator_id, item.name]));
    const controls = h("div", {class: "job-actions"},
      active && job.external ? h("p", {class: "notice"},
        t("jobs.background_job_notice")) : null,
      active && !job.external ? h("button", {type: "button", class: "danger", onclick: () => actions.onCancel(job.job_id)},
        job.status === "cancelling" ? t("jobs.stopping") : t("jobs.stop")) : null,
      retryable ? h("button", {type: "button", class: "retry", disabled: blocked,
        onclick: () => actions.onRetry(job.job_id)}, t("jobs.retry_same")) : null,
      !active ? h("button", {type: "button", disabled: blocked, onclick: actions.onNew}, t("jobs.new_job")) : null,
      h("button", {type: "button", class: "secondary", disabled: active, onclick: actions.onHistory}, t("jobs.history")));
    return h("section", {class: "page backup-page", "data-job-id": job.job_id},
      jobPart(h("header", {class: "heading job-heading"}, h("div", {}, h("p", {class: "eyebrow"}, "BACKUP JOB"),
        h("h1", {}, t("jobs.job_title")), h("p", {}, jobModeLabel(job))),
      h("span", {class: `job-status status-${job.status}`}, statusText(job.status))), "header"),
      jobPart(activeJobNotice(blocked ? activeJob : null) || h("div", {hidden: true}), "global-active"),
      jobPart(h("section", {class: "job-scope"}, h("p", {class: "eyebrow"}, "BACKUP SCOPE"),
        h("h2", {}, jobCreatorLabel(job, creators)), selectedCreators.length
          ? h("ul", {}, selectedCreators.map(id => h("li", {}, h("strong", {}, creatorNames.get(id) || id), h("span", {}, `@${id}`))))
          : h("p", {}, t("jobs.all_supporting"))), "scope"),
      jobPart(planSummary(plan, creators) || h("div", {hidden: true}), "plan"),
      jobPart(currentActivity(job), "activity"),
      jobPart(h("p", {class: "job-error", hidden: !job.error}, h("strong", {}, t("jobs.error_label")), job.error || ""), "error"),
      jobPart(h("div", {class: "result-strip", hidden: !job.result}, job.result ? [
        h("span", {}, t("jobs.result_selected"), h("strong", {}, job.result.selected ?? 0)),
        h("span", {}, t("jobs.result_success"), h("strong", {}, job.result.success ?? 0)),
        h("span", {}, t("jobs.result_unchanged"), h("strong", {}, job.result.unchanged ?? 0)),
        h("span", {}, t("jobs.result_failure"), h("strong", {}, job.result.failure ?? 0)),
      ] : null), "result"), jobPart(controls, "actions"), jobPart(eventLog(job.events ?? []), "details"));
  }

  export function renderBackupFormPage(
    creators: CreatorSummary[], defaults: BackupFormDefaults,
    activeJob: WebJob | null, auth: AuthStatus, actions: BackupFormActions,
  ): HTMLElement {
    const blocked = Boolean(activeJob);
    const selected: string[] = [];
    const dryRun = h("input", {id: "backup-dry-run", type: "checkbox", checked: defaults.dryRun}) as HTMLInputElement;
    const includeProfile = h("input", {id: "backup-include-profile", type: "checkbox", checked: defaults.includeProfile}) as HTMLInputElement;
    const includeFancard = h("input", {id: "backup-include-fancard", type: "checkbox", checked: defaults.includeFancard}) as HTMLInputElement;
    const maxPosts = h("input", {id: "backup-max-posts", type: "number", min: 1, max: 100, value: defaults.maxPosts}) as HTMLInputElement;
    const selectedList = h("div", {class: "selected-creator-list"});
    const count = h("strong", {}, t("backup.selected_count", {count: 0}));
    const input = h("input", {type: "search", placeholder: t("backup.search_placeholder"), autocomplete: "off",
      role: "combobox", "aria-label": t("backup.search_label"), "aria-expanded": "false"}) as HTMLInputElement;
    const menu = h("div", {class: "creator-combobox-menu", role: "listbox", hidden: true});
    const combobox = h("div", {class: "creator-combobox form-field"}, h("span", {}, t("backup.add_creator")), input, menu);
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
      count.textContent = t("backup.selected_count", {count: selected.length});
      selectedList.replaceChildren(...(selected.length ? selected.map(id => {
        const creator = creators.find(item => item.creator_id === id);
        return h("div", {class: "selected-creator"}, h("button", {type: "button", class: "remove-creator",
          "aria-label": t("backup.remove_creator", {name: creator?.name || id, creator_id: id}), onclick: () => {
            selected.splice(selected.indexOf(id), 1); renderSelected(); renderCandidates();
          }}, "×"), h("span", {}, h("strong", {}, creator?.name || id), h("small", {}, `@${id}`)));
      }) : [h("p", {class: "empty compact"}, t("backup.no_selection"))]))
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
        : [h("p", {class: "empty compact"}, t("backup.no_match"))]))
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
      h("p", {class: "eyebrow"}, "BACKUP CONTROL"), h("h1", {}, t("backup.title")), h("p", {}, t("backup.subtitle"))),
      h("button", {type: "button", class: "primary", onclick: actions.onHistory}, t("jobs.history"))),
    activeJobNotice(activeJob),
    auth.state !== "authenticated" && auth.state !== "locked" ? h("section", {class: "backup-auth-notice", role: "status"},
      h("div", {}, h("strong", {}, auth.state === "expired" ? t("backup.auth_expired") : t("backup.auth_check")),
        h("p", {}, auth.message)),
      h("button", {type: "button", onclick: actions.onSignIn}, t("backup.go_sign_in"))) : null,
    h("form", {class: "backup-form", onsubmit: (event: Event) => { event.preventDefault(); if (!blocked) start("full", dryRun.checked); }},
      combobox,
      h("section", {class: "selected-creators", "aria-live": "polite"}, h("div", {class: "selected-creators-heading"},
        h("span", {}, t("backup.list_title")), count), selectedList),
      h("label", {}, h("span", {}, t("backup.max_posts")), maxPosts),
      h("label", {class: "checkbox"}, dryRun, h("span", {}, t("backup.dry_run"))),
      h("label", {class: "checkbox"}, includeProfile, h("span", {}, t("backup.include_profile"))),
      h("label", {class: "checkbox"}, includeFancard, h("span", {}, t("backup.include_fancard"))),
      h("button", {type: "submit", class: "primary", disabled: blocked}, t("backup.start_full")),
      h("div", {class: "metadata-actions"}, h("div", {}, h("strong", {}, t("backup.single_title")), h("small", {}, t("backup.single_hint"))),
        h("div", {class: "metadata-buttons"}, h("button", {type: "button", disabled: blocked,
          onclick: () => start("profile", false)}, t("backup.include_profile")),
          h("button", {type: "button", disabled: blocked, onclick: () => start("fancard", false)}, t("backup.include_fancard"))))),
    h("p", {class: "notice"}, t("backup.single_notice")));
  }

  export function renderBackupHistoryPage(
    data: JobPage, creators: CreatorSummary[], filterValue: string, order: SortOrder,
    actions: BackupHistoryActions,
  ): HTMLElement {
    return h("section", {class: "page backup-page"}, h("header", {class: "heading"}, h("div", {},
      h("p", {class: "eyebrow"}, "JOB HISTORY"), h("h1", {}, t("jobs.history")),
      h("p", {}, t("backup.history_subtitle"))),
      h("button", {type: "button", class: "primary", onclick: actions.onNew}, t("jobs.new_job"))),
    jobHistory(data, null, creators, filterValue, order, actions));
  }

  function verificationHistory(
    data: JobPage, selectedId: string | null, order: SortOrder, actions: HistoryActions,
  ): HTMLElement {
    const active = data.active;
    const rows = data.items.map(item => h("button", {type: "button", class: `history-row${item.job_id === selectedId ? " selected" : ""}`,
      disabled: Boolean(active && item.job_id !== active.job_id), onclick: () => actions.onShow(item.job_id)},
    h("span", {class: `history-status status-${item.status}`}, statusText(item.status)),
    h("span", {class: "history-main"}, h("strong", {}, t("jobs.kind_verify")), h("small", {}, formatDate(item.created_at))),
    h("span", {class: "history-result"}, item.result
      ? item.result.passed ? t("verify.passed") : t("verify.issue_count", {count: item.result.issue_count ?? 0})
      : item.error ? t("jobs.view_error") : t("jobs.view_progress"))));
    return h("section", {class: "job-history"}, h("div", {class: "history-heading"},
      h("div", {}, h("p", {class: "eyebrow"}, "VERIFY HISTORY"), h("h2", {}, t("verify.history_title"))),
      sortToggle(order, actions.onOrder, t("verify.history_sort"))),
      active ? h("p", {class: "history-notice"}, t("verify.history_locked")) : null,
      h("div", {class: "history-list"}, rows.length ? rows : h("p", {class: "empty compact"}, t("verify.history_empty"))),
      renderPagination(data, actions.onPage, t("verify.history_pagination")));
  }

  export function renderMaintenancePage(
    job: WebJob | null, history: JobPage, order: SortOrder, activeJob: WebJob | null,
    actions: MaintenanceActions,
  ): HTMLElement {
    const active = Boolean(activeJob);
    const result = job?.result;
    const issues = result?.issues ?? [];
    const issueRows = issues.map(item => h("li", {}, h("strong", {}, item.reason), h("code", {}, item.path),
      item.post_id ? h("small", {}, `Post ${item.post_id}`) : null));
    return h("section", {class: "page maintenance-page"}, h("header", {class: "heading"}, h("div", {},
      h("p", {class: "eyebrow"}, "ARCHIVE MAINTENANCE"), h("h1", {}, t("verify.title")),
      h("p", {}, t("verify.subtitle"))),
      job ? h("span", {class: `job-status status-${job.status}`}, statusText(job.status)) : null),
    activeJobNotice(activeJob),
    h("section", {class: "maintenance-action"}, h("div", {}, h("h2", {},
      activeJob?.kind === "verify" ? t("verify.running") : activeJob ? t("verify.other_job") : t("verify.integrity")),
      h("p", {}, t("verify.hint"))),
      h("button", {type: "button", class: "primary", disabled: active, onclick: actions.onStart},
        activeJob?.kind === "verify" ? t("verify.button_running") : activeJob ? t("verify.button_blocked") : t("verify.button_start"))),
    job?.error ? h("p", {class: "job-error"}, h("strong", {}, t("jobs.error_label")), job.error) : null,
    verificationProgress(job),
    result ? h("section", {class: `verification-result ${result.passed ? "passed" : "issues"}`},
      h("div", {class: "verification-summary"}, h("strong", {}, result.passed ? t("verify.passed") : t("verify.issue_count", {count: result.issue_count ?? 0})),
        h("span", {}, result.passed ? t("verify.passed_detail") : t("verify.issues_detail"))),
      issueRows.length ? h("ul", {class: "verification-issues"}, issueRows) : null,
      result.truncated ? h("p", {class: "notice"}, t("verify.truncated")) : null) : null,
    verificationHistory(history, job?.job_id ?? null, order, actions));
  }
}
