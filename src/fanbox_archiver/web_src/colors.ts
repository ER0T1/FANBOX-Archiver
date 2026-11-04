namespace FanboxUI {
  const COLOR_LABELS: Record<string, string> = {
    bg: "背景", surface: "卡片", "surface-2": "次要卡片", text: "文字", muted: "次要文字", line: "分隔線",
    accent: "強調色", "accent-soft": "強調淡色", blue: "藍（資訊）", green: "綠（成功）",
    yellow: "黃（警告）", red: "紅（錯誤）", purple: "紫",
  };
  const MODE_LABELS: Record<ColorMode, string> = {light: "亮色配色", dark: "暗色配色"};
  const HEX_COLOR = /^#[0-9a-f]{6}$/;
  const EXPORT_FORMAT = "fanbox-archiver-colors";
  /** [foreground, background, minimum ratio, label]; "white" is the text on accent buttons. */
  const CONTRAST_CHECKS: [string, string, number, string][] = [
    ["text", "bg", 4.5, "文字／背景"], ["text", "surface", 4.5, "文字／卡片"],
    ["text", "surface-2", 4.5, "文字／次要卡片"], ["muted", "surface", 3, "次要文字／卡片"],
    ["accent", "surface", 3, "強調色／卡片"], ["white", "accent", 3, "按鈕白字／強調色"],
    ["red", "surface", 3, "錯誤色／卡片"], ["green", "surface", 3, "成功色／卡片"],
  ];

  function hexToRgb(hex: string): [number, number, number] {
    const value = Number.parseInt(hex.slice(1), 16);
    return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
  }

  function rgbToHex(r: number, g: number, b: number): string {
    return `#${[r, g, b].map(part => Math.round(Math.min(255, Math.max(0, part))).toString(16).padStart(2, "0")).join("")}`;
  }

  function rgbToHsl(r: number, g: number, b: number): [number, number, number] {
    const [red, green, blue] = [r / 255, g / 255, b / 255];
    const max = Math.max(red, green, blue), min = Math.min(red, green, blue);
    const lightness = (max + min) / 2;
    if (max === min) return [0, 0, Math.round(lightness * 100)];
    const delta = max - min;
    const saturation = lightness > .5 ? delta / (2 - max - min) : delta / (max + min);
    const hue = max === red ? (green - blue) / delta + (green < blue ? 6 : 0)
      : max === green ? (blue - red) / delta + 2 : (red - green) / delta + 4;
    return [Math.round(hue * 60), Math.round(saturation * 100), Math.round(lightness * 100)];
  }

  function hslToRgb(h: number, s: number, l: number): [number, number, number] {
    const saturation = s / 100, lightness = l / 100;
    const chroma = (1 - Math.abs(2 * lightness - 1)) * saturation;
    const segment = (h % 360) / 60;
    const second = chroma * (1 - Math.abs(segment % 2 - 1));
    const [r, g, b] = segment < 1 ? [chroma, second, 0] : segment < 2 ? [second, chroma, 0]
      : segment < 3 ? [0, chroma, second] : segment < 4 ? [0, second, chroma]
      : segment < 5 ? [second, 0, chroma] : [chroma, 0, second];
    const offset = lightness - chroma / 2;
    return [(r + offset) * 255, (g + offset) * 255, (b + offset) * 255];
  }

  /** WCAG 2 contrast ratio between two #rrggbb colours. */
  export function contrastRatio(first: string, second: string): number {
    const luminance = (hex: string): number => {
      const [r, g, b] = hexToRgb(hex).map(part => {
        const channel = part / 255;
        return channel <= .03928 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4;
      }) as [number, number, number];
      return .2126 * r + .7152 * g + .0722 * b;
    };
    const [light, dark] = [luminance(first), luminance(second)].sort((a, b) => b - a) as [number, number];
    return (light + .05) / (dark + .05);
  }

  /** Validates an imported or pasted palette exactly like the server does. */
  export function parseColorExport(text: string, keys: string[]): ThemeColorSettings {
    let value: unknown;
    try { value = JSON.parse(text); } catch { throw new Error("檔案不是有效的 JSON。"); }
    if (!value || typeof value !== "object" || (value as {format?: unknown}).format !== EXPORT_FORMAT) {
      throw new Error("這不是 FANBOX Archiver 匯出的配色檔。");
    }
    const result: ThemeColorSettings = {light: {}, dark: {}};
    for (const mode of ["light", "dark"] as ColorMode[]) {
      const colors = (value as Record<string, unknown>)[mode] ?? {};
      if (typeof colors !== "object" || colors === null) throw new Error(`${MODE_LABELS[mode]}格式錯誤。`);
      for (const [key, color] of Object.entries(colors)) {
        if (!keys.includes(key)) throw new Error(`不支援的顏色名稱：${key}`);
        const normalized = String(color).trim().toLowerCase();
        if (!HEX_COLOR.test(normalized)) throw new Error(`顏色必須是 #RRGGBB：${key}`);
        result[mode][key] = normalized;
      }
    }
    return result;
  }

  function copy(colors: ThemeColorSettings): ThemeColorSettings {
    return {light: {...colors.light}, dark: {...colors.dark}};
  }

  function numberSlider(label: string, max: number, onValue: (value: number) => void): {
    node: HTMLElement; set(value: number): void;
  } {
    const range = h("input", {type: "range", min: 0, max, step: 1, "aria-label": label}) as HTMLInputElement;
    const number = h("input", {type: "number", min: 0, max, step: 1, "aria-label": `${label}數值`}) as HTMLInputElement;
    const emit = (source: HTMLInputElement): void => {
      const value = Math.min(max, Math.max(0, Math.round(Number(source.value) || 0)));
      (source === range ? number : range).value = String(value);
      onValue(value);
    };
    range.addEventListener("input", () => emit(range));
    number.addEventListener("change", () => emit(number));
    return {node: h("label", {class: "color-slider"}, h("span", {}, label), range, number),
      set(value) { range.value = String(value); number.value = String(value); }};
  }

  /** Allowlisted colour overrides per mode, with live preview, contrast hints and import/export. */
  export function colorEditor(data: SettingsResponse): {node: HTMLElement; read(): ThemeColorSettings} {
    const keys = data.theme_colors.keys;
    const defaults = data.theme_colors.defaults;
    const saved = copy(data.editable.display.colors);
    let working = copy(saved);
    // Start on the palette in effect now ("follow system" resolves to the OS light/dark setting).
    const theme = data.editable.display.theme;
    let mode: ColorMode = theme === "system"
      ? (window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light") : theme;

    const effective = (key: string): string => working[mode][key] ?? defaults[mode][key] ?? "#000000";
    const feedback = h("p", {class: "color-feedback", role: "status", "aria-live": "polite"});
    const warnings = h("ul", {class: "color-warnings"});
    const preview = h("div", {class: "color-preview", "aria-label": "配色預覽"},
      h("div", {class: "color-preview-card"},
        h("strong", {}, "預覽標題"), h("p", {}, "一般文字的樣子。"), h("p", {class: "color-preview-muted"}, "次要說明文字"),
        h("div", {class: "color-preview-row"},
          h("span", {class: "color-preview-button"}, "主要按鈕"), h("span", {class: "color-preview-chip"}, "強調標籤"),
          h("span", {class: "color-preview-link"}, "連結文字")),
        h("div", {class: "color-preview-row"}, ...["blue", "green", "yellow", "red", "purple"].map(key =>
          h("span", {class: "color-preview-status", "data-color": key}, COLOR_LABELS[key] ?? key)))));
    const rows = h("div", {class: "color-rows"});
    const modeButtons = (["light", "dark"] as ColorMode[]).map(value => h("button", {type: "button",
      class: "color-mode", "aria-pressed": value === mode,
      onclick: () => { mode = value; render(); }}, MODE_LABELS[value]));

    function refreshPreview(): void {
      for (const key of keys) preview.style.setProperty(`--${key}`, effective(key));
      warnings.replaceChildren(...CONTRAST_CHECKS.flatMap(([foreground, background, minimum, label]) => {
        const ratio = contrastRatio(foreground === "white" ? "#ffffff" : effective(foreground), effective(background));
        return ratio < minimum
          ? [h("li", {}, `${label} 對比度 ${ratio.toFixed(2)}:1，低於建議的 ${minimum}:1，可能不易閱讀。`)] : [];
      }));
      warnings.hidden = !warnings.childElementCount;
    }

    function colorRow(key: string): HTMLElement {
      const swatch = h("span", {class: "color-swatch", "aria-hidden": "true"});
      const code = h("code", {});
      const badge = h("small", {class: "color-badge"});
      const hex = h("input", {type: "text", maxlength: 7, spellcheck: "false", autocomplete: "off",
        "aria-label": `${COLOR_LABELS[key]} Hex`, class: "color-hex"}) as HTMLInputElement;
      let current = effective(key);
      const setColor = (value: string, source?: string): void => {
        current = value;
        if (value === defaults[mode][key]) delete working[mode][key];
        else working[mode][key] = value;
        update(source);
        refreshPreview();
      };
      const fromRgb = (index: number) => (value: number): void => {
        const rgb = hexToRgb(current);
        rgb[index] = value;
        setColor(rgbToHex(...rgb), "rgb");
      };
      const fromHsl = (index: number) => (value: number): void => {
        const hsl = rgbToHsl(...hexToRgb(current));
        hsl[index] = value;
        setColor(rgbToHex(...hslToRgb(...hsl)), "hsl");
      };
      const rgb = ["R", "G", "B"].map((label, index) => numberSlider(label, 255, fromRgb(index)));
      const hsl = [["色相", 360], ["彩度", 100], ["明暗", 100]].map(([label, max], index) =>
        numberSlider(label as string, max as number, fromHsl(index)));
      function update(source?: string): void {
        swatch.style.background = current;
        code.textContent = current;
        badge.textContent = working[mode][key] ? "已自訂" : "預設";
        badge.classList.toggle("custom", Boolean(working[mode][key]));
        if (source !== "hex") { hex.value = current; hex.removeAttribute("aria-invalid"); }
        if (source !== "rgb") hexToRgb(current).forEach((value, index) => rgb[index]?.set(value));
        if (source !== "hsl") rgbToHsl(...hexToRgb(current)).forEach((value, index) => hsl[index]?.set(value));
      }
      hex.addEventListener("input", () => {
        const value = hex.value.trim().toLowerCase();
        const normalized = value.startsWith("#") ? value : `#${value}`;
        if (HEX_COLOR.test(normalized)) setColor(normalized, "hex");
        else hex.setAttribute("aria-invalid", "true");
      });
      hex.addEventListener("blur", () => update());
      update();
      return h("details", {class: "color-row"},
        h("summary", {}, swatch, h("span", {class: "color-name"}, COLOR_LABELS[key] ?? key), code, badge),
        h("div", {class: "color-controls"},
          h("label", {class: "color-hex-field"}, h("span", {}, "Hex"), hex),
          h("div", {class: "color-slider-group"}, h("span", {class: "color-group-label"}, "RGB"), ...rgb.map(item => item.node)),
          h("div", {class: "color-slider-group"}, h("span", {class: "color-group-label"}, "色相／彩度／明暗"), ...hsl.map(item => item.node)),
          h("button", {type: "button", onclick: () => setColor(defaults[mode][key] ?? current)}, "恢復此色預設")));
    }

    function render(): void {
      modeButtons.forEach((button, index) => button.setAttribute("aria-pressed", String((["light", "dark"] as ColorMode[])[index] === mode)));
      preview.dataset.mode = mode;
      rows.replaceChildren(...keys.map(colorRow));
      refreshPreview();
    }

    const importInput = h("input", {type: "file", accept: "application/json,.json", hidden: true,
      onchange: async (event: Event) => {
        const input = event.currentTarget as HTMLInputElement;
        const file = input.files?.[0];
        input.value = "";
        if (!file) return;
        try {
          working = parseColorExport(await file.text(), keys);
          render();
          feedback.textContent = "已匯入配色；按「儲存設定」後才會套用。";
        } catch (error) {
          feedback.textContent = `無法匯入：${error instanceof Error ? error.message : String(error)}`;
        }
      }}) as HTMLInputElement;

    const node = h("section", {class: "settings-section color-editor"}, h("h3", {}, "自訂配色"),
      h("p", {class: "settings-section-description"},
        "只能調整下列顏色，未自訂的顏色沿用內建值；亮色與暗色各一組。儲存後套用到動態閱讀器與桌面程式，不套用到匯出的靜態網站。"),
      h("div", {class: "color-mode-switch", role: "group", "aria-label": "編輯哪一組配色"}, ...modeButtons),
      preview, warnings, rows,
      h("div", {class: "color-actions"},
        h("button", {type: "button", onclick: () => { working[mode] = {}; render();
          feedback.textContent = `${MODE_LABELS[mode]}已恢復內建值；按「儲存設定」後套用。`; }}, "恢復此組預設"),
        h("button", {type: "button", onclick: () => { working = copy(saved); render(); feedback.textContent = "已取消未儲存的配色修改。"; }},
          "取消未儲存修改"),
        h("button", {type: "button", onclick: () => {
          const blob = new Blob([JSON.stringify({format: EXPORT_FORMAT, version: 1, ...working}, null, 2) + "\n"],
            {type: "application/json"});
          const url = URL.createObjectURL(blob);
          const link = h("a", {href: url, download: "fanbox-archiver-colors.json", hidden: true});
          document.body.append(link);
          link.click();
          link.remove();
          setTimeout(() => URL.revokeObjectURL(url), 1000);
          feedback.textContent = "已匯出目前編輯中的配色（JSON，不含任何帳號資料）。";
        }}, "匯出配色"),
        h("button", {type: "button", onclick: () => importInput.click()}, "匯入配色"), importInput),
      feedback);
    render();
    return {node, read: () => copy(working)};
  }
}
