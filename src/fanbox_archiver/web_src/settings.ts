namespace FanboxUI {
  interface InputControl {
    input: HTMLInputElement;
    node: HTMLElement;
  }

  function settingCheckbox(label: string, checked: boolean): InputControl {
    const input = h("input", {type: "checkbox", checked}) as HTMLInputElement;
    return {input, node: h("label", {class: "setting-toggle"}, input, h("span", {}, label))};
  }

  function settingNumber(
    label: string, value: number, min: number, max: number, step = 1, hint: string | null = null,
  ): InputControl {
    const input = h("input", {type: "number", value, min, max, step}) as HTMLInputElement;
    return {input, node: h("label", {class: "setting-field"}, h("span", {}, label), input,
      hint ? h("small", {}, hint) : null)};
  }

  const OTHER_TIMEZONE = "__other__";

  /** Timezone picker: computer system first, then common zones, then a searchable full list. */
  function timezoneControl(data: SettingsResponse, blocked: boolean): {node: HTMLElement; read(): string} {
    const setting = data.editable.display.timezone;
    const common = data.timezones.common;
    const custom = setting !== "system" && !common.includes(setting);
    let choice = custom ? OTHER_TIMEZONE : setting;
    const listId = `timezone-list-${Math.random().toString(36).slice(2, 9)}`;
    const other = h("input", {type: "text", value: custom ? setting : "", list: listId, spellcheck: "false",
      placeholder: "例如 Asia/Tokyo", "aria-label": "其他時區（IANA 名稱）", autocomplete: "off"}) as HTMLInputElement;
    const otherField = h("label", {class: "setting-field timezone-other", hidden: !custom},
      h("span", {}, "其他時區（輸入以搜尋）"), other,
      h("datalist", {id: listId}, data.timezones.all.map(name => h("option", {value: name}))));
    const select = customSelect({id: "display-timezone", label: "時區", value: choice, disabled: blocked,
      options: [{value: "system", label: `電腦系統（目前：${data.display.system_timezone}）`},
        ...common.map(name => ({value: name, label: name})), {value: OTHER_TIMEZONE, label: "其他時區…"}],
      onChange: next => { choice = next; otherField.hidden = next !== OTHER_TIMEZONE; if (!otherField.hidden) other.focus(); }});
    const node = h("section", {class: "settings-section"}, h("h3", {}, "時區"),
      h("p", {class: "settings-section-description"},
        `所有時間以 24 小時制、依此時區顯示，自動備份的時間也依此解讀；切換不會改寫已保存的資料。目前生效：${data.display.timezone}`),
      data.display.notice ? h("p", {class: "notice"}, data.display.notice) : null,
      h("div", {class: "settings-grid two-columns"}, h("div", {class: "setting-field"}, h("span", {}, "時區"), select), otherField));
    return {node, read: () => choice === OTHER_TIMEZONE ? other.value.trim() : choice};
  }

  const THEME_LABELS: Record<ThemeSetting, string> = {
    system: "跟隨系統（Windows 深淺色）", dark: "暗色", light: "亮色",
  };

  /** Applies a theme to this page the same way the server does on load (the static site calls "system" "auto"). */
  export function applyTheme(theme: ThemeSetting): void {
    document.documentElement.dataset.theme = theme === "system" ? "auto" : theme;
  }

  function themeControl(data: SettingsResponse, blocked: boolean): {node: HTMLElement; read(): ThemeSetting} {
    let choice: ThemeSetting = data.editable.display.theme;
    const select = customSelect({id: "display-theme", label: "主題", value: choice, disabled: blocked,
      options: (Object.keys(THEME_LABELS) as ThemeSetting[]).map(value => ({value, label: THEME_LABELS[value]})),
      onChange: next => { choice = next as ThemeSetting; applyTheme(choice); }});
    const node = h("section", {class: "settings-section"}, h("h3", {}, "主題"),
      h("p", {class: "settings-section-description"},
        "選擇後立即預覽，儲存後套用到動態閱讀器、桌面程式，以及之後匯出的靜態網站（靜態網站上仍可自行切換）。"),
      h("div", {class: "settings-grid two-columns"}, h("div", {class: "setting-field"}, h("span", {}, "主題"), select)));
    return {node, read: () => choice};
  }

  // Language names are shown in their own language. The pseudo-locale is listed only while
  // config.yaml selects it, so saving the form never silently switches it off.
  const LANGUAGE_LABELS: Record<LanguageSetting, string> = {
    auto: "跟隨系統", "zh-Hant": "繁體中文", "qps-ploc": "測試語系（Pseudo，僅限 config.yaml）",
  };

  function languageControl(data: SettingsResponse, blocked: boolean): {node: HTMLElement; read(): LanguageSetting} {
    let choice: LanguageSetting = data.editable.display.language;
    const values: LanguageSetting[] = choice === "qps-ploc" ? ["auto", "zh-Hant", "qps-ploc"] : ["auto", "zh-Hant"];
    const select = customSelect({id: "display-language", label: "介面語言", value: choice, disabled: blocked,
      options: values.map(value => ({value, label: LANGUAGE_LABELS[value]})),
      onChange: next => { choice = next as LanguageSetting; }});
    const node = h("section", {class: "settings-section"}, h("h3", {}, "介面語言"),
      h("p", {class: "settings-section-description"},
        `目前提供繁體中文；「跟隨系統」找不到支援的語言時使用繁體中文。投稿、創作者名稱與標籤等封存內容不會翻譯。儲存後重新整理頁面套用。目前生效：${currentLocale()}`),
      h("div", {class: "settings-grid two-columns"}, h("div", {class: "setting-field"}, h("span", {}, "介面語言"), select)));
    return {node, read: () => choice};
  }

  export interface AboutSectionActions {
    onOpen: (target: FolderTarget) => Promise<string | null>;
  }

  async function copyText(text: string): Promise<boolean> {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // Fall back to a temporary selection when the clipboard API is unavailable.
      const area = h("textarea", {readonly: true, class: "visually-hidden"}) as HTMLTextAreaElement;
      area.value = text;
      document.body.append(area);
      area.select();
      const copied = document.execCommand("copy");
      area.remove();
      return copied;
    }
  }

  /** Versions, locations and safe folder shortcuts; never shows cookies or sign-in data. */
  function renderAboutSection(info: DiagnosticsInfo | null, actions: AboutSectionActions): HTMLElement {
    const card = h("section", {class: "settings-card about-card"},
      h("p", {class: "eyebrow"}, "ABOUT & DIAGNOSTICS"), h("h2", {}, "關於與診斷"));
    if (!info) {
      card.append(h("p", {class: "notice"}, "無法讀取診斷資訊；重新整理後再試一次。"));
      return card;
    }
    const feedback = h("p", {class: "about-feedback", role: "status", "aria-live": "polite"});
    const show = (text: string, error = false): void => {
      feedback.textContent = text;
      feedback.classList.toggle("settings-error", error);
    };
    const schema = info.schema.database === null ? `無法讀取（程式支援 ${info.schema.supported}）`
      : `${info.schema.database}（程式支援 ${info.schema.supported}）`;
    const rows: [string, string][] = [
      ["程式版本", info.app_version],
      ["執行方式", info.mode === "desktop" ? `桌面版 ${info.desktop_version ?? "（版本不明）"}` : "瀏覽器版"],
      ["資料庫 schema", schema],
      ["Python", info.python_version],
      ["作業系統", info.os],
      ["時區", info.timezone],
      ["設定檔", info.paths.config ?? "未指定"],
      ["封存目錄", info.paths.archive],
      ["資料庫", info.paths.database],
      ["封存日誌", info.paths.archive_logs],
    ];
    if (info.paths.desktop_logs) rows.push(["桌面日誌", info.paths.desktop_logs]);
    const folderButton = (target: FolderTarget, label: string, missing: string): HTMLElement => {
      const available = info.can_open_folders && info.folders[target];
      return h("button", {type: "button", disabled: !available,
        title: !info.can_open_folders ? "此系統無法開啟資料夾" : info.folders[target] ? "" : missing,
        onclick: async (event: Event) => {
          const button = event.currentTarget as HTMLButtonElement;
          button.disabled = true;
          const error = await actions.onOpen(target);
          button.disabled = false;
          show(error ? `無法開啟資料夾：${error}` : `已開啟「${label.replace("開啟", "")}」。`, Boolean(error));
        }}, label);
    };
    card.append(
      h("p", {class: "settings-section-description"},
        "回報問題時可附上下方的診斷資訊；其中不含 Cookie、帳號或登入資料。"),
      h("div", {class: "settings-paths about-facts"},
        rows.map(([label, value]) => h("div", {}, h("span", {}, label), h("code", {}, value)))),
      h("div", {class: "account-actions about-actions"},
        folderButton("archive", "開啟封存資料夾", "封存資料夾不存在"),
        folderButton("archive_logs", "開啟封存日誌資料夾", "尚未產生日誌（需啟用「寫入檔案日誌」）"),
        info.paths.desktop_logs ? folderButton("desktop_logs", "開啟桌面日誌資料夾", "尚未產生桌面日誌") : null,
        h("button", {type: "button", onclick: async () => {
          show(await copyText(info.text) ? "診斷資訊已複製到剪貼簿。" : "無法複製；請手動選取上方文字。",
            false);
        }}, "複製診斷資訊")),
      feedback);
    return card;
  }

  export const SETTINGS_TABS: {id: SettingsTab; label: string}[] = [
    {id: "account", label: "帳號與登入"},
    {id: "general", label: "一般"},
    {id: "backup", label: "備份"},
    {id: "theme", label: "主題"},
    {id: "about", label: "關於與診斷"},
  ];

  export function isSettingsTab(value: unknown): value is SettingsTab {
    return SETTINGS_TABS.some(tab => tab.id === value);
  }

  export interface AccountActions {
    onRefresh(): void;
    onLogin(): Promise<string | null>;
    onCancel(jobId: string): Promise<string | null>;
    onLogout(): Promise<string | null>;
  }

  export interface SettingsPageContext {
    data: SettingsResponse;
    tab: SettingsTab;
    message: string;
    activeJob: WebJob | null;
    onTab(tab: SettingsTab): void;
    /** Saves only the fields of the current sub-page; resolves an error message or null. */
    onSave(patch: SettingsSavePatch): Promise<string | null>;
    /** Account tab: null until the (slow) sign-in check answers. */
    auth?: AuthStatus | null;
    account?: AccountActions;
    schedule?: {status: ScheduleStatus; creators: CreatorSummary[]; actions: ScheduleSectionActions};
    about?: {info: DiagnosticsInfo | null; actions: AboutSectionActions};
  }

  export interface SettingsPageHandle {
    node: HTMLElement;
    /** True while the current sub-page has edits that are not saved. */
    isDirty(): boolean;
    /** Locks or unlocks editing for a job without redrawing (keeps unsaved input). */
    setLocked(activeJob: WebJob | null): void;
    /** Account tab: shows the sign-in check result once it arrives. */
    setAuth(auth: AuthStatus): void;
  }

  const AUTH_LABELS: Record<AuthState, string> = {checking: "檢查中", locked: "工作中", authenticated: "已登入",
    signed_out: "未登入", expired: "已失效", error: "檢查失敗"};

  function renderAccountCard(auth: AuthStatus | null, blocked: boolean, actions: AccountActions): HTMLElement {
    if (!auth) {
      // Shown at once; the check can take a while (it may start the dedicated browser).
      return h("section", {class: "settings-card account-card tone-neutral", "aria-busy": "true"},
        h("div", {class: "account-heading"}, h("div", {}, h("p", {class: "eyebrow"}, "ACCOUNT & SIGN-IN"),
          h("h2", {}, "帳號／登入")), h("span", {class: "auth-badge neutral"}, "檢查中")),
        h("p", {class: "account-message", role: "status", "aria-live": "polite"}, "正在檢查登入狀態…"));
    }
    const authBusy = auth.state === "checking";
    const authLocked = auth.state === "locked";
    const authTone = auth.state === "authenticated" ? "success"
      : auth.state === "expired" || auth.state === "error" ? "error" : "neutral";
    const lastKnown = authLocked && auth.last_known
      ? `上次檢查：${AUTH_LABELS[auth.last_known.state]}（${formatDate(auth.last_known.checked_at)}）` : null;
    const authFeedback = h("p", {class: "settings-error", role: "alert", hidden: true});
    const runAuth = async (action: () => Promise<string | null>): Promise<void> => {
      authFeedback.hidden = true;
      const error = await action();
      if (error) { authFeedback.textContent = error; authFeedback.hidden = false; }
    };
    return h("section", {class: `settings-card account-card tone-${authTone}`},
      h("div", {class: "account-heading"}, h("div", {}, h("p", {class: "eyebrow"}, "ACCOUNT & SIGN-IN"),
        h("h2", {}, "帳號／登入")), h("span", {class: `auth-badge ${authTone}`}, AUTH_LABELS[auth.state])),
      h("p", {class: "account-message", role: "status", "aria-live": "polite"}, auth.message),
      lastKnown ? h("p", {class: "account-last-known"}, lastKnown) : null,
      h("p", {class: "settings-section-description"}, auth.source === "profile"
        ? "認證來源：FANBOX Archiver 專用瀏覽器工作階段"
        : auth.source === "environment" ? "認證來源：外部環境 FANBOX_COOKIE"
        : "尚無認證來源"),
      auth.externally_managed ? h("p", {class: "auth-external-notice"},
        "此登入由啟動環境管理，應用程式無法撤銷；請更新或移除 FANBOX_COOKIE 後重新啟動。") : null,
      h("div", {class: "account-actions"},
        h("button", {type: "button", class: "primary", disabled: blocked || authLocked || authBusy || !auth.can_login,
          onclick: () => void runAuth(actions.onLogin)}, "登入 FANBOX"),
        h("button", {type: "button", disabled: blocked || authLocked || authBusy, onclick: actions.onRefresh}, "重新檢查"),
        authBusy && auth.job ? h("button", {type: "button", class: "danger-outline",
          onclick: () => void runAuth(() => actions.onCancel(auth.job!.job_id))}, "取消登入") : null,
        h("button", {type: "button", class: "danger-outline",
          disabled: blocked || authLocked || authBusy || !auth.can_logout,
          onclick: async () => {
            const confirmed = await confirmDialog({
              title: "登出 FANBOX？", message: "將清除專用 FANBOX 工作階段；封存與設定不會被刪除。",
              cancelLabel: "取消", confirmLabel: "登出", danger: true,
            });
            if (confirmed) void runAuth(actions.onLogout);
          }}, "登出"), authFeedback));
  }

  interface EditablePage {
    content: HTMLElement[];
    fields: TrackedField[];
    patch(): SettingsSavePatch;
    onDirty?(dirty: boolean): void;
    onLocked?(locked: boolean): void;
  }

  function generalPage(data: SettingsResponse, blocked: boolean): EditablePage {
    const value = data.editable;
    const language = languageControl(data, blocked);
    const timezone = timezoneControl(data, blocked);
    const markdown = settingCheckbox("產生 Markdown", value.markdown.enabled);
    const frontMatter = settingCheckbox("加入 YAML front matter", value.markdown.yaml_front_matter);
    const relativePaths = settingCheckbox("Markdown 使用相對圖片路徑", value.markdown.relative_image_paths);
    const preserveOrder = settingCheckbox("保留原始內容順序", value.markdown.preserve_original_order);
    const logLevel = customSelect({id: "log-level", label: "日誌等級", value: value.logging.level, disabled: blocked,
      options: ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"].map(item => ({value: item, label: item}))});
    const logLevelField = h("div", {class: "setting-field"}, h("span", {}, "日誌等級"), logLevel);
    const keepDays = settingNumber("日誌保留天數", value.logging.keep_days, 1, 365);
    const fileLogs = settingCheckbox("寫入檔案日誌", value.logging.write_to_file);
    const checked = (control: InputControl): TrackedField => ({node: control.node, read: () => control.input.checked});
    return {
      content: [h("section", {class: "settings-card"}, h("p", {class: "eyebrow"}, "GENERAL"), h("h2", {}, "一般"),
        language.node, timezone.node,
        h("section", {class: "settings-section"}, h("h3", {}, "Markdown"),
          h("div", {class: "setting-toggles"}, markdown.node, frontMatter.node, relativePaths.node, preserveOrder.node)),
        h("section", {class: "settings-section"}, h("h3", {}, "日誌"),
          h("div", {class: "settings-grid two-columns"}, logLevelField, keepDays.node),
          h("div", {class: "setting-toggles"}, fileLogs.node)))],
      fields: [
        {node: language.node, read: language.read}, {node: timezone.node, read: timezone.read},
        checked(markdown), checked(frontMatter), checked(relativePaths), checked(preserveOrder),
        {node: logLevelField, read: () => logLevel.value}, {node: keepDays.node, read: () => keepDays.input.value},
        checked(fileLogs),
      ],
      patch: () => ({
        display: {timezone: timezone.read(), language: language.read()},
        markdown: {enabled: markdown.input.checked, yaml_front_matter: frontMatter.input.checked,
          relative_image_paths: relativePaths.input.checked, preserve_original_order: preserveOrder.input.checked},
        logging: {level: logLevel.value, write_to_file: fileLogs.input.checked, keep_days: Number(keepDays.input.value)},
      }),
    };
  }

  function themePage(data: SettingsResponse, blocked: boolean): EditablePage {
    const theme = themeControl(data, blocked);
    const colors = colorEditor(data);
    return {
      content: [h("section", {class: "settings-card"}, h("p", {class: "eyebrow"}, "THEME"), h("h2", {}, "主題"),
        theme.node, colors.node)],
      fields: [{node: theme.node, read: theme.read}, {node: colors.node, read: colors.read}],
      patch: () => ({display: {theme: theme.read(), colors: colors.read()}}),
    };
  }

  function backupPage(
    data: SettingsResponse, blocked: boolean,
    schedule: NonNullable<SettingsPageContext["schedule"]>,
  ): EditablePage {
    const value = data.editable;
    const maxPosts = settingNumber(
      "單次最多下載投稿數", value.sync.max_posts_per_run, 1, 100, 1,
      "new、updated 與 retry 共用的下載配額；略過的投稿不占配額。新工作可單次覆寫。",
    );
    const unchangedStop = settingNumber(
      "連續未變投稿停止掃描數", value.sync.recent_unchanged_stop_count, 1, 500, 1,
      "連續遇到已完成且未更新投稿時停止掃描；這不是下載數量。",
    );
    const defaultDryRun = settingCheckbox("完整備份只預覽，不下載", value.backup_defaults.dry_run);
    const defaultProfile = settingCheckbox("預設拉取個人資料", value.backup_defaults.include_profile);
    const defaultFancard = settingCheckbox("預設拉取粉絲卡", value.backup_defaults.include_fancard);
    const originalImages = settingCheckbox("下載原始圖片", value.download.original_images);
    const attachments = settingCheckbox("下載附件", value.download.download_attachments);
    const covers = settingCheckbox("下載投稿與 Profile 封面", value.download.download_cover);
    const resume = settingCheckbox("支援續傳", value.download.resume);
    const hashes = settingCheckbox("下載後驗證 SHA-256", value.download.verify_sha256);
    const preserveDeleted = settingCheckbox("保留遠端已刪除投稿的本機備份", value.sync.preserve_deleted_posts);
    const skipCompleted = settingCheckbox("略過已完成且未更新的投稿", value.sync.skip_completed);
    const checkUpdates = settingCheckbox("檢查遠端更新", value.sync.check_updates);
    const rotate = settingCheckbox("輪替創作者處理順序", value.sync.rotate_creators);
    const retries = settingNumber("失敗重試次數", value.download.retry_count, 0, 10);
    const interval = settingNumber("請求間隔（秒）", value.download.request_interval_seconds, 1, 3600, .5,
      "最低 1 秒；提高此值可降低請求頻率。");
    const timeout = settingNumber("請求逾時（秒）", value.download.timeout_seconds, 5, 600);
    const scheduleSection = renderScheduleSection(value.schedule, schedule.status, schedule.creators, blocked,
      schedule.actions);
    const checked = (control: InputControl): TrackedField => ({node: control.node, read: () => control.input.checked});
    const number = (control: InputControl): TrackedField => ({node: control.node, read: () => control.input.value});
    return {
      content: [h("section", {class: "settings-card backup-settings"}, h("p", {class: "eyebrow"}, "BACKUP"), h("h2", {}, "備份"),
        h("section", {class: "settings-section"}, h("h3", {}, "工作數量與掃描停止"),
          h("p", {class: "settings-section-description"}, "下載配額與掃描停止門檻是兩個不同概念。"),
          h("div", {class: "settings-grid two-columns"}, maxPosts.node, unchangedStop.node)),
        h("section", {class: "settings-section"}, h("h3", {}, "新工作預設"),
          h("p", {class: "settings-section-description"}, "每次進入新工作表單時套用；重試仍沿用原工作設定。"),
          h("div", {class: "setting-toggles"}, defaultDryRun.node, defaultProfile.node, defaultFancard.node)),
        scheduleSection.node,
        h("section", {class: "settings-section"}, h("h3", {}, "內容與保存"),
          h("div", {class: "setting-toggles"}, originalImages.node, attachments.node, covers.node, resume.node, hashes.node, preserveDeleted.node)),
        h("section", {class: "settings-section"}, h("h3", {}, "更新判定與處理順序"),
          h("div", {class: "setting-toggles"}, skipCompleted.node, checkUpdates.node, rotate.node)),
        h("section", {class: "settings-section"}, h("h3", {}, "網路與失敗處理"),
          h("div", {class: "settings-grid"}, retries.node, interval.node, timeout.node)))],
      fields: [
        number(maxPosts), number(unchangedStop), checked(defaultDryRun), checked(defaultProfile), checked(defaultFancard),
        ...scheduleSection.fields,
        checked(originalImages), checked(attachments), checked(covers), checked(resume), checked(hashes),
        checked(preserveDeleted), checked(skipCompleted), checked(checkUpdates), checked(rotate),
        number(retries), number(interval), number(timeout),
      ],
      patch: () => ({
        download: {
          original_images: originalImages.input.checked, download_attachments: attachments.input.checked,
          download_cover: covers.input.checked, resume: resume.input.checked, verify_sha256: hashes.input.checked,
          retry_count: Number(retries.input.value), request_interval_seconds: Number(interval.input.value),
          timeout_seconds: Number(timeout.input.value),
        },
        sync: {
          skip_completed: skipCompleted.input.checked, check_updates: checkUpdates.input.checked,
          preserve_deleted_posts: preserveDeleted.input.checked, rotate_creators: rotate.input.checked,
          max_posts_per_run: Number(maxPosts.input.value),
          recent_unchanged_stop_count: Number(unchangedStop.input.value),
        },
        backup_defaults: {
          dry_run: defaultDryRun.input.checked, include_profile: defaultProfile.input.checked,
          include_fancard: defaultFancard.input.checked,
        },
        schedule: scheduleSection.read(),
      }),
      // "Run now" uses the saved schedule, so it waits until edits are saved or discarded.
      onDirty: dirty => scheduleSection.setRunBlocked(dirty ? "請先儲存或放棄未儲存的變更，再立即執行。" : null),
      onLocked: locked => scheduleSection.setLocked(locked),
    };
  }

  /** The settings page: sub-page tabs, then one sub-page, each saving only its own fields. */
  export function renderSettingsPage(ctx: SettingsPageContext): SettingsPageHandle {
    const {data, tab} = ctx;
    let blocked = Boolean(ctx.activeJob);
    const tabButtons = new Map<SettingsTab, HTMLButtonElement>();
    const tabs = h("nav", {class: "settings-tabs", "aria-label": "設定子頁面"},
      SETTINGS_TABS.map(item => {
        const button = h("button", {type: "button", "data-settings-tab": item.id,
          "aria-current": item.id === tab ? "page" : null, class: item.id === tab ? "active" : "",
          onclick: () => { if (item.id !== tab) ctx.onTab(item.id); }},
        h("span", {}, item.label)) as HTMLButtonElement;
        tabButtons.set(item.id, button);
        return button;
      }));
    const markTab = (dirty: boolean): void => {
      const button = tabButtons.get(tab);
      if (!button) return;
      button.querySelector(".tab-dirty")?.remove();
      if (dirty) button.append(h("span", {class: "tab-dirty"}, "未儲存"));
    };
    let notice = activeJobNotice(ctx.activeJob) ?? h("div", {hidden: true});
    const body = h("div", {class: "settings-body"});
    let tracker: DirtyTracker | null = null;
    let fieldset: HTMLFieldSetElement | null = null;
    let save: HTMLButtonElement | null = null;
    let lockNote: HTMLElement | null = null;
    let account: HTMLElement | null = null;
    let auth = ctx.auth ?? null;

    const editable: EditablePage | null = tab === "general" ? generalPage(data, blocked)
      : tab === "theme" ? themePage(data, blocked)
      : tab === "backup" && ctx.schedule ? backupPage(data, blocked, ctx.schedule) : null;

    if (editable) {
      const feedback = h("p", {class: "settings-error", role: "alert", hidden: true});
      save = h("button", {type: "submit", class: "primary", disabled: !data.writable || blocked}, "儲存設定") as HTMLButtonElement;
      lockNote = h("span", {class: "notice", hidden: !blocked}, "工作結束後即可儲存設定。");
      fieldset = h("fieldset", {disabled: blocked}, ...editable.content) as HTMLFieldSetElement;
      const form = h("form", {class: "settings-form", "aria-disabled": blocked, onsubmit: async (event: Event) => {
        event.preventDefault();
        if (blocked) return;
        feedback.hidden = true;
        save!.disabled = true;
        const error = await ctx.onSave(editable.patch());
        if (save!.isConnected) save!.disabled = !data.writable || blocked;
        if (error) {
          feedback.textContent = `儲存失敗：${error}`;
          feedback.hidden = false;
        }
      }},
      fieldset,
      h("div", {class: "settings-actions"}, save,
        !data.writable ? h("span", {class: "notice"}, "目前伺服器未指定可寫入的設定檔。") : null,
        lockNote, feedback));
      body.append(form);
      tracker = trackChanges(form, editable.fields, dirty => { markTab(dirty); editable.onDirty?.(dirty); });
    } else if (tab === "account" && ctx.account) {
      account = renderAccountCard(auth, blocked, ctx.account);
      body.append(account);
    } else if (tab === "about" && ctx.about) {
      body.append(renderAboutSection(ctx.about.info, ctx.about.actions));
    }

    const node = h("section", {class: "page settings-page"},
      h("header", {class: "heading"}, h("div", {}, h("p", {class: "eyebrow"}, "LOCAL SETTINGS"), h("h1", {}, "設定"),
        h("p", {}, "只顯示安全的一般選項；儲存與認證路徑維持唯讀。"))),
      tabs,
      ctx.message ? h("p", {class: "settings-saved", role: "status"}, ctx.message) : null,
      notice,
      body);
    // On narrow screens the tab row scrolls; keep the current sub-page's tab in view.
    requestAnimationFrame(() => tabButtons.get(tab)?.scrollIntoView({block: "nearest", inline: "nearest"}));

    return {
      node,
      isDirty: () => tracker?.isDirty() ?? false,
      setLocked: activeJob => {
        const next = Boolean(activeJob);
        const replacement = activeJobNotice(activeJob) ?? h("div", {hidden: true});
        notice.replaceWith(replacement);
        notice = replacement;
        if (next === blocked) return;
        blocked = next;
        if (fieldset) {
          fieldset.disabled = blocked;
          // Custom selects keep their own disabled flag (a <summary> ignores fieldset[disabled]).
          for (const select of fieldset.querySelectorAll<CustomSelectElement>(".custom-select")) select.disabled = blocked;
        }
        editable?.onLocked?.(blocked);
        if (save) save.disabled = !data.writable || blocked;
        if (lockNote) lockNote.hidden = !blocked;
        if (account && ctx.account) {
          const card = renderAccountCard(auth, blocked, ctx.account);
          account.replaceWith(card);
          account = card;
        }
      },
      setAuth: next => {
        auth = next;
        if (!account || !ctx.account) return;
        const card = renderAccountCard(auth, blocked, ctx.account);
        account.replaceWith(card);
        account = card;
      },
    };
  }
}
