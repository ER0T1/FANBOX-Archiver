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

  export function renderSettingsPage(
    data: SettingsResponse, message: string, activeJob: WebJob | null,
    onSave: (patch: SettingsPatch) => void,
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
      "備份表單預設投稿上限", value.sync.max_posts_per_run, 1, 100, 1,
      "建立工作時可針對單次備份覆寫，不會反向修改此設定。",
    );
    const unchangedStop = settingNumber("連續未變時停止回補", value.sync.recent_unchanged_stop_count, 1, 500);
    const defaultDryRun = settingCheckbox("完整備份只預覽，不下載", value.backup_defaults.dry_run);
    const defaultProfile = settingCheckbox("預設拉取個人資料", value.backup_defaults.include_profile);
    const defaultFancard = settingCheckbox("預設拉取粉絲卡", value.backup_defaults.include_fancard);
    const markdown = settingCheckbox("產生 Markdown", value.markdown.enabled);
    const frontMatter = settingCheckbox("加入 YAML front matter", value.markdown.yaml_front_matter);
    const relativePaths = settingCheckbox("Markdown 使用相對圖片路徑", value.markdown.relative_image_paths);
    const preserveOrder = settingCheckbox("保留原始內容順序", value.markdown.preserve_original_order);
    const fileLogs = settingCheckbox("寫入檔案日誌", value.logging.write_to_file);
    const keepDays = settingNumber("日誌保留天數", value.logging.keep_days, 1, 365);
    const logLevel = customSelect({id: "log-level", label: "日誌等級", value: value.logging.level,
      options: ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"].map(item => ({value: item, label: item}))});
    const blocked = Boolean(activeJob);
    const form = h("form", {class: "settings-form", "aria-disabled": blocked, onsubmit: (event: Event) => {
      event.preventDefault();
      if (blocked) return;
      onSave({download: {
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
      }, markdown: {
        enabled: markdown.input.checked, yaml_front_matter: frontMatter.input.checked,
        relative_image_paths: relativePaths.input.checked, preserve_original_order: preserveOrder.input.checked,
      }, logging: {level: logLevel.value, write_to_file: fileLogs.input.checked,
        keep_days: Number(keepDays.input.value)}});
    }},
    h("fieldset", {disabled: blocked},
    h("section", {class: "settings-card"}, h("p", {class: "eyebrow"}, "DOWNLOAD"), h("h2", {}, "下載"),
      h("div", {class: "settings-grid"}, retries.node, interval.node, timeout.node),
      h("div", {class: "setting-toggles"}, originalImages.node, attachments.node, covers.node, resume.node, hashes.node)),
    h("section", {class: "settings-card"}, h("p", {class: "eyebrow"}, "SYNC"), h("h2", {}, "同步"),
      h("div", {class: "settings-grid"}, maxPosts.node, unchangedStop.node),
      h("div", {class: "setting-toggles"}, skipCompleted.node, checkUpdates.node, preserveDeleted.node, rotate.node)),
    h("section", {class: "settings-card"}, h("p", {class: "eyebrow"}, "BACKUP DEFAULTS"), h("h2", {}, "新備份表單預設值"),
      h("p", {class: "setting-help"}, "每次進入新工作表單時套用；重試工作仍沿用原工作設定。"),
      h("div", {class: "setting-toggles"}, defaultDryRun.node, defaultProfile.node, defaultFancard.node)),
    h("section", {class: "settings-card"}, h("p", {class: "eyebrow"}, "OUTPUT"), h("h2", {}, "Markdown 與日誌"),
      h("div", {class: "settings-grid"}, h("label", {class: "setting-field"}, h("span", {}, "日誌等級"), logLevel), keepDays.node),
      h("div", {class: "setting-toggles"}, markdown.node, frontMatter.node, relativePaths.node, preserveOrder.node, fileLogs.node)),
    h("div", {class: "settings-actions"}, h("button", {type: "submit", class: "primary",
      disabled: !data.writable || blocked}, "儲存設定"),
      !data.writable ? h("span", {class: "notice"}, "目前伺服器未指定可寫入的設定檔。") : null,
      blocked ? h("span", {class: "notice"}, "工作結束後即可儲存設定。") : null)));
    return h("section", {class: "page settings-page"},
      h("header", {class: "heading"}, h("div", {}, h("p", {class: "eyebrow"}, "LOCAL SETTINGS"), h("h1", {}, "設定"),
        h("p", {}, "只顯示安全的一般選項；儲存與認證路徑維持唯讀。"))),
      message ? h("p", {class: "settings-saved", role: "status"}, message) : null,
      activeJobNotice(activeJob),
      h("section", {class: "settings-paths"},
        h("div", {}, h("span", {}, "封存目錄"), h("code", {}, data.storage.output_dir)),
        h("div", {}, h("span", {}, "資料庫"), h("code", {}, data.storage.database)),
        h("div", {}, h("span", {}, "設定檔"), h("code", {}, data.config_path || "未指定"))), form);
  }
}
