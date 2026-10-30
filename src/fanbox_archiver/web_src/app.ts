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

    function updateActiveJob(jobs: WebJob[]): WebJob | null {
      state.activeJob = jobs.find(isActiveJob) ?? null;
      return state.activeJob;
    }

    function scheduleJobRefresh(): void {
      if (jobTimer !== undefined) clearTimeout(jobTimer);
      if (state.activeJob && ["backup", "maintenance", "settings"].includes(state.view)) {
        jobTimer = window.setTimeout(() => void refreshView(false), 900);
      }
    }

    async function loadPosts(): Promise<void> {
      state.current = null;
      app.replaceChildren(h("p", {class: "empty"}, "正在讀取投稿…"));
      try {
        const params = new URLSearchParams({page: String(state.page), page_size: "50"});
        if (state.q) params.set("q", state.q);
        const data = await getPosts(params);
        app.replaceChildren(renderPostListPage(data, {
          onOpen: postId => void loadPost(postId),
          onPage: page => { state.page = page; void loadPosts(); },
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
        const params = new URLSearchParams();
        if (version !== null) params.set("version", String(version));
        if (creatorContent && creatorId) params.set("creator", creatorId);
        if (state.q) params.set("q", state.q);
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
          const params = new URLSearchParams({creator: creatorId, page: String(state.page), page_size: "50"});
          if (state.q) params.set("q", state.q);
          const data = await getPosts(params);
          content = renderCreatorPostList(data, {
            onOpen: postId => void loadPost(postId),
            onPage: page => { state.page = page; void loadCreator(creatorId, "posts"); },
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

    async function showJob(jobId: string, creators: CreatorSummary[], jobs: WebJob[]): Promise<void> {
      try {
        state.backupScreen = "job";
        state.backupJobId = jobId;
        renderJob(await getJob(jobId), creators, jobs);
      } catch (error) {
        errorView(error);
      }
    }

    function renderJob(job: WebJob, creators: CreatorSummary[], jobs: WebJob[] = [job]): void {
      if (jobTimer !== undefined) clearTimeout(jobTimer);
      const active = isActiveJob(job);
      const page = renderBackupJobPage(job, creators, jobs, state.jobFilter, state.activeJob, {
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
      const currentPage = app.querySelector<HTMLElement>(".backup-page[data-job-id]");
      if (currentPage?.dataset.jobId === job.job_id) updateJobPage(currentPage, page, active);
      else app.replaceChildren(page);
      scheduleJobRefresh();
    }

    function renderBackupForm(creators: CreatorSummary[], settings: SettingsResponse): void {
      const value = settings.editable;
      app.replaceChildren(renderBackupFormPage(creators, {
        dryRun: value.backup_defaults.dry_run,
        includeProfile: value.backup_defaults.include_profile,
        includeFancard: value.backup_defaults.include_fancard,
        maxPosts: value.sync.max_posts_per_run,
      }, state.activeJob, {
        onStart: (creators, dryRun, maxPosts, mode, includeProfile, includeFancard) =>
          void startBackup(creators, dryRun, maxPosts, mode, includeProfile, includeFancard),
        onHistory: () => { state.backupScreen = "history"; void loadBackup(false); },
      }));
      scheduleJobRefresh();
    }

    function renderBackupHistory(creators: CreatorSummary[], jobs: WebJob[]): void {
      app.replaceChildren(renderBackupHistoryPage(jobs, creators, state.jobFilter, {
        onNew: () => { state.backupScreen = "form"; void loadBackup(false); },
        onShow: jobId => void showJob(jobId, creators, jobs),
        onFilter: value => { state.jobFilter = value; renderBackupHistory(creators, jobs); },
      }));
    }

    async function loadBackup(showLoading = true): Promise<void> {
      state.current = null;
      if (showLoading) app.replaceChildren(h("p", {class: "empty"}, "正在讀取工作狀態…"));
      try {
        const [creatorData, jobData, settings] = await Promise.all([getCreators(), getJobs(), getSettings()]);
        updateActiveJob(jobData.items);
        const backupJobs = jobData.items.filter(item => item.kind === "backup");
        const active = backupJobs.find(isActiveJob);
        if (active) {
          state.backupScreen = "job";
          state.backupJobId = active.job_id;
          renderJob(await getJob(active.job_id), creatorData.items, backupJobs);
        } else if (state.backupScreen === "job" && state.backupJobId) {
          const selected = backupJobs.find(item => item.job_id === state.backupJobId);
          if (selected) renderJob(await getJob(selected.job_id), creatorData.items, backupJobs);
          else { state.backupScreen = "form"; state.backupJobId = null; renderBackupForm(creatorData.items, settings); }
        } else if (state.backupScreen === "history") renderBackupHistory(creatorData.items, backupJobs);
        else renderBackupForm(creatorData.items, settings);
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
        const [creatorData, jobData] = await Promise.all([getCreators(), getJobs()]);
        updateActiveJob(jobData.items);
        renderJob(job, creatorData.items, jobData.items.filter(item => item.kind === "backup"));
      } catch (error) {
        errorView(error);
      }
    }

    async function cancelBackupJob(jobId: string): Promise<void> {
      try {
        const job = await cancelJob(jobId, sessionToken);
        const [creatorData, jobData] = await Promise.all([getCreators(), getJobs()]);
        updateActiveJob(jobData.items);
        renderJob(job, creatorData.items, jobData.items.filter(item => item.kind === "backup"));
      } catch (error) {
        errorView(error);
      }
    }

    async function retryBackupJob(jobId: string): Promise<void> {
      try {
        const job = await retryJob(jobId, sessionToken);
        const [creatorData, jobData] = await Promise.all([getCreators(), getJobs()]);
        updateActiveJob(jobData.items);
        renderJob(job, creatorData.items, jobData.items.filter(item => item.kind === "backup"));
      } catch (error) {
        errorView(error);
      }
    }

    function renderMaintenance(job: WebJob | null = null, jobs: WebJob[] = []): void {
      if (jobTimer !== undefined) clearTimeout(jobTimer);
      app.replaceChildren(renderMaintenancePage(job, jobs, state.activeJob, {
        onStart: () => void startVerification(),
        onShow: jobId => void showVerification(jobId, jobs),
      }));
      scheduleJobRefresh();
    }

    async function loadMaintenance(showLoading = true): Promise<void> {
      state.current = null;
      if (showLoading) app.replaceChildren(h("p", {class: "empty"}, "正在讀取驗證狀態…"));
      try {
        const data = await getJobs();
        updateActiveJob(data.items);
        const jobs = data.items.filter(item => item.kind === "verify");
        const selected = jobs.find(isActiveJob) ?? jobs[0];
        renderMaintenance(selected ? await getJob(selected.job_id) : null, jobs);
      } catch (error) {
        errorView(error);
      }
    }

    async function startVerification(): Promise<void> {
      try {
        const job = await startVerificationJob(sessionToken);
        const data = await getJobs();
        updateActiveJob(data.items);
        renderMaintenance(job, data.items.filter(item => item.kind === "verify"));
      } catch (error) {
        errorView(error);
      }
    }

    async function showVerification(jobId: string, jobs: WebJob[]): Promise<void> {
      try {
        renderMaintenance(await getJob(jobId), jobs);
      } catch (error) {
        errorView(error);
      }
    }

    async function loadSettings(message = "", showLoading = true): Promise<void> {
      state.current = null;
      if (showLoading) app.replaceChildren(h("p", {class: "empty"}, "正在讀取設定…"));
      try {
        const [data, jobData] = await Promise.all([getSettings(), getJobs()]);
        updateActiveJob(jobData.items);
        app.replaceChildren(renderSettingsPage(data, message, state.activeJob,
          patch => saveSettingsForm(patch)));
        scheduleJobRefresh();
      } catch (error) {
        errorView(error);
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
