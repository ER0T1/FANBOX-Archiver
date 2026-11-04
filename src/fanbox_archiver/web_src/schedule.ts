namespace FanboxUI {

  export interface ScheduleSectionActions {
    /** Server-side summary and next runs for the values currently in the form. */
    onPreview(schedule: ScheduleSettingsPatch): Promise<SchedulePreview>;
    onRunNow(): Promise<string | null>;
  }

  export interface ScheduleSection {
    node: HTMLElement;
    read(): ScheduleSettingsPatch;
    /** Each editable part, so unsaved changes can be marked where they are. */
    fields: TrackedField[];
    /** Disables "run now" with a reason (e.g. unsaved changes), or re-enables it with null. */
    setRunBlocked(reason: string | null): void;
    /** Follows the page lock when a job starts or ends without a redraw. */
    setLocked(locked: boolean): void;
  }

  function lastResultText(status: ScheduleStatus): string {
    const job = status.last_job;
    if (!job) return status.last_due_at ? t("schedule.last_due", {time: formatDate(status.last_due_at)}) : t("schedule.never_run");
    const outcome = job.status === "completed" ? t("schedule.outcome_completed")
      : job.status === "failed" ? t("schedule.outcome_failed")
      : isActiveJob(job as WebJob) ? t("schedule.outcome_running") : statusText(job.status);
    const time = formatDate(status.last_due_at ?? job.created_at);
    return job.error ? t("schedule.last_result_error", {time, outcome, error: job.error})
      : t("schedule.last_result", {time, outcome});
  }

  export function renderScheduleSection(
    value: ScheduleSettings, status: ScheduleStatus, creators: CreatorSummary[], blocked: boolean,
    actions: ScheduleSectionActions,
  ): ScheduleSection {
    const enabled = h("input", {type: "checkbox", checked: value.enabled}) as HTMLInputElement;
    let frequencyValue: ScheduleFrequency = value.frequency;
    let powerValue: SchedulePower = value.power;
    let monthDay = value.month_day;
    const interval = h("input", {type: "number", value: value.interval, min: 1, max: 30, step: 1}) as HTMLInputElement;
    // 24-hour hour/minute pickers: a native time input follows the Windows locale (上午／下午).
    const [savedHour, savedMinute] = value.time.split(":");
    const hour = customSelect({id: "schedule-hour", label: t("schedule.hour"), value: savedHour, disabled: blocked,
      options: Array.from({length: 24}, (_, index) => ({value: String(index).padStart(2, "0"), label: String(index).padStart(2, "0")})),
      onChange: () => sync()});
    const minute = customSelect({id: "schedule-minute", label: t("schedule.minute"), value: savedMinute, disabled: blocked,
      options: Array.from({length: 60}, (_, index) => ({value: String(index).padStart(2, "0"), label: String(index).padStart(2, "0")})),
      onChange: () => sync()});
    const intervalUnit = h("small", {});
    const preview = h("p", {class: "schedule-preview", role: "status", "aria-live": "polite"});
    const runFeedback = h("p", {class: "settings-error", role: "alert", hidden: true});

    const frequency = customSelect({id: "schedule-frequency", label: t("schedule.frequency"), value: frequencyValue, disabled: blocked,
      options: [{value: "daily", label: t("schedule.frequency_daily")}, {value: "weekly", label: t("schedule.frequency_weekly")},
        {value: "monthly", label: t("schedule.frequency_monthly")}],
      onChange: next => { frequencyValue = next as ScheduleFrequency; sync(); }});
    const power = customSelect({id: "schedule-power", label: t("schedule.power"), value: powerValue, disabled: blocked,
      options: [{value: "no_wake_battery_ok", label: t("schedule.power_no_wake_battery_ok")},
        {value: "no_wake_ac_only", label: t("schedule.power_no_wake_ac_only")},
        {value: "wake", label: t("schedule.power_wake")}],
      onChange: next => { powerValue = next as SchedulePower; sync(); }});
    const weekday = customSelect({id: "schedule-weekday", label: t("schedule.weekday"), value: value.weekday, disabled: blocked,
      options: Array.from({length: 7}, (_, index) => ({value: index, label: t(`schedule.weekday_${index}`)})),
      onChange: () => sync()});
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

    const intervalField = h("label", {class: "setting-field"}, h("span", {}, t("schedule.interval")), interval, intervalUnit);
    const weekdayField = h("div", {class: "setting-field"}, h("span", {}, t("schedule.weekday")), weekday);
    const monthField = h("div", {class: "setting-field schedule-month"},
      h("span", {id: "schedule-month-label"}, t("schedule.month_day")),
      h("div", {class: "schedule-days", role: "group", "aria-labelledby": "schedule-month-label"}, dayButtons),
      h("small", {}, t("schedule.month_day_hint")));

    const read = (): ScheduleSettingsPatch => ({
      enabled: enabled.checked, frequency: frequencyValue,
      interval: Math.min(30, Math.max(1, Math.round(Number(interval.value) || 1))),
      weekday: Number(weekday.value), month_day: monthDay, time: `${hour.value}:${minute.value}`, power: powerValue,
      creators: [...creatorBoxes.filter(item => item.input.checked).map(item => item.input.value), ...unknownCreators],
    });

    let previewTimer: number | undefined;
    let previewToken = 0;
    const sync = (): void => {
      intervalField.hidden = frequencyValue === "monthly";
      weekdayField.hidden = frequencyValue !== "weekly";
      monthField.hidden = frequencyValue !== "monthly";
      intervalUnit.textContent = t(frequencyValue === "weekly" ? "schedule.interval_weekly" : "schedule.interval_daily");
      for (const [index, button] of dayButtons.entries()) {
        button.setAttribute("aria-pressed", index + 1 === monthDay ? "true" : "false");
      }
      if (previewTimer !== undefined) clearTimeout(previewTimer);
      previewTimer = window.setTimeout(() => {
        const token = ++previewToken;
        actions.onPreview(read()).then(result => {
          if (token !== previewToken) return;
          preview.textContent = t("schedule.preview", {summary: result.summary,
            runs: result.next_runs.map(formatDate).join(t("schedule.run_separator"))});
        }).catch(error => {
          if (token !== previewToken) return;
          preview.textContent = t("schedule.preview_failed", {error: error instanceof Error ? error.message : String(error)});
        });
      }, 250);
    };
    for (const input of [enabled, interval]) input.addEventListener("input", sync);

    const runNow = h("button", {type: "button", class: "secondary", disabled: blocked, onclick: async () => {
      runFeedback.hidden = true;
      const error = await actions.onRunNow();
      if (error) { runFeedback.textContent = error; runFeedback.hidden = false; }
    }}, t("schedule.run_now")) as HTMLButtonElement;
    const runBlockedNote = h("small", {class: "schedule-run-blocked", hidden: true});
    const enabledField = h("label", {class: "setting-toggle"}, enabled, h("span", {}, t("schedule.enabled")));
    const frequencyField = h("div", {class: "setting-field"}, h("span", {}, t("schedule.frequency")), frequency);
    const timeField = h("div", {class: "setting-field"}, h("span", {}, t("schedule.time", {zone: status.timezone})),
      h("div", {class: "schedule-time"}, hour, h("span", {"aria-hidden": "true"}, ":"), minute));
    const powerField = h("div", {class: "setting-field schedule-power"}, h("span", {}, t("schedule.power")), power,
      h("small", {}, t("schedule.power_hint")));
    const creatorsField = h("details", {class: "schedule-creators"}, h("summary", {}, t("schedule.creators_summary")),
      creatorBoxes.length ? h("div", {class: "setting-toggles"}, creatorBoxes.map(item => item.node))
        : h("p", {class: "settings-section-description"}, t("schedule.creators_empty")));

    const node = h("section", {class: "settings-section schedule-settings"},
      h("h3", {}, t("schedule.title")),
      h("p", {class: "settings-section-description"},
        t("schedule.description", {zone: status.timezone})),
      h("dl", {class: "schedule-status"},
        h("div", {}, h("dt", {}, t("schedule.current")), h("dd", {}, status.enabled ? status.summary : t("schedule.disabled"))),
        h("div", {}, h("dt", {}, t("schedule.next_run")), h("dd", {}, status.next_run_at ? formatDate(status.next_run_at) : "—")),
        h("div", {}, h("dt", {}, t("schedule.last_result_label")), h("dd", {}, lastResultText(status))),
        h("div", {class: `schedule-background state-${status.background.state}`},
          h("dt", {}, t("schedule.background")), h("dd", {}, status.background.message))),
      status.note ? h("p", {class: "notice schedule-note"}, status.note) : null,
      enabledField,
      h("div", {class: "settings-grid"}, frequencyField, intervalField, weekdayField, timeField),
      monthField,
      powerField,
      creatorsField,
      preview,
      h("div", {class: "schedule-actions"}, runNow,
        h("span", {class: "settings-section-description"}, t("schedule.run_now_hint")),
        runBlockedNote),
      runFeedback);
    sync();
    const fields: TrackedField[] = [
      {node: enabledField, read: () => read().enabled},
      {node: frequencyField, read: () => read().frequency},
      {node: intervalField, read: () => read().interval},
      {node: weekdayField, read: () => read().weekday},
      {node: timeField, read: () => read().time},
      {node: monthField, read: () => read().month_day},
      {node: powerField, read: () => read().power},
      {node: creatorsField, read: () => read().creators},
    ];
    let locked = blocked;
    let runReason: string | null = null;
    const updateRun = (): void => {
      runNow.disabled = locked || runReason !== null;
      runBlockedNote.hidden = runReason === null;
      runBlockedNote.textContent = runReason ?? "";
    };
    const setRunBlocked = (reason: string | null): void => { runReason = reason; updateRun(); };
    const setLocked = (next: boolean): void => { locked = next; updateRun(); };
    return {node, read, fields, setRunBlocked, setLocked};
  }
}
