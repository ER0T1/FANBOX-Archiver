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
      placeholder: t("settings.timezone_placeholder"), "aria-label": t("settings.timezone_other_aria"), autocomplete: "off"}) as HTMLInputElement;
    const otherField = h("label", {class: "setting-field timezone-other", hidden: !custom},
      h("span", {}, t("settings.timezone_other_search")), other,
      h("datalist", {id: listId}, data.timezones.all.map(name => h("option", {value: name}))));
    const select = customSelect({id: "display-timezone", label: t("settings.timezone"), value: choice, disabled: blocked,
      options: [{value: "system", label: t("settings.timezone_system", {zone: data.display.system_timezone})},
        ...common.map(name => ({value: name, label: name})), {value: OTHER_TIMEZONE, label: t("settings.timezone_other")}],
      onChange: next => { choice = next; otherField.hidden = next !== OTHER_TIMEZONE; if (!otherField.hidden) other.focus(); }});
    const node = h("section", {class: "settings-section"}, h("h3", {}, t("settings.timezone")),
      h("p", {class: "settings-section-description"},
        t("settings.timezone_description", {zone: data.display.timezone})),
      data.display.notice ? h("p", {class: "notice"}, data.display.notice) : null,
      h("div", {class: "settings-grid two-columns"}, h("div", {class: "setting-field"}, h("span", {}, t("settings.timezone")), select), otherField));
    return {node, read: () => choice === OTHER_TIMEZONE ? other.value.trim() : choice};
  }

  const THEMES: ThemeSetting[] = ["system", "dark", "light"];

  /** Applies a theme to this page the same way the server does on load ("system" is rendered as "auto"). */
  export function applyTheme(theme: ThemeSetting): void {
    document.documentElement.dataset.theme = theme === "system" ? "auto" : theme;
  }

  function themeControl(data: SettingsResponse, blocked: boolean): {node: HTMLElement; read(): ThemeSetting} {
    let choice: ThemeSetting = data.editable.display.theme;
    const select = customSelect({id: "display-theme", label: t("settings.theme"), value: choice, disabled: blocked,
      options: THEMES.map(value => ({value, label: t(`settings.theme_${value}`)})),
      onChange: next => { choice = next as ThemeSetting; applyTheme(choice); }});
    const node = h("section", {class: "settings-section"}, h("h3", {}, t("settings.theme")),
      h("p", {class: "settings-section-description"},
        t("settings.theme_description")),
      h("div", {class: "settings-grid two-columns"}, h("div", {class: "setting-field"}, h("span", {}, t("settings.theme")), select)));
    return {node, read: () => choice};
  }

  // Language names are shown in their own language and never translated. The pseudo-locale is
  // listed only while config.yaml selects it, so saving the form never silently switches it off.
  const languageLabel = (value: LanguageSetting): string => value === "auto" ? t("settings.language_auto")
    : value === "qps-ploc" ? t("settings.language_pseudo") : "繁體中文";

  function languageControl(data: SettingsResponse, blocked: boolean): {node: HTMLElement; read(): LanguageSetting} {
    let choice: LanguageSetting = data.editable.display.language;
    const values: LanguageSetting[] = choice === "qps-ploc" ? ["auto", "zh-Hant", "qps-ploc"] : ["auto", "zh-Hant"];
    const select = customSelect({id: "display-language", label: t("settings.language"), value: choice, disabled: blocked,
      options: values.map(value => ({value, label: languageLabel(value)})),
      onChange: next => { choice = next as LanguageSetting; }});
    const node = h("section", {class: "settings-section"}, h("h3", {}, t("settings.language")),
      h("p", {class: "settings-section-description"},
        t("settings.language_description", {locale: currentLocale()})),
      h("div", {class: "settings-grid two-columns"}, h("div", {class: "setting-field"}, h("span", {}, t("settings.language")), select)));
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
      h("p", {class: "eyebrow"}, "ABOUT & DIAGNOSTICS"), h("h2", {}, t("settings.tab_about")));
    if (!info) {
      card.append(h("p", {class: "notice"}, t("settings.about_unavailable")));
      return card;
    }
    const feedback = h("p", {class: "about-feedback", role: "status", "aria-live": "polite"});
    const show = (text: string, error = false): void => {
      feedback.textContent = text;
      feedback.classList.toggle("settings-error", error);
    };
    const supported = String(info.schema.supported);
    const schema = info.schema.database === null ? t("settings.schema_unreadable", {supported})
      : t("settings.schema_value", {database: String(info.schema.database), supported});
    const rows: [string, string][] = [
      [t("settings.about_app_version"), info.app_version],
      [t("settings.about_mode"), info.mode === "desktop" ? t("settings.about_desktop", {version: info.desktop_version ?? t("settings.about_version_unknown")}) : t("settings.about_browser")],
      [t("settings.about_schema"), schema],
      ["Python", info.python_version],
      [t("settings.about_os"), info.os],
      [t("settings.timezone"), info.timezone],
      [t("settings.about_config"), info.paths.config ?? t("settings.about_unspecified")],
      [t("settings.about_archive"), info.paths.archive],
      [t("settings.about_database"), info.paths.database],
      [t("settings.about_archive_logs"), info.paths.archive_logs],
    ];
    if (info.paths.desktop_logs) rows.push([t("settings.about_desktop_logs"), info.paths.desktop_logs]);
    const folderButton = (target: FolderTarget): HTMLElement => {
      const available = info.can_open_folders && info.folders[target];
      return h("button", {type: "button", disabled: !available,
        title: !info.can_open_folders ? t("settings.folder_unsupported") : info.folders[target] ? ""
          : t(`settings.folder_missing_${target}`),
        onclick: async (event: Event) => {
          const button = event.currentTarget as HTMLButtonElement;
          button.disabled = true;
          const error = await actions.onOpen(target);
          button.disabled = false;
          show(error ? t("settings.folder_open_failed", {error})
            : t("settings.folder_opened", {name: t(`settings.folder_${target}`)}), Boolean(error));
        }}, t(`settings.open_${target}`));
    };
    card.append(
      h("p", {class: "settings-section-description"},
        t("settings.about_description")),
      ...(info.notices ?? []).map(text => h("p", {class: "notice"}, text)),
      h("div", {class: "settings-paths about-facts"},
        rows.map(([label, value]) => h("div", {}, h("span", {}, label), h("code", {}, value)))),
      h("div", {class: "account-actions about-actions"},
        folderButton("archive"),
        folderButton("archive_logs"),
        info.paths.desktop_logs ? folderButton("desktop_logs") : null,
        h("button", {type: "button", onclick: async () => {
          show(await copyText(info.text) ? t("settings.copied") : t("settings.copy_failed"),
            false);
        }}, t("settings.copy_diagnostics"))),
      feedback);
    return card;
  }

  export const SETTINGS_TABS: SettingsTab[] = ["account", "general", "backup", "theme", "about"];

  export function isSettingsTab(value: unknown): value is SettingsTab {
    return SETTINGS_TABS.includes(value as SettingsTab);
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

  const authLabel = (state: AuthState): string => t(`settings.auth_${state}`);

  function renderAccountCard(auth: AuthStatus | null, blocked: boolean, actions: AccountActions): HTMLElement {
    if (!auth) {
      // Shown at once; the check can take a while (it may start the dedicated browser).
      return h("section", {class: "settings-card account-card tone-neutral", "aria-busy": "true"},
        h("div", {class: "account-heading"}, h("div", {}, h("p", {class: "eyebrow"}, "ACCOUNT & SIGN-IN"),
          h("h2", {}, t("settings.account_title"))), h("span", {class: "auth-badge neutral"}, authLabel("checking"))),
        h("p", {class: "account-message", role: "status", "aria-live": "polite"}, t("settings.account_checking")));
    }
    const authBusy = auth.state === "checking";
    const authLocked = auth.state === "locked";
    const authTone = auth.state === "authenticated" ? "success"
      : auth.state === "expired" || auth.state === "error" ? "error" : "neutral";
    const lastKnown = authLocked && auth.last_known
      ? t("settings.last_known", {state: authLabel(auth.last_known.state), time: formatDate(auth.last_known.checked_at)})
      : null;
    const authFeedback = h("p", {class: "settings-error", role: "alert", hidden: true});
    const runAuth = async (action: () => Promise<string | null>): Promise<void> => {
      authFeedback.hidden = true;
      const error = await action();
      if (error) { authFeedback.textContent = error; authFeedback.hidden = false; }
    };
    return h("section", {class: `settings-card account-card tone-${authTone}`},
      h("div", {class: "account-heading"}, h("div", {}, h("p", {class: "eyebrow"}, "ACCOUNT & SIGN-IN"),
        h("h2", {}, t("settings.account_title"))), h("span", {class: `auth-badge ${authTone}`}, authLabel(auth.state))),
      h("p", {class: "account-message", role: "status", "aria-live": "polite"}, auth.message),
      lastKnown ? h("p", {class: "account-last-known"}, lastKnown) : null,
      h("p", {class: "settings-section-description"}, auth.source === "profile"
        ? t("settings.source_profile")
        : auth.source === "environment" ? t("settings.source_environment")
        : t("settings.source_none")),
      auth.externally_managed ? h("p", {class: "auth-external-notice"},
        t("settings.external_notice")) : null,
      h("div", {class: "account-actions"},
        h("button", {type: "button", class: "primary", disabled: blocked || authLocked || authBusy || !auth.can_login,
          onclick: () => void runAuth(actions.onLogin)}, t("settings.login")),
        h("button", {type: "button", disabled: blocked || authLocked || authBusy, onclick: actions.onRefresh}, t("settings.recheck")),
        authBusy && auth.job ? h("button", {type: "button", class: "danger-outline",
          onclick: () => void runAuth(() => actions.onCancel(auth.job!.job_id))}, t("settings.cancel_login")) : null,
        h("button", {type: "button", class: "danger-outline",
          disabled: blocked || authLocked || authBusy || !auth.can_logout,
          onclick: async () => {
            const confirmed = await confirmDialog({
              title: t("settings.logout_title"), message: t("settings.logout_message"),
              cancelLabel: t("settings.logout_cancel"), confirmLabel: t("settings.logout"), danger: true,
            });
            if (confirmed) void runAuth(actions.onLogout);
          }}, t("settings.logout")), authFeedback));
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
    const markdown = settingCheckbox(t("settings.markdown_enabled"), value.markdown.enabled);
    const frontMatter = settingCheckbox(t("settings.markdown_front_matter"), value.markdown.yaml_front_matter);
    const relativePaths = settingCheckbox(t("settings.markdown_relative_paths"), value.markdown.relative_image_paths);
    const preserveOrder = settingCheckbox(t("settings.markdown_original_order"), value.markdown.preserve_original_order);
    const logLevel = customSelect({id: "log-level", label: t("settings.log_level"), value: value.logging.level, disabled: blocked,
      options: ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"].map(item => ({value: item, label: item}))});
    const logLevelField = h("div", {class: "setting-field"}, h("span", {}, t("settings.log_level")), logLevel);
    const keepDays = settingNumber(t("settings.log_keep_days"), value.logging.keep_days, 1, 365);
    const fileLogs = settingCheckbox(t("settings.log_to_file"), value.logging.write_to_file);
    const checked = (control: InputControl): TrackedField => ({node: control.node, read: () => control.input.checked});
    return {
      content: [h("section", {class: "settings-card"}, h("p", {class: "eyebrow"}, "GENERAL"), h("h2", {}, t("settings.tab_general")),
        language.node, timezone.node,
        h("section", {class: "settings-section"}, h("h3", {}, "Markdown"),
          h("div", {class: "setting-toggles"}, markdown.node, frontMatter.node, relativePaths.node, preserveOrder.node)),
        h("section", {class: "settings-section"}, h("h3", {}, t("settings.logs")),
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
      content: [h("section", {class: "settings-card"}, h("p", {class: "eyebrow"}, "THEME"), h("h2", {}, t("settings.tab_theme")),
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
      t("settings.max_posts"), value.sync.max_posts_per_run, 1, 100, 1,
      t("settings.max_posts_hint"),
    );
    const unchangedStop = settingNumber(
      t("settings.unchanged_stop"), value.sync.recent_unchanged_stop_count, 1, 500, 1,
      t("settings.unchanged_stop_hint"),
    );
    const defaultDryRun = settingCheckbox(t("settings.default_dry_run"), value.backup_defaults.dry_run);
    const defaultProfile = settingCheckbox(t("settings.default_profile"), value.backup_defaults.include_profile);
    const defaultFancard = settingCheckbox(t("settings.default_fancard"), value.backup_defaults.include_fancard);
    const originalImages = settingCheckbox(t("settings.original_images"), value.download.original_images);
    const attachments = settingCheckbox(t("settings.attachments"), value.download.download_attachments);
    const covers = settingCheckbox(t("settings.covers"), value.download.download_cover);
    const resume = settingCheckbox(t("settings.resume"), value.download.resume);
    const hashes = settingCheckbox(t("settings.verify_sha256"), value.download.verify_sha256);
    const preserveDeleted = settingCheckbox(t("settings.preserve_deleted"), value.sync.preserve_deleted_posts);
    const skipCompleted = settingCheckbox(t("settings.skip_completed"), value.sync.skip_completed);
    const checkUpdates = settingCheckbox(t("settings.check_updates"), value.sync.check_updates);
    const rotate = settingCheckbox(t("settings.rotate_creators"), value.sync.rotate_creators);
    const retries = settingNumber(t("settings.retries"), value.download.retry_count, 0, 10);
    const interval = settingNumber(t("settings.request_interval"), value.download.request_interval_seconds, 1, 3600, .5,
      t("settings.request_interval_hint"));
    const timeout = settingNumber(t("settings.request_timeout"), value.download.timeout_seconds, 5, 600);
    const scheduleSection = renderScheduleSection(value.schedule, schedule.status, schedule.creators, blocked,
      schedule.actions);
    const checked = (control: InputControl): TrackedField => ({node: control.node, read: () => control.input.checked});
    const number = (control: InputControl): TrackedField => ({node: control.node, read: () => control.input.value});
    return {
      content: [h("section", {class: "settings-card backup-settings"}, h("p", {class: "eyebrow"}, "BACKUP"), h("h2", {}, t("settings.tab_backup")),
        h("section", {class: "settings-section"}, h("h3", {}, t("settings.section_quota")),
          h("p", {class: "settings-section-description"}, t("settings.section_quota_description")),
          h("div", {class: "settings-grid two-columns"}, maxPosts.node, unchangedStop.node)),
        h("section", {class: "settings-section"}, h("h3", {}, t("settings.section_defaults")),
          h("p", {class: "settings-section-description"}, t("settings.section_defaults_description")),
          h("div", {class: "setting-toggles"}, defaultDryRun.node, defaultProfile.node, defaultFancard.node)),
        scheduleSection.node,
        h("section", {class: "settings-section"}, h("h3", {}, t("settings.section_content")),
          h("div", {class: "setting-toggles"}, originalImages.node, attachments.node, covers.node, resume.node, hashes.node, preserveDeleted.node)),
        h("section", {class: "settings-section"}, h("h3", {}, t("settings.section_updates")),
          h("div", {class: "setting-toggles"}, skipCompleted.node, checkUpdates.node, rotate.node)),
        h("section", {class: "settings-section"}, h("h3", {}, t("settings.section_network")),
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
      onDirty: dirty => scheduleSection.setRunBlocked(dirty ? t("settings.run_blocked_unsaved") : null),
      onLocked: locked => scheduleSection.setLocked(locked),
    };
  }

  /** The settings page: sub-page tabs, then one sub-page, each saving only its own fields. */
  export function renderSettingsPage(ctx: SettingsPageContext): SettingsPageHandle {
    const {data, tab} = ctx;
    let blocked = Boolean(ctx.activeJob);
    const tabButtons = new Map<SettingsTab, HTMLButtonElement>();
    const tabs = h("nav", {class: "settings-tabs", "aria-label": t("settings.tabs_label")},
      SETTINGS_TABS.map(item => {
        const button = h("button", {type: "button", "data-settings-tab": item,
          "aria-current": item === tab ? "page" : null, class: item === tab ? "active" : "",
          onclick: () => { if (item !== tab) ctx.onTab(item); }},
        h("span", {}, t(`settings.tab_${item}`))) as HTMLButtonElement;
        tabButtons.set(item, button);
        return button;
      }));
    const markTab = (dirty: boolean): void => {
      const button = tabButtons.get(tab);
      if (!button) return;
      button.querySelector(".tab-dirty")?.remove();
      if (dirty) button.append(h("span", {class: "tab-dirty"}, t("settings.tab_unsaved")));
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
      save = h("button", {type: "submit", class: "primary", disabled: !data.writable || blocked}, t("settings.save")) as HTMLButtonElement;
      lockNote = h("span", {class: "notice", hidden: !blocked}, t("settings.locked_note"));
      fieldset = h("fieldset", {disabled: blocked}, ...editable.content) as HTMLFieldSetElement;
      const form = h("form", {class: "settings-form", "aria-disabled": blocked, onsubmit: async (event: Event) => {
        event.preventDefault();
        if (blocked) return;
        feedback.hidden = true;
        save!.disabled = true;
        const error = await ctx.onSave(editable.patch());
        if (save!.isConnected) save!.disabled = !data.writable || blocked;
        if (error) {
          feedback.textContent = t("settings.save_failed", {error});
          feedback.hidden = false;
        }
      }},
      fieldset,
      h("div", {class: "settings-actions"}, save,
        !data.writable ? h("span", {class: "notice"}, t("settings.not_writable")) : null,
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
      h("header", {class: "heading"}, h("div", {}, h("p", {class: "eyebrow"}, "LOCAL SETTINGS"), h("h1", {}, t("settings.title")),
        h("p", {}, t("settings.subtitle")))),
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
