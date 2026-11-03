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
    const state = createInitialState();
    let jobTimer: number | undefined;
    let searchTimer: number | undefined;
    let creatorRequest = 0;

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

    function setView(view: View): void {
      if (jobTimer !== undefined) clearTimeout(jobTimer);
      state.view = view;
      state.current = null;
      state.page = 1;
      state.tag = "";
      if (view === "backup") {
        state.backupScreen = "form";
        state.backupJobId = null;
      }
      if (view !== "creator") state.creatorId = null;
      setActiveNav(view);
      setSearch(view);
      void refreshView();
    }

    function refreshView(showLoading = true): void | Promise<void> {
      if (state.view === "backup") return loadBackup(showLoading);
      if (state.view === "maintenance") return loadMaintenance(showLoading);
      if (state.view === "settings") return loadSettings("", showLoading);
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

    function scheduleJobRefresh(): void {
      if (jobTimer !== undefined) clearTimeout(jobTimer);
      if (state.activeJob && ["backup", "maintenance", "settings"].includes(state.view)
        || state.view === "settings" && app.querySelector(".auth-badge")?.textContent === "檢查中") {
        jobTimer = window.setTimeout(() => void refreshView(false), 900);
      }
    }

    async function loadPosts(): Promise<void> {
      state.current = null;
      app.replaceChildren(h("p", {class: "empty"}, "正在讀取投稿…"));
      try {
        const params = new URLSearchParams({page: String(state.page), page_size: "20", order: state.postOrder});
        if (state.q) params.set("q", state.q);
        const data = await getPosts(params);
        state.page = data.page;
        app.replaceChildren(renderPostListPage(data, {
          onOpen: postId => void loadPost(postId),
          onPage: page => { state.page = page; void loadPosts(); },
          order: state.postOrder,
          onOrder: order => { state.postOrder = order; state.page = 1; void loadPosts(); },
        }));
      } catch (error) {
        errorView(error);
      }
    }

    async function loadPost(postId: string, version: number | null = null): Promise<void> {
      const creatorContent = state.view === "creator"
        ? app.querySelector<HTMLElement>(".creator-content") : null;
      const target = creatorContent ?? app;
      const creatorId = state.creatorId;
      const back = creatorContent && creatorId
        ? () => void loadCreator(creatorId, "posts") : () => void loadPosts();
      state.postNavigation = null;
      target.replaceChildren(h("p", {class: "empty"}, "正在讀取投稿…"));
      try {
        const params = new URLSearchParams({order: state.postOrder});
        if (version !== null) params.set("version", String(version));
        if (creatorContent && creatorId) params.set("creator", creatorId);
        if (state.q) params.set("q", state.q);
        if (creatorContent && state.tag) params.set("tag", state.tag);
        const post = await getPost(postId, params);
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
        errorView(error);
      }
    }

    async function loadCreators(): Promise<void> {
      state.current = null;
      app.replaceChildren(h("p", {class: "empty"}, "正在讀取創作者…"));
      try {
        const data = await getCreators();
        app.replaceChildren(renderCreatorsPage(data.items, state.q, creatorId => openCreator(creatorId)));
      } catch (error) {
        errorView(error);
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
      state.creatorTab = tab;
      setSearch("creator");
      const requestNumber = ++creatorRequest;
      try {
        let creator = state.creator?.creator_id === creatorId ? state.creator : null;
        let heroProfile = state.creatorProfile;
        if (!creator) {
          app.replaceChildren(h("p", {class: "empty"}, "正在讀取創作者頁面…"));
          creator = await getCreator(creatorId);
          heroProfile = creator.profile_available ? await getCreatorProfile(creatorId) : null;
          if (requestNumber !== creatorRequest || state.creatorId !== creatorId) return;
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
          const data = await getPosts(params);
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
          const data = await getFanCards(params);
          content = renderFanCardList(data, {onOpen: (id, month) => void loadFancard(id, month)});
        } else {
          let profile = heroProfile;
          if (creator.profile_available && profileVersion !== null) {
            profile = await getCreatorProfile(creatorId, profileVersion);
          }
          const versionSelect = profile ? customSelect({id: "profile-version", label: "Profile 版本", value: profile.version,
            options: profile.versions.map(item => ({value: item.number,
              label: `v${String(item.number).padStart(4, "0")} · ${formatDate(item.captured_at)}`})),
            onChange: value => void loadCreator(creatorId, "profile", Number(value))}) : null;
          content = renderCreatorProfile(creator, profile, versionSelect);
        }
        if (requestNumber !== creatorRequest || state.creatorId !== creatorId || state.creatorTab !== tab) return;
        contentRoot.replaceChildren(content);
      } catch (error) {
        if (requestNumber !== creatorRequest || state.creatorId !== creatorId) return;
        errorView(error);
      }
    }

    async function loadFancard(
      creatorId: string, month: string, version: number | null = null,
    ): Promise<void> {
      const creatorContent = state.view === "creator"
        ? app.querySelector<HTMLElement>(".creator-content") : null;
      const target = creatorContent ?? app;
      target.replaceChildren(h("p", {class: "empty"}, "正在讀取粉絲卡…"));
      try {
        const card = await getFanCard(creatorId, month, version);
        state.current = {type: "fancard", creatorId, month};
        const versionSelect = customSelect({id: "fancard-version", label: "版本", value: card.version,
          options: card.versions.map(item => ({value: item.number,
            label: `v${String(item.number).padStart(4, "0")} · ${formatDate(item.captured_at)}`})),
          onChange: value => void loadFancard(creatorId, month, Number(value))});
        target.replaceChildren(renderFanCardReader(card, {
          onBack: () => void loadCreator(creatorId, "fancards"), versionSelect,
        }));
      } catch (error) {
        errorView(error);
      }
    }

    async function showJob(jobId: string, creators: CreatorSummary[]): Promise<void> {
      try {
        state.backupScreen = "job";
        state.backupJobId = jobId;
        renderJob(await getJob(jobId), creators);
      } catch (error) {
        errorView(error);
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
        onSignIn: () => setView("settings"),
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
      state.current = null;
      if (showLoading) app.replaceChildren(h("p", {class: "empty"}, "正在讀取工作狀態…"));
      try {
        const [creatorData, jobData, settings, auth] = await Promise.all([
          getCreators(), getJobs(historyParams("backup", state.jobPage, state.jobOrder, state.jobFilter)),
          getSettings(), getAuthStatus(sessionToken),
        ]);
        updateActiveJob(jobData);
        const active = jobData.active?.kind === "backup" ? jobData.active : null;
        if (active) {
          state.backupScreen = "job";
          state.backupJobId = active.job_id;
          renderJob(await getJob(active.job_id), creatorData.items);
        } else if (state.backupScreen === "job" && state.backupJobId) {
          const selected = await getJob(state.backupJobId).catch(() => null);
          if (selected) renderJob(selected, creatorData.items);
          else { state.backupScreen = "form"; state.backupJobId = null; renderBackupForm(creatorData.items, settings, auth); }
        } else if (state.backupScreen === "history") renderBackupHistory(creatorData.items, jobData);
        else renderBackupForm(creatorData.items, settings, auth);
      } catch (error) {
        errorView(error);
      }
    }

    async function startBackup(
      creators: string[], dryRun: boolean, maxPosts: number,
      mode: "full" | "profile" | "fancard" = "full",
      includeProfile = true, includeFancard = true,
    ): Promise<void> {
      try {
        const job = await startBackupJob({creators, dry_run: dryRun, max_posts: maxPosts, mode,
          include_profile: includeProfile, include_fancard: includeFancard}, sessionToken);
        state.backupScreen = "job";
        state.backupJobId = job.job_id;
        await renderJobWithActive(job);
      } catch (error) {
        errorView(error);
      }
    }

    async function renderJobWithActive(job: WebJob): Promise<void> {
      const [creatorData, jobData] = await Promise.all([getCreators(), getJobs()]);
      updateActiveJob(jobData);
      renderJob(job, creatorData.items);
    }

    async function cancelBackupJob(jobId: string): Promise<void> {
      try {
        await renderJobWithActive(await cancelJob(jobId, sessionToken));
      } catch (error) {
        errorView(error);
      }
    }

    async function retryBackupJob(jobId: string): Promise<void> {
      try {
        await renderJobWithActive(await retryJob(jobId, sessionToken));
      } catch (error) {
        errorView(error);
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
      state.current = null;
      if (showLoading) app.replaceChildren(h("p", {class: "empty"}, "正在讀取驗證狀態…"));
      try {
        const [history, newest] = await Promise.all([
          getJobs(historyParams("verify", state.verifyPage, state.verifyOrder)),
          getJobs(historyParams("verify", 1, "desc")),
        ]);
        updateActiveJob(history);
        // Show the running verification, else the one the user picked, else the newest result.
        const selectedId = (history.active?.kind === "verify" ? history.active.job_id : null)
          ?? state.verifyJobId ?? newest.items[0]?.job_id ?? null;
        const selected = selectedId ? await getJob(selectedId).catch(() => null) : null;
        renderMaintenance(selected, history);
      } catch (error) {
        errorView(error);
      }
    }

    async function startVerification(): Promise<void> {
      try {
        const job = await startVerificationJob(sessionToken);
        state.verifyJobId = job.job_id;
        const history = await getJobs(historyParams("verify", state.verifyPage, state.verifyOrder));
        updateActiveJob(history);
        renderMaintenance(job, history);
      } catch (error) {
        errorView(error);
      }
    }

    async function loadSettings(message = "", showLoading = true): Promise<void> {
      state.current = null;
      if (showLoading) app.replaceChildren(h("p", {class: "empty"}, "正在讀取設定…"));
      try {
        const [data, jobData, auth] = await Promise.all([getSettings(), getJobs(), getAuthStatus(sessionToken)]);
        updateActiveJob(jobData);
        app.replaceChildren(renderSettingsPage(data, auth, message, state.activeJob,
          patch => saveSettingsForm(patch),
          () => void loadSettings("", false),
          () => authAction(async () => { await startAuthLogin(sessionToken); },
            "登入視窗已開啟；請在專用 Chrome 中完成登入。"),
          jobId => authAction(async () => { await cancelAuthLogin(jobId, sessionToken); },
            "正在取消登入…"),
          () => authAction(async () => { await logoutAuth(sessionToken); },
            "已安全登出；封存與設定均未變更。")));
        scheduleJobRefresh();
      } catch (error) {
        errorView(error);
      }
    }

    async function authAction(action: () => Promise<void>, message: string): Promise<string | null> {
      try {
        await action();
        void loadSettings(message, false);
        return null;
      } catch (error) {
        return error instanceof Error ? error.message : String(error);
      }
    }

    async function saveSettingsForm(patch: SettingsPatch): Promise<string | null> {
      try {
        await saveSettings(patch, sessionToken);
        void loadSettings("設定已安全寫入；後續新工作會使用更新後的值。日誌處理器變更會在重新啟動後完整套用。");
        return null;
      } catch (error) {
        return error instanceof Error ? error.message : String(error);
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
      state.q = "";
      search.value = "";
      setView(view as View);
    });
    window.addEventListener("popstate", event => {
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
    setView("posts");
  }
}

if (typeof document !== "undefined" && document.getElementById("app")) FanboxUI.startApp();
