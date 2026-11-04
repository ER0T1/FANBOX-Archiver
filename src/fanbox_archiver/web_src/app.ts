namespace FanboxUI {
  export function startApp(): void {
    const appElement = document.getElementById("app");
    const searchElement = document.getElementById("search");
    const navElement = document.getElementById("nav");
    const tokenMeta = document.querySelector<HTMLMetaElement>('meta[name="fanbox-session-token"]');
    if (!(appElement instanceof HTMLElement) || !(searchElement instanceof HTMLInputElement)
      || !(navElement instanceof HTMLElement) || !tokenMeta) {
      throw new Error("GUI 缺少必要的頁面元素");
    }
    const app: HTMLElement = appElement;
    const search: HTMLInputElement = searchElement;
    const nav: HTMLElement = navElement;
    const sessionToken = tokenMeta.content;
    setDisplayTimeZone(document.querySelector<HTMLMetaElement>('meta[name="fanbox-timezone"]')?.content);
    applyI18n(document);
    const state = createInitialState();
    let jobTimer: number | undefined;
    let searchTimer: number | undefined;
    // The one page load that may still draw: every navigation, page, sort, tab or search starts a
    // new load and gives up the previous one (its requests are aborted and its results dropped).
    let currentLoad: AbortController | null = null;

    interface Load {
      signal: AbortSignal;
      /** False once the user moved on; check after every await, before touching the page or state. */
      live(): boolean;
    }

    function beginLoad(): Load {
      currentLoad?.abort();
      if (jobTimer !== undefined) clearTimeout(jobTimer);
      const controller = new AbortController();
      currentLoad = controller;
      return {signal: controller.signal, live: () => currentLoad === controller && !controller.signal.aborted};
    }

    /** Shows an error only for the load still on screen; given-up loads fail silently. */
    function loadFailed(load: Load, error: unknown): void {
      if (load.live() && !isAbortError(error)) errorView(error);
    }

    /** A read whose failure is tolerated, but whose abort still ends the load. */
    function optional<T>(request: Promise<T>): Promise<T | null> {
      return request.catch(error => {
        if (isAbortError(error)) throw error;
        return null;
      });
    }

    document.addEventListener("click", event => closeDropdownsOutside(event.target));

    function errorView(error: unknown): void {
      app.replaceChildren(renderError(error, refreshView));
    }

    function setActiveNav(view: View): void {
      setActiveNavigation(nav, view);
    }

    function setSearch(view: View): void {
      setSearchState(search, view, state.creatorTab);
    }

    // The saved theme, rendered by the server; an unsaved settings preview never outlives the page.
    let savedTheme = document.documentElement.dataset.theme ?? "auto";

    function setView(view: View): void {
      currentLoad?.abort();
      if (jobTimer !== undefined) clearTimeout(jobTimer);
      document.documentElement.dataset.theme = savedTheme;
      state.view = view;
      state.current = null;
      state.page = 1;
      state.tag = "";
      if (view === "backup") {
        state.backupScreen = "form";
        state.backupJobId = null;
      }
      if (view !== "creator") state.creatorId = null;
      if (view !== "settings") {
        settingsPage = null;
        if (location.hash.startsWith("#settings")) history.pushState(null, "", `${location.pathname}${location.search}`);
      }
      setActiveNav(view);
      setSearch(view);
      void refreshView();
    }

    function refreshView(showLoading = true): void | Promise<void> {
      if (state.view === "backup") return loadBackup(showLoading);
      if (state.view === "maintenance") return loadMaintenance(showLoading);
      if (state.view === "settings") return showLoading ? loadSettings() : refreshSettings();
      if (state.view === "creators") return loadCreators();
      if (state.view === "creator" && state.creatorId) return loadCreator(state.creatorId, state.creatorTab);
      return loadPosts();
    }

    function updateActiveJob(data: JobPage): WebJob | null {
      state.activeJob = data.active;
      return state.activeJob;
    }

    function historyParams(kind: "backup" | "verify", page: number, order: SortOrder, status = "all"): URLSearchParams {
      const params = new URLSearchParams({kind, page: String(page), page_size: "20", order});
      if (status !== "all") params.set("status", status);
      return params;
    }

    function scheduleJobRefresh(authChecking = false): void {
      if (jobTimer !== undefined) clearTimeout(jobTimer);
      if (state.activeJob && ["backup", "maintenance", "settings"].includes(state.view)
        || state.view === "settings" && authChecking) {
        jobTimer = window.setTimeout(() => void refreshView(false), 900);
      }
    }

    async function loadPosts(): Promise<void> {
      const load = beginLoad();
      state.current = null;
      app.replaceChildren(h("p", {class: "empty"}, t("common.loading_posts")));
      try {
        const params = new URLSearchParams({page: String(state.page), page_size: "20", order: state.postOrder});
        if (state.q) params.set("q", state.q);
        const data = await getPosts(params, load.signal);
        if (!load.live()) return;
        state.page = data.page;
        app.replaceChildren(renderPostListPage(data, {
          onOpen: postId => void loadPost(postId),
          onPage: page => { state.page = page; void loadPosts(); },
          order: state.postOrder,
          onOrder: order => { state.postOrder = order; state.page = 1; void loadPosts(); },
        }));
      } catch (error) {
        loadFailed(load, error);
      }
    }

    async function loadPost(postId: string, version: number | null = null): Promise<void> {
      const load = beginLoad();
      const creatorContent = state.view === "creator"
        ? app.querySelector<HTMLElement>(".creator-content") : null;
      const target = creatorContent ?? app;
      const creatorId = state.creatorId;
      const back = creatorContent && creatorId
        ? () => void loadCreator(creatorId, "posts") : () => void loadPosts();
      state.postNavigation = null;
      target.replaceChildren(h("p", {class: "empty"}, t("common.loading_posts")));
      try {
        const params = new URLSearchParams({order: state.postOrder});
        if (version !== null) params.set("version", String(version));
        if (creatorContent && creatorId) params.set("creator", creatorId);
        if (state.q) params.set("q", state.q);
        if (creatorContent && state.tag) params.set("tag", state.tag);
        const post = await getPost(postId, params, load.signal);
        if (!load.live()) return;
        state.current = postId;
        state.postNavigation = post.navigation;
        const versionSelect = customSelect({id: "post-version", label: "版本", value: post.version,
          options: post.versions.map(item => ({value: item.number,
            label: `v${String(item.number).padStart(4, "0")} · ${formatDate(item.captured_at)}`})),
          onChange: value => void loadPost(postId, Number(value))});
        target.replaceChildren(renderPostReader(post, {
          onBack: back,
          onOpenPost: nextPostId => void loadPost(nextPostId),
          versionSelect,
        }));
      } catch (error) {
        loadFailed(load, error);
      }
    }

    async function loadCreators(): Promise<void> {
      const load = beginLoad();
      state.current = null;
      app.replaceChildren(h("p", {class: "empty"}, "正在讀取創作者…"));
      try {
        const data = await getCreators(load.signal);
        if (!load.live()) return;
        app.replaceChildren(renderCreatorsPage(data.items, state.q, creatorId => openCreator(creatorId)));
      } catch (error) {
        loadFailed(load, error);
      }
    }

    function openCreator(creatorId: string, tab: CreatorTab = "profile"): void {
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

    function switchCreatorTab(creatorId: string, tab: CreatorTab): void {
      state.creatorTab = tab;
      state.current = null;
      state.page = 1;
      state.q = "";
      state.tag = "";
      search.value = "";
      setSearch("creator");
      void loadCreator(creatorId, tab);
    }

    function creatorShell(
      creator: CreatorDetail, tab: CreatorTab, content: HTMLElement,
      profile: CreatorProfile | null = null,
    ): HTMLElement {
      return renderCreatorShell(creator, tab, content, profile, {
        onBack: () => setView("creators"),
        onTab: nextTab => switchCreatorTab(creator.creator_id, nextTab),
      });
    }

    async function loadCreator(
      creatorId: string, tab: CreatorTab = "profile", profileVersion: number | null = null,
    ): Promise<void> {
      const load = beginLoad();
      state.creatorTab = tab;
      setSearch("creator");
      try {
        let creator = state.creator?.creator_id === creatorId ? state.creator : null;
        let heroProfile = state.creatorProfile;
        if (!creator) {
          app.replaceChildren(h("p", {class: "empty"}, "正在讀取創作者頁面…"));
          creator = await getCreator(creatorId, load.signal);
          heroProfile = creator.profile_available ? await getCreatorProfile(creatorId, null, load.signal) : null;
          if (!load.live() || state.creatorId !== creatorId) return;
          state.creator = creator;
          state.creatorProfile = heroProfile;
          app.replaceChildren(creatorShell(creator, tab, h("p", {class: "empty"}, "正在讀取內容…"), heroProfile));
        }
        let shell = app.querySelector<HTMLElement>(".creator-page");
        if (!shell || shell.dataset.creatorId !== creatorId) {
          app.replaceChildren(creatorShell(creator, tab, h("p", {class: "empty"}, "正在讀取內容…"), heroProfile));
          shell = app.querySelector<HTMLElement>(".creator-page");
        }
        if (!shell) return;
        for (const button of shell.querySelectorAll<HTMLButtonElement>("[data-creator-tab]")) {
          button.classList.toggle("active", button.dataset.creatorTab === tab);
        }
        const contentRoot = shell.querySelector<HTMLElement>(".creator-content");
        if (!contentRoot) return;
        contentRoot.replaceChildren(h("p", {class: "empty"}, "正在讀取內容…"));
        let content: HTMLElement;
        if (tab === "posts") {
          const params = new URLSearchParams({creator: creatorId, page: String(state.page), page_size: "20",
            order: state.postOrder});
          if (state.q) params.set("q", state.q);
          if (state.tag) params.set("tag", state.tag);
          const data = await getPosts(params, load.signal);
          if (!load.live()) return;
          state.page = data.page;
          content = renderCreatorPostList(data, {
            onOpen: postId => void loadPost(postId),
            onPage: page => { state.page = page; void loadCreator(creatorId, "posts"); },
            order: state.postOrder,
            onOrder: order => { state.postOrder = order; state.page = 1; void loadCreator(creatorId, "posts"); },
            activeTag: state.tag,
            onTag: tag => {
              state.tag = tag;
              state.page = 1;
              history.pushState({fanboxCreatorId: creatorId, fanboxCreatorTag: tag}, "", location.href);
              void loadCreator(creatorId, "posts");
            },
          });
        } else if (tab === "fancards") {
          const params = new URLSearchParams({creator: creatorId});
          if (state.q) params.set("q", state.q);
          const data = await getFanCards(params, load.signal);
          content = renderFanCardList(data, {onOpen: (id, month) => void loadFancard(id, month)});
        } else {
          let profile = heroProfile;
          if (creator.profile_available && profileVersion !== null) {
            profile = await getCreatorProfile(creatorId, profileVersion, load.signal);
          }
          const versionSelect = profile ? customSelect({id: "profile-version", label: "Profile 版本", value: profile.version,
            options: profile.versions.map(item => ({value: item.number,
              label: `v${String(item.number).padStart(4, "0")} · ${formatDate(item.captured_at)}`})),
            onChange: value => void loadCreator(creatorId, "profile", Number(value))}) : null;
          content = renderCreatorProfile(creator, profile, versionSelect);
        }
        if (!load.live() || state.creatorId !== creatorId || state.creatorTab !== tab) return;
        contentRoot.replaceChildren(content);
      } catch (error) {
        if (state.creatorId !== creatorId) return;
        loadFailed(load, error);
      }
    }

    async function loadFancard(
      creatorId: string, month: string, version: number | null = null,
    ): Promise<void> {
      const creatorContent = state.view === "creator"
        ? app.querySelector<HTMLElement>(".creator-content") : null;
      const load = beginLoad();
      const target = creatorContent ?? app;
      target.replaceChildren(h("p", {class: "empty"}, "正在讀取粉絲卡…"));
      try {
        const card = await getFanCard(creatorId, month, version, load.signal);
        if (!load.live()) return;
        state.current = {type: "fancard", creatorId, month};
        const versionSelect = customSelect({id: "fancard-version", label: "版本", value: card.version,
          options: card.versions.map(item => ({value: item.number,
            label: `v${String(item.number).padStart(4, "0")} · ${formatDate(item.captured_at)}`})),
          onChange: value => void loadFancard(creatorId, month, Number(value))});
        target.replaceChildren(renderFanCardReader(card, {
          onBack: () => void loadCreator(creatorId, "fancards"), versionSelect,
        }));
      } catch (error) {
        loadFailed(load, error);
      }
    }

    async function showJob(jobId: string, creators: CreatorSummary[]): Promise<void> {
      const load = beginLoad();
      try {
        const job = await getJob(jobId, load.signal);
        if (!load.live()) return;
        state.backupScreen = "job";
        state.backupJobId = jobId;
        renderJob(job, creators);
      } catch (error) {
        loadFailed(load, error);
      }
    }

    function renderJob(job: WebJob, creators: CreatorSummary[]): void {
      if (jobTimer !== undefined) clearTimeout(jobTimer);
      const active = isActiveJob(job);
      const page = renderBackupJobPage(job, creators, state.activeJob, {
        onCancel: jobId => void cancelBackupJob(jobId),
        onRetry: jobId => void retryBackupJob(jobId),
        onNew: () => { state.backupScreen = "form"; state.backupJobId = null; void loadBackup(false); },
        onHistory: () => { state.backupScreen = "history"; state.backupJobId = null; void loadBackup(false); },
      });
      const currentPage = app.querySelector<HTMLElement>(".backup-page[data-job-id]");
      if (currentPage?.dataset.jobId === job.job_id) updateJobPage(currentPage, page, active);
      else app.replaceChildren(page);
      scheduleJobRefresh();
    }

    function renderBackupForm(
      creators: CreatorSummary[], settings: SettingsResponse, auth: AuthStatus,
    ): void {
      const value = settings.editable;
      app.replaceChildren(renderBackupFormPage(creators, {
        dryRun: value.backup_defaults.dry_run,
        includeProfile: value.backup_defaults.include_profile,
        includeFancard: value.backup_defaults.include_fancard,
        maxPosts: value.sync.max_posts_per_run,
      }, state.activeJob, auth, {
        onStart: (creators, dryRun, maxPosts, mode, includeProfile, includeFancard) =>
          void startBackup(creators, dryRun, maxPosts, mode, includeProfile, includeFancard),
        onHistory: () => { state.backupScreen = "history"; void loadBackup(false); },
        onSignIn: () => void navigate("settings", "account"),
      }));
      scheduleJobRefresh();
    }

    function renderBackupHistory(creators: CreatorSummary[], history: JobPage): void {
      state.jobPage = history.page;
      app.replaceChildren(renderBackupHistoryPage(history, creators, state.jobFilter, state.jobOrder, {
        onNew: () => { state.backupScreen = "form"; void loadBackup(false); },
        onShow: jobId => void showJob(jobId, creators),
        onFilter: value => { state.jobFilter = value; state.jobPage = 1; void loadBackup(false); },
        onOrder: order => { state.jobOrder = order; state.jobPage = 1; void loadBackup(false); },
        onPage: page => { state.jobPage = page; void loadBackup(false); },
      }));
    }

    async function loadBackup(showLoading = true): Promise<void> {
      const load = beginLoad();
      state.current = null;
      if (showLoading) app.replaceChildren(h("p", {class: "empty"}, "正在讀取工作狀態…"));
      try {
        const [creatorData, jobData, settings, auth] = await Promise.all([
          getCreators(load.signal),
          getJobs(historyParams("backup", state.jobPage, state.jobOrder, state.jobFilter), load.signal),
          getSettings(load.signal), getAuthStatus(sessionToken, load.signal),
        ]);
        if (!load.live()) return;
        updateActiveJob(jobData);
        const active = jobData.active?.kind === "backup" ? jobData.active : null;
        if (active) {
          const job = await getJob(active.job_id, load.signal);
          if (!load.live()) return;
          state.backupScreen = "job";
          state.backupJobId = active.job_id;
          renderJob({...job, external: active.external}, creatorData.items);
        } else if (state.backupScreen === "job" && state.backupJobId) {
          const selected = await optional(getJob(state.backupJobId, load.signal));
          if (!load.live()) return;
          if (selected) renderJob(selected, creatorData.items);
          else { state.backupScreen = "form"; state.backupJobId = null; renderBackupForm(creatorData.items, settings, auth); }
        } else if (state.backupScreen === "history") renderBackupHistory(creatorData.items, jobData);
        else renderBackupForm(creatorData.items, settings, auth);
      } catch (error) {
        loadFailed(load, error);
      }
    }

    async function startBackup(
      creators: string[], dryRun: boolean, maxPosts: number,
      mode: "full" | "profile" | "fancard" = "full",
      includeProfile = true, includeFancard = true,
    ): Promise<void> {
      // The write itself is never aborted; only drawing its result is skipped if the user left.
      const load = beginLoad();
      try {
        const job = await startBackupJob({creators, dry_run: dryRun, max_posts: maxPosts, mode,
          include_profile: includeProfile, include_fancard: includeFancard}, sessionToken);
        if (!load.live()) return;
        state.backupScreen = "job";
        state.backupJobId = job.job_id;
        await renderJobWithActive(job, load);
      } catch (error) {
        loadFailed(load, error);
      }
    }

    async function renderJobWithActive(job: WebJob, load: Load): Promise<void> {
      const [creatorData, jobData] = await Promise.all([getCreators(load.signal), getJobs(undefined, load.signal)]);
      if (!load.live()) return;
      updateActiveJob(jobData);
      renderJob(job, creatorData.items);
    }

    async function cancelBackupJob(jobId: string): Promise<void> {
      const load = beginLoad();
      try {
        const job = await cancelJob(jobId, sessionToken);
        if (load.live()) await renderJobWithActive(job, load);
      } catch (error) {
        loadFailed(load, error);
      }
    }

    async function retryBackupJob(jobId: string): Promise<void> {
      const load = beginLoad();
      try {
        const job = await retryJob(jobId, sessionToken);
        if (load.live()) await renderJobWithActive(job, load);
      } catch (error) {
        loadFailed(load, error);
      }
    }

    function renderMaintenance(job: WebJob | null, history: JobPage): void {
      if (jobTimer !== undefined) clearTimeout(jobTimer);
      state.verifyPage = history.page;
      app.replaceChildren(renderMaintenancePage(job, history, state.verifyOrder, state.activeJob, {
        onStart: () => void startVerification(),
        onShow: jobId => { state.verifyJobId = jobId; void loadMaintenance(false); },
        onOrder: order => { state.verifyOrder = order; state.verifyPage = 1; void loadMaintenance(false); },
        onPage: page => { state.verifyPage = page; void loadMaintenance(false); },
      }));
      scheduleJobRefresh();
    }

    async function loadMaintenance(showLoading = true): Promise<void> {
      const load = beginLoad();
      state.current = null;
      if (showLoading) app.replaceChildren(h("p", {class: "empty"}, "正在讀取驗證狀態…"));
      try {
        const [history, newest] = await Promise.all([
          getJobs(historyParams("verify", state.verifyPage, state.verifyOrder), load.signal),
          getJobs(historyParams("verify", 1, "desc"), load.signal),
        ]);
        if (!load.live()) return;
        // Show the running verification, else the one the user picked, else the newest result.
        const selectedId = (history.active?.kind === "verify" ? history.active.job_id : null)
          ?? state.verifyJobId ?? newest.items[0]?.job_id ?? null;
        const selected = selectedId ? await optional(getJob(selectedId, load.signal)) : null;
        if (!load.live()) return;
        updateActiveJob(history);
        renderMaintenance(selected, history);
      } catch (error) {
        loadFailed(load, error);
      }
    }

    async function startVerification(): Promise<void> {
      const load = beginLoad();
      try {
        const job = await startVerificationJob(sessionToken);
        if (!load.live()) return;
        state.verifyJobId = job.job_id;
        const history = await getJobs(historyParams("verify", state.verifyPage, state.verifyOrder), load.signal);
        if (!load.live()) return;
        updateActiveJob(history);
        renderMaintenance(job, history);
      } catch (error) {
        loadFailed(load, error);
      }
    }

    // The settings sub-page on screen, its data, and the extra data only some sub-pages need.
    let settingsPage: SettingsPageHandle | null = null;
    let settingsData: SettingsResponse | null = null;
    let settingsExtras: {
      schedule?: {status: ScheduleStatus; creators: CreatorSummary[]};
      diagnostics?: DiagnosticsInfo | null;
    } = {};

    function settingsUrl(tab: SettingsTab): string {
      return `${location.pathname}${location.search}#settings/${tab}`;
    }

    function settingsTabFromHash(): SettingsTab | null {
      const match = /^#settings(?:\/([a-z]+))?$/.exec(location.hash);
      if (!match) return null;
      return isSettingsTab(match[1]) ? match[1] : "general";
    }

    /** Asks before unsaved settings are thrown away; true when it is fine to leave. */
    async function confirmLeaveSettings(): Promise<boolean> {
      if (state.view !== "settings" || !settingsPage?.isDirty()) return true;
      return confirmDialog({
        title: "放棄未儲存的變更？",
        message: "這個子頁面有尚未儲存的變更，離開後這些變更會遺失。",
        cancelLabel: "繼續編輯", confirmLabel: "放棄變更", danger: true,
      });
    }

    async function navigate(view: View, tab: SettingsTab | null = null): Promise<void> {
      if (!await confirmLeaveSettings()) return;
      if (tab) state.settingsTab = tab;
      if (view === "settings") history.pushState(null, "", settingsUrl(state.settingsTab));
      setView(view);
    }

    async function switchSettingsTab(tab: SettingsTab): Promise<void> {
      if (!await confirmLeaveSettings()) return;
      history.pushState(null, "", settingsUrl(tab));
      openSettingsTab(tab);
    }

    function openSettingsTab(tab: SettingsTab): void {
      state.settingsTab = tab;
      // An unsaved theme preview never outlives its sub-page.
      document.documentElement.dataset.theme = savedTheme;
      void loadSettings();
    }

    const errorText = (error: unknown): string => error instanceof Error ? error.message : String(error);

    function renderSettings(message: string): void {
      if (!settingsData) return;
      const tab = state.settingsTab;
      settingsPage = renderSettingsPage({
        data: settingsData, tab, message, activeJob: state.activeJob,
        onTab: next => void switchSettingsTab(next),
        onSave: patch => saveSettingsForm(patch),
        auth: null,
        account: {
          onRefresh: () => void loadSettings(),
          onLogin: () => authAction(async () => { await startAuthLogin(sessionToken); },
            "登入視窗已開啟；請在專用 Chrome 中完成登入。"),
          onCancel: jobId => authAction(async () => { await cancelAuthLogin(jobId, sessionToken); },
            "正在取消登入…"),
          onLogout: () => authAction(async () => { await logoutAuth(sessionToken); },
            "已安全登出；封存與設定均未變更。"),
        },
        schedule: settingsExtras.schedule ? {...settingsExtras.schedule, actions: {
          onPreview: schedule => previewSchedule(schedule, sessionToken),
          onRunNow: async () => {
            try {
              // The backup page opens the running job, which this one now is.
              await runScheduleNow(sessionToken);
              setView("backup");
              return null;
            } catch (error) {
              return errorText(error);
            }
          },
        }} : undefined,
        about: tab === "about" ? {info: settingsExtras.diagnostics ?? null, actions: {
          onOpen: async target => {
            try {
              await openDiagnosticsFolder(target, sessionToken);
              return null;
            } catch (error) {
              return errorText(error);
            }
          },
        }} : undefined,
      });
      app.replaceChildren(settingsPage.node);
    }

    /** The sign-in check runs after the account sub-page is shown, and only there. */
    function checkAuth(load: Load): void {
      getAuthStatus(sessionToken, load.signal).then(auth => {
        if (!load.live() || state.view !== "settings" || state.settingsTab !== "account") return;
        settingsPage?.setAuth(auth);
        scheduleJobRefresh(auth.state === "checking");
      }).catch(error => {
        if (!load.live() || isAbortError(error)) return;
        settingsPage?.setAuth({state: "error", source: "none", message: `無法檢查登入狀態：${errorText(error)}`,
          can_login: false, can_logout: false, externally_managed: false, job: null});
      });
    }

    async function loadSettings(message = "", showLoading = true): Promise<void> {
      const load = beginLoad();
      const tab = state.settingsTab;
      state.current = null;
      settingsPage = null;
      if (showLoading) app.replaceChildren(h("p", {class: "empty"}, "正在讀取設定…"));
      try {
        // Each sub-page reads only what it shows; only "帳號與登入" asks for the sign-in check.
        const [data, jobData, schedule, diagnostics] = await Promise.all([
          getSettings(load.signal), getJobs(undefined, load.signal),
          tab === "backup" ? Promise.all([getScheduleStatus(load.signal), getCreators(load.signal)]) : null,
          tab === "about" ? optional(getDiagnostics(sessionToken, load.signal)) : null,
        ]);
        if (!load.live()) return;
        updateActiveJob(jobData);
        settingsData = data;
        settingsExtras = {
          schedule: schedule ? {status: schedule[0], creators: schedule[1].items} : undefined,
          diagnostics,
        };
        setDisplayTimeZone(data.display.timezone);
        // A preview that was never saved is undone whenever the page reloads its settings.
        applyTheme(data.editable.display.theme);
        savedTheme = document.documentElement.dataset.theme ?? "auto";
        renderSettings(message);
        if (tab === "account") checkAuth(load);
        scheduleJobRefresh();
      } catch (error) {
        loadFailed(load, error);
      }
    }

    /** Background refresh while a job runs: updates the lock without redrawing unsaved input. */
    async function refreshSettings(): Promise<void> {
      if (!settingsPage) return loadSettings("", false);
      const load = beginLoad();
      try {
        const jobData = await getJobs(undefined, load.signal);
        if (!load.live()) return;
        updateActiveJob(jobData);
        settingsPage.setLocked(state.activeJob);
        if (state.settingsTab === "account") checkAuth(load);
        scheduleJobRefresh();
      } catch (error) {
        loadFailed(load, error);
      }
    }

    async function authAction(action: () => Promise<void>, message: string): Promise<string | null> {
      try {
        await action();
        // The write always finishes; the account sub-page is redrawn only if the user is still on it.
        if (state.view === "settings" && state.settingsTab === "account") void loadSettings(message, false);
        return null;
      } catch (error) {
        return errorText(error);
      }
    }

    async function saveSettingsForm(patch: SettingsSavePatch): Promise<string | null> {
      const tab = state.settingsTab;
      try {
        const result = await saveSettings(patch, sessionToken);
        if (state.view !== "settings" || state.settingsTab !== tab || !settingsData) return null;
        const languageChanged = patch.display?.language !== undefined
          && result.editable.display.language !== settingsData.editable.display.language;
        // Saving updates this sub-page only; the page and the sign-in state are not reloaded.
        settingsData = {...settingsData, editable: result.editable, display: result.display};
        setDisplayTimeZone(result.display.timezone);
        if (patch.display?.theme !== undefined || patch.display?.colors !== undefined) {
          applyTheme(result.editable.display.theme);
          savedTheme = document.documentElement.dataset.theme ?? "auto";
          // Re-read the generated custom-colour stylesheet so a saved palette applies at once.
          document.getElementById("custom-theme")?.setAttribute("href", `/theme.css?v=${Date.now()}`);
        }
        if (tab === "backup" && settingsExtras.schedule) {
          const status = await optional(getScheduleStatus());
          if (status) settingsExtras.schedule = {...settingsExtras.schedule, status};
          if (state.view !== "settings" || state.settingsTab !== tab) return null;
        }
        renderSettings(languageChanged
          ? "設定已安全寫入；介面語言會在重新整理頁面後套用。"
          : "設定已安全寫入；後續新工作會使用更新後的值。日誌處理器變更會在重新啟動後完整套用。");
        return null;
      } catch (error) {
        return errorText(error);
      }
    }

    search.addEventListener("input", () => {
      if (searchTimer !== undefined) clearTimeout(searchTimer);
      searchTimer = window.setTimeout(() => {
        state.q = search.value.trim();
        state.page = 1;
        void refreshView();
      }, 180);
    });
    nav.addEventListener("click", event => {
      const target = event.target instanceof Element
        ? event.target.closest<HTMLButtonElement>("button[data-view]") : null;
      const view = target?.dataset.view;
      if (!view || !["posts", "creators", "backup", "maintenance", "settings"].includes(view)) return;
      void (async () => {
        if (!await confirmLeaveSettings()) return;
        state.q = "";
        search.value = "";
        if (view === "settings") history.pushState(null, "", settingsUrl(state.settingsTab));
        setView(view as View);
      })();
    });
    window.addEventListener("popstate", event => {
      const hashTab = settingsTabFromHash();
      if (state.view === "settings" && hashTab !== state.settingsTab) {
        const current = state.settingsTab;
        void confirmLeaveSettings().then(ok => {
          // Declined: put the address back where the unsaved sub-page is.
          if (!ok) { history.pushState(null, "", settingsUrl(current)); return; }
          if (hashTab) openSettingsTab(hashTab);
          else setView("posts");
        });
        return;
      }
      if (hashTab && state.view !== "settings") {
        state.settingsTab = hashTab;
        setView("settings");
        return;
      }
      if (state.view !== "creator" || state.creatorTab !== "posts" || !state.creatorId) return;
      const historyState = event.state as {fanboxCreatorId?: string; fanboxCreatorTag?: string} | null;
      if (historyState?.fanboxCreatorId && historyState.fanboxCreatorId !== state.creatorId) return;
      state.tag = historyState?.fanboxCreatorTag ?? "";
      state.page = 1;
      void loadCreator(state.creatorId, "posts");
    });
    window.addEventListener("keydown", event => {
      if (["ArrowLeft", "ArrowRight"].includes(event.key)
        && typeof state.current === "string" && state.postNavigation) {
        const target = event.target;
        const interactive = target instanceof Element && (
          target.matches("input,textarea,select,button,a,summary,[contenteditable='true']")
          || target.closest(".custom-select,.page-jump")
        );
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
      if (event.key !== "Escape") return;
      if (closeDropdownsAndFocus()) return;
      if (state.current) void refreshView();
    });
    window.addEventListener("beforeunload", event => {
      if (state.view === "settings" && settingsPage?.isDirty()) {
        event.preventDefault();
        event.returnValue = "";
      }
    });
    const startTab = settingsTabFromHash();
    if (startTab) state.settingsTab = startTab;
    setView(startTab ? "settings" : "posts");
  }
}

if (typeof document !== "undefined" && document.getElementById("app")) FanboxUI.startApp();
