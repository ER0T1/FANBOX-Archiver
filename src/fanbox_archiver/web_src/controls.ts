namespace FanboxUI {
  export interface SelectOption {
    value: string | number;
    label: string;
  }

  export interface CustomSelectOptions {
    id?: string;
    label: string;
    value?: string | number | null;
    options: SelectOption[];
    onChange?: (value: string) => void;
  }

  export interface CustomSelectElement extends HTMLDetailsElement {
    value: string;
  }

  export function customSelect(options: CustomSelectOptions): CustomSelectElement {
    const normalized = options.options.map(option => ({value: String(option.value), label: String(option.label)}));
    let selectedValue = String(options.value ?? normalized[0]?.value ?? "");
    const menuId = `${options.id || "select"}-menu-${Math.random().toString(36).slice(2, 9)}`;
    const summaryText = h("span", {class: "select-value"});
    const menu = h("div", {id: menuId, class: "select-menu", role: "listbox", "aria-label": options.label});
    const root = h("details", {class: "custom-select", id: options.id}) as CustomSelectElement;
    const summary = h("summary", {role: "combobox", "aria-label": options.label, "aria-controls": menuId,
      "aria-expanded": "false", "aria-haspopup": "listbox"}, summaryText);

    const update = (nextValue: string | number): void => {
      selectedValue = String(nextValue);
      const selected = normalized.find(option => option.value === selectedValue) ?? normalized[0];
      summaryText.textContent = selected?.label ?? "";
      for (const item of menu.querySelectorAll<HTMLButtonElement>('[role="option"]')) {
        const active = item.dataset.value === selectedValue;
        item.setAttribute("aria-selected", active ? "true" : "false");
        item.tabIndex = active ? 0 : -1;
      }
    };

    for (const option of normalized) {
      menu.append(h("button", {type: "button", role: "option", "data-value": option.value, onclick: () => {
        const changed = selectedValue !== option.value;
        update(option.value);
        root.open = false;
        summary.focus();
        if (changed) options.onChange?.(option.value);
      }}, option.label));
    }
    summary.addEventListener("keydown", event => {
      if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      root.open = true;
      const choices = [...menu.querySelectorAll<HTMLButtonElement>('[role="option"]')];
      const selectedIndex = Math.max(0, choices.findIndex(item => item.dataset.value === selectedValue));
      const targetIndex = event.key === "End" ? choices.length - 1 : event.key === "ArrowUp"
        ? Math.max(0, selectedIndex - 1) : event.key === "ArrowDown"
          ? Math.min(choices.length - 1, selectedIndex + 1) : 0;
      choices[targetIndex]?.focus();
    });
    menu.addEventListener("keydown", event => {
      const choices = [...menu.querySelectorAll<HTMLButtonElement>('[role="option"]')];
      const index = choices.indexOf(document.activeElement as HTMLButtonElement);
      if (event.key === "Escape") {
        event.preventDefault();
        root.open = false;
        summary.focus();
        return;
      }
      if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const targetIndex = event.key === "Home" ? 0 : event.key === "End" ? choices.length - 1
        : event.key === "ArrowDown" ? Math.min(choices.length - 1, index + 1) : Math.max(0, index - 1);
      choices[targetIndex]?.focus();
    });
    root.addEventListener("toggle", () => {
      summary.setAttribute("aria-expanded", root.open ? "true" : "false");
      if (root.open) menu.querySelector<HTMLElement>('[aria-selected="true"]')?.scrollIntoView({block: "nearest"});
    });
    Object.defineProperty(root, "value", {get: () => selectedValue, set: update});
    root.append(summary, menu);
    update(selectedValue);
    return root;
  }

  export function closeDropdownsOutside(target: EventTarget | null): void {
    for (const dropdown of document.querySelectorAll<HTMLDetailsElement>(".custom-select[open], .page-jump[open]")) {
      if (!(target instanceof Node) || !dropdown.contains(target)) dropdown.open = false;
    }
  }

  export function closeDropdownsAndFocus(): boolean {
    const dropdowns = [...document.querySelectorAll<HTMLDetailsElement>(".custom-select[open], .page-jump[open]")];
    for (const dropdown of dropdowns) {
      dropdown.open = false;
      dropdown.querySelector<HTMLElement>("summary")?.focus();
    }
    return dropdowns.length > 0;
  }

  export function renderError(error: unknown, onRetry: () => void): HTMLElement {
    const message = error instanceof Error ? error.message : String(error);
    return h("section", {class: "panel error"}, h("p", {class: "eyebrow"}, "ERROR"),
      h("h1", {}, "無法讀取封存"), h("p", {}, message),
      h("button", {type: "button", onclick: onRetry}, "重試"));
  }

  export function setActiveNavigation(nav: HTMLElement, view: View): void {
    const active = view === "creator" ? "creators" : view;
    for (const button of nav.querySelectorAll<HTMLButtonElement>("button")) {
      button.classList.toggle("active", button.dataset.view === active);
    }
  }

  export function setSearchState(search: HTMLInputElement, view: View, creatorTab: CreatorTab): void {
    search.disabled = ["backup", "maintenance", "settings"].includes(view)
      || (view === "creator" && creatorTab === "profile");
    search.placeholder = view === "posts" ? "搜尋標題、Post ID 或創作者…"
      : view === "creators" ? "搜尋創作者…"
      : view === "creator" && creatorTab === "fancards" ? "搜尋月份…"
      : view === "creator" && creatorTab === "posts" ? "搜尋此創作者的投稿…"
      : view === "backup" ? "備份執行期間可繼續閱讀封存"
      : view === "maintenance" ? "封存驗證與維護"
      : view === "settings" ? "本機設定" : "創作者個人資料";
  }
}
