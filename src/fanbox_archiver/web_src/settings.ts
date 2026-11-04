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

  export function renderSettingsPage(
    data: SettingsResponse, auth: AuthStatus, message: string, activeJob: WebJob | null,
    onSave: (patch: SettingsPatch) => Promise<string | null>,
    onAuthRefresh: () => void,
    onAuthLogin: () => Promise<string | null>,
    onAuthCancel: (jobId: string) => Promise<string | null>,
    onAuthLogout: () => Promise<string | null>,
    schedule: {status: ScheduleStatus; creators: CreatorSummary[]; actions: ScheduleSectionActions},
    about: {info: DiagnosticsInfo | null; actions: AboutSectionActions},
  ): HTMLElement {
    const value = data.editable;
    const originalImages = settingCheckbox("下載原始圖片", value.download.original_images);
    const attachments = settingCheckbox("下載附件", value.download.download_attachments);
    const covers = settingCheckbox("下載投稿與 Profile 封面", value.download.download_cover);
    const resume = settingCheckbox("支援續傳", value.download.resume);
    const hashes = settingCheckbox("下載後驗證 SHA-256", value.download.verify_sha256);
    const retries = settingNumber("失敗重試次數", value.download.retry_count, 0, 10);
    const interval = settingNumber("請求間隔（秒）", value.download.request_interval_seconds, 1, 3600, .5,
      "最低 1 秒；提高此值可降低請求頻率。");
    const timeout = settingNumber("請求逾時（秒）", value.download.timeout_seconds, 5, 600);
    const skipCompleted = settingCheckbox("略過已完成且未更新的投稿", value.sync.skip_completed);
    const checkUpdates = settingCheckbox("檢查遠端更新", value.sync.check_updates);
    const preserveDeleted = settingCheckbox("保留遠端已刪除投稿的本機備份", value.sync.preserve_deleted_posts);
    const rotate = settingCheckbox("輪替創作者處理順序", value.sync.rotate_creators);
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
    const markdown = settingCheckbox("產生 Markdown", value.markdown.enabled);
    const frontMatter = settingCheckbox("加入 YAML front matter", value.markdown.yaml_front_matter);
    const relativePaths = settingCheckbox("Markdown 使用相對圖片路徑", value.markdown.relative_image_paths);
    const preserveOrder = settingCheckbox("保留原始內容順序", value.markdown.preserve_original_order);
    const fileLogs = settingCheckbox("寫入檔案日誌", value.logging.write_to_file);
    const keepDays = settingNumber("日誌保留天數", value.logging.keep_days, 1, 365);
    const blocked = Boolean(activeJob);
    const scheduleSection = renderScheduleSection(value.schedule, schedule.status, schedule.creators, blocked,
      schedule.actions);
    const timezone = timezoneControl(data, blocked);
    const logLevel = customSelect({id: "log-level", label: "日誌等級", value: value.logging.level, disabled: blocked,
      options: ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"].map(item => ({value: item, label: item}))});
    const authBusy = auth.state === "checking";
    const authLocked = auth.state === "locked";
    const authTone = auth.state === "authenticated" ? "success"
      : auth.state === "expired" || auth.state === "error" ? "error" : "neutral";
    const authLabels: Record<AuthState, string> = {checking: "檢查中", locked: "工作中", authenticated: "已登入",
      signed_out: "未登入", expired: "已失效", error: "檢查失敗"};
    const authLabel = authLabels[auth.state];
    const lastKnown = authLocked && auth.last_known
      ? `上次檢查：${authLabels[auth.last_known.state]}（${formatDate(auth.last_known.checked_at)}）` : null;
    const authFeedback = h("p", {class: "settings-error", role: "alert", hidden: true});
    const runAuth = async (action: () => Promise<string | null>): Promise<void> => {
      authFeedback.hidden = true;
      const error = await action();
      if (error) { authFeedback.textContent = error; authFeedback.hidden = false; }
    };
    const feedback = h("p", {class: "settings-error", role: "alert", hidden: true});
    const form = h("form", {class: "settings-form", "aria-disabled": blocked, onsubmit: async (event: Event) => {
      event.preventDefault();
      if (blocked) return;
      feedback.hidden = true;
      const error = await onSave({download: {
        original_images: originalImages.input.checked, download_attachments: attachments.input.checked,
        download_cover: covers.input.checked, resume: resume.input.checked, verify_sha256: hashes.input.checked,
        retry_count: Number(retries.input.value), request_interval_seconds: Number(interval.input.value),
        timeout_seconds: Number(timeout.input.value),
      }, sync: {
        skip_completed: skipCompleted.input.checked, check_updates: checkUpdates.input.checked,
        preserve_deleted_posts: preserveDeleted.input.checked, rotate_creators: rotate.input.checked,
        max_posts_per_run: Number(maxPosts.input.value),
        recent_unchanged_stop_count: Number(unchangedStop.input.value),
      }, backup_defaults: {
        dry_run: defaultDryRun.input.checked, include_profile: defaultProfile.input.checked,
        include_fancard: defaultFancard.input.checked,
      }, schedule: scheduleSection.read(), display: {timezone: timezone.read()}, markdown: {
        enabled: markdown.input.checked, yaml_front_matter: frontMatter.input.checked,
        relative_image_paths: relativePaths.input.checked, preserve_original_order: preserveOrder.input.checked,
      }, logging: {level: logLevel.value, write_to_file: fileLogs.input.checked,
        keep_days: Number(keepDays.input.value)}});
      if (error) {
        feedback.textContent = `儲存失敗：${error}`;
        feedback.hidden = false;
      }
    }},
    h("fieldset", {disabled: blocked},
    h("section", {class: "settings-card backup-settings"}, h("p", {class: "eyebrow"}, "BACKUP"), h("h2", {}, "備份"),
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
        h("div", {class: "settings-grid"}, retries.node, interval.node, timeout.node))),
    h("section", {class: "settings-card"}, h("p", {class: "eyebrow"}, "OUTPUT & LOGGING"), h("h2", {}, "輸出與紀錄"),
      timezone.node,
      h("section", {class: "settings-section"}, h("h3", {}, "Markdown"),
        h("div", {class: "setting-toggles"}, markdown.node, frontMatter.node, relativePaths.node, preserveOrder.node)),
      h("section", {class: "settings-section"}, h("h3", {}, "日誌"),
        h("div", {class: "settings-grid two-columns"}, h("div", {class: "setting-field"}, h("span", {}, "日誌等級"), logLevel), keepDays.node),
        h("div", {class: "setting-toggles"}, fileLogs.node))),
    h("div", {class: "settings-actions"}, h("button", {type: "submit", class: "primary",
      disabled: !data.writable || blocked}, "儲存設定"),
      !data.writable ? h("span", {class: "notice"}, "目前伺服器未指定可寫入的設定檔。") : null,
      blocked ? h("span", {class: "notice"}, "工作結束後即可儲存設定。") : null,
      feedback)));
    return h("section", {class: "page settings-page"},
      h("header", {class: "heading"}, h("div", {}, h("p", {class: "eyebrow"}, "LOCAL SETTINGS"), h("h1", {}, "設定"),
        h("p", {}, "只顯示安全的一般選項；儲存與認證路徑維持唯讀。"))),
      message ? h("p", {class: "settings-saved", role: "status"}, message) : null,
      activeJobNotice(activeJob),
      h("section", {class: `settings-card account-card tone-${authTone}`},
        h("div", {class: "account-heading"}, h("div", {}, h("p", {class: "eyebrow"}, "ACCOUNT & SIGN-IN"),
          h("h2", {}, "帳號／登入")), h("span", {class: `auth-badge ${authTone}`}, authLabel)),
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
            onclick: () => void runAuth(onAuthLogin)}, "登入 FANBOX"),
          h("button", {type: "button", disabled: blocked || authLocked || authBusy, onclick: onAuthRefresh}, "重新檢查"),
          authBusy && auth.job ? h("button", {type: "button", class: "danger-outline",
            onclick: () => void runAuth(() => onAuthCancel(auth.job!.job_id))}, "取消登入") : null,
          h("button", {type: "button", class: "danger-outline",
            disabled: blocked || authLocked || authBusy || !auth.can_logout,
            onclick: () => { if (window.confirm("確定要清除專用 FANBOX 工作階段嗎？封存與設定不會被刪除。")) {
              void runAuth(onAuthLogout);
            }}}, "登出"), authFeedback)),
      form, renderAboutSection(about.info, about.actions));
  }
}
