namespace FanboxUI {
  const WEEKDAYS = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"];

  export interface ScheduleSectionActions {
    /** Server-side summary and next runs for the values currently in the form. */
    onPreview(schedule: ScheduleSettingsPatch): Promise<SchedulePreview>;
    onRunNow(): Promise<string | null>;
  }

  export interface ScheduleSection {
    node: HTMLElement;
    read(): ScheduleSettingsPatch;
  }

  function lastResultText(status: ScheduleStatus): string {
    const job = status.last_job;
    if (!job) return status.last_due_at ? `上次排程：${formatDate(status.last_due_at)}` : "尚未執行過排程備份。";
    const outcome = job.status === "completed" ? "完成" : job.status === "failed" ? "失敗"
      : isActiveJob(job as WebJob) ? "執行中" : statusText(job.status);
    return `上次排程：${formatDate(status.last_due_at ?? job.created_at)} · ${outcome}${job.error ? `（${job.error}）` : ""}`;
  }

  export function renderScheduleSection(
    value: ScheduleSettings, status: ScheduleStatus, creators: CreatorSummary[], blocked: boolean,
    actions: ScheduleSectionActions,
  ): ScheduleSection {
    const enabled = h("input", {type: "checkbox", checked: value.enabled}) as HTMLInputElement;
    let frequencyValue: ScheduleFrequency = value.frequency;
    let monthDay = value.month_day;
    const interval = h("input", {type: "number", value: value.interval, min: 1, max: 30, step: 1}) as HTMLInputElement;
    const time = h("input", {type: "time", value: value.time, step: 60, required: true}) as HTMLInputElement;
    const intervalUnit = h("small", {});
    const preview = h("p", {class: "schedule-preview", role: "status", "aria-live": "polite"});
    const runFeedback = h("p", {class: "settings-error", role: "alert", hidden: true});

    const frequency = customSelect({id: "schedule-frequency", label: "週期", value: frequencyValue, disabled: blocked,
      options: [{value: "daily", label: "每天／每 N 天"}, {value: "weekly", label: "每週／每 N 週"},
        {value: "monthly", label: "每月指定日期"}],
      onChange: next => { frequencyValue = next as ScheduleFrequency; sync(); }});
    const weekday = customSelect({id: "schedule-weekday", label: "星期", value: value.weekday, disabled: blocked,
      options: WEEKDAYS.map((label, index) => ({value: index, label})), onChange: () => sync()});
    const dayButtons = Array.from({length: 31}, (_, index) => h("button", {type: "button",
      class: "schedule-day", "aria-pressed": index + 1 === monthDay ? "true" : "false",
      onclick: () => { monthDay = index + 1; sync(); }}, String(index + 1)) as HTMLButtonElement);
    const creatorBoxes = creators.map(item => {
      const input = h("input", {type: "checkbox", value: item.creator_id,
        checked: value.creators.includes(item.creator_id)}) as HTMLInputElement;
      input.addEventListener("change", () => sync());
      return {input, node: h("label", {class: "setting-toggle"}, input, h("span", {}, `${item.name} @${item.creator_id}`))};
    });
    const unknownCreators = value.creators.filter(id => !creators.some(item => item.creator_id === id));

    const intervalField = h("label", {class: "setting-field"}, h("span", {}, "間隔"), interval, intervalUnit);
    const weekdayField = h("div", {class: "setting-field"}, h("span", {}, "星期"), weekday);
    const monthField = h("div", {class: "setting-field schedule-month"},
      h("span", {id: "schedule-month-label"}, "每月日期"),
      h("div", {class: "schedule-days", role: "group", "aria-labelledby": "schedule-month-label"}, dayButtons),
      h("small", {}, "選 29–31 日時，沒有這一天的月份會在月底執行。"));

    const read = (): ScheduleSettingsPatch => ({
      enabled: enabled.checked, frequency: frequencyValue,
      interval: Math.min(30, Math.max(1, Math.round(Number(interval.value) || 1))),
      weekday: Number(weekday.value), month_day: monthDay, time: time.value,
      creators: [...creatorBoxes.filter(item => item.input.checked).map(item => item.input.value), ...unknownCreators],
    });

    let previewTimer: number | undefined;
    let previewToken = 0;
    const sync = (): void => {
      intervalField.hidden = frequencyValue === "monthly";
      weekdayField.hidden = frequencyValue !== "weekly";
      monthField.hidden = frequencyValue !== "monthly";
      intervalUnit.textContent = frequencyValue === "weekly" ? "1 = 每週；2 = 每兩週" : "1 = 每天；2 = 每兩天";
      for (const [index, button] of dayButtons.entries()) {
        button.setAttribute("aria-pressed", index + 1 === monthDay ? "true" : "false");
      }
      if (previewTimer !== undefined) clearTimeout(previewTimer);
      previewTimer = window.setTimeout(() => {
        const token = ++previewToken;
        actions.onPreview(read()).then(result => {
          if (token !== previewToken) return;
          preview.textContent = `預覽：${result.summary}｜接下來：${result.next_runs.map(formatDate).join("、")}`;
        }).catch(error => {
          if (token !== previewToken) return;
          preview.textContent = `無法預覽：${error instanceof Error ? error.message : String(error)}`;
        });
      }, 250);
    };
    for (const input of [enabled, interval, time]) input.addEventListener("input", sync);

    const runNow = h("button", {type: "button", class: "secondary", disabled: blocked, onclick: async () => {
      runFeedback.hidden = true;
      const error = await actions.onRunNow();
      if (error) { runFeedback.textContent = error; runFeedback.hidden = false; }
    }}, "立即執行一次");

    const node = h("section", {class: "settings-section schedule-settings"},
      h("h3", {}, "自動備份"),
      h("p", {class: "settings-section-description"},
        "程式開著時依排程自動開始完整備份；關閉期間錯過的排程，下次開啟時只會補跑一次。時間一律以 Asia/Taipei 計算。"),
      h("dl", {class: "schedule-status"},
        h("div", {}, h("dt", {}, "目前排程"), h("dd", {}, status.enabled ? status.summary : "未啟用")),
        h("div", {}, h("dt", {}, "下一次執行"), h("dd", {}, status.next_run_at ? formatDate(status.next_run_at) : "—")),
        h("div", {}, h("dt", {}, "上次結果"), h("dd", {}, lastResultText(status)))),
      status.note ? h("p", {class: "notice schedule-note"}, status.note) : null,
      h("label", {class: "setting-toggle"}, enabled, h("span", {}, "啟用自動備份")),
      h("div", {class: "settings-grid"}, h("div", {class: "setting-field"}, h("span", {}, "週期"), frequency),
        intervalField, weekdayField, h("label", {class: "setting-field"}, h("span", {}, "時間（Asia/Taipei）"), time)),
      monthField,
      h("details", {class: "schedule-creators"}, h("summary", {}, "備份範圍：未勾選時備份全部支援中的創作者"),
        creatorBoxes.length ? h("div", {class: "setting-toggles"}, creatorBoxes.map(item => item.node))
          : h("p", {class: "settings-section-description"}, "目前沒有已知的創作者；將備份全部支援中的創作者。")),
      preview,
      h("div", {class: "schedule-actions"}, runNow,
        h("span", {class: "settings-section-description"}, "使用目前已儲存的排程範圍與「新工作預設」的 Profile／Fan Card 選項，不會變更下一次排程。")),
      runFeedback);
    sync();
    return {node, read};
  }
}
