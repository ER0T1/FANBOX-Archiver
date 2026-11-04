namespace FanboxUI {
  interface DesktopTauriBridge {
    core: {
      invoke<T>(command: string): Promise<T>;
    };
  }

  interface DesktopWindow extends Window {
    __TAURI__?: DesktopTauriBridge;
    FanboxDesktop?: {showLaunchError(message: string): void};
  }

  interface DesktopMessages {
    locale: string;
    messages: Record<string, string>;
  }

  // The desktop pages load before the local server runs, so their text comes from the desktop
  // shell (the same catalogs, in the Windows display language) instead of /i18n.js.
  let desktopMessages: Record<string, string> = {};

  function desktopText(key: string, params: Record<string, string> = {}): string {
    const message = desktopMessages[key];
    if (message === undefined) return key;
    return message.replace(/\{([a-z_][a-z0-9_]*)\}/g, (match, name: string) => params[name] ?? match);
  }

  function applyDesktopMessages(data: DesktopMessages | null): void {
    if (data) {
      desktopMessages = data.messages;
      document.documentElement.lang = data.locale;
      for (const element of document.querySelectorAll<HTMLElement>("[data-desktop-i18n]")) {
        const key = element.dataset.desktopI18n;
        if (key && desktopMessages[key] !== undefined) element.textContent = desktopMessages[key];
      }
      for (const element of document.querySelectorAll<HTMLElement>("[data-desktop-i18n-label]")) {
        const key = element.dataset.desktopI18nLabel;
        if (key && desktopMessages[key] !== undefined) element.setAttribute("aria-label", desktopMessages[key]);
      }
    }
    // Without messages the base text stays: better than an empty page.
    document.body.classList.add("desktop-ready");
  }

  /** The recovery screen shown when the local server does not start (called by the shell). */
  function showLaunchError(message: string, bridge: DesktopTauriBridge): void {
    document.body.className = "desktop-bootstrap desktop-ready";
    const retry = h("button", {id: "retry-selection", type: "button", class: "primary"},
      desktopText("desktop.error_retry")) as HTMLButtonElement;
    const reason = h("p", {id: "launch-error", class: "desktop-status error"}, message);
    document.body.replaceChildren(h("main", {class: "desktop-onboarding desktop-error"},
      h("section", {class: "desktop-intro"},
        h("p", {class: "eyebrow"}, "STARTUP RECOVERY"),
        h("h1", {}, desktopText("desktop.error_title")),
        h("p", {}, desktopText("desktop.error_body"))),
      reason,
      h("div", {class: "desktop-error-actions"}, retry, h("small", {}, desktopText("desktop.error_kept")))));
    retry.addEventListener("click", async () => {
      retry.disabled = true;
      retry.textContent = desktopText("desktop.error_returning");
      try {
        await bridge.core.invoke("reset_desktop_selection");
      } catch (error) {
        retry.disabled = false;
        retry.textContent = desktopText("desktop.error_retry");
        reason.textContent = String(error);
      }
    });
  }

  async function startDesktopOnboarding(): Promise<void> {
    const root = document.getElementById("desktop-onboarding");
    const status = document.getElementById("desktop-status");
    if (!(root instanceof HTMLElement) || !(status instanceof HTMLElement)) return;
    const desktopWindow = window as DesktopWindow;
    const bridge = desktopWindow.__TAURI__;
    if (!bridge) {
      applyDesktopMessages(null);
      status.textContent = desktopText("desktop.needs_app") === "desktop.needs_app"
        ? "FANBOX Archiver desktop app required." : desktopText("desktop.needs_app");
      status.classList.add("error");
      return;
    }
    const statusElement = status;
    const tauriCore = bridge.core;
    desktopWindow.FanboxDesktop = {showLaunchError: message => showLaunchError(message, bridge)};
    try {
      applyDesktopMessages(await tauriCore.invoke<DesktopMessages>("desktop_messages"));
    } catch {
      applyDesktopMessages(null);
    }

    const buttons = [...root.querySelectorAll<HTMLButtonElement>("button[data-command]")];
    async function launch(command: string): Promise<void> {
      for (const button of buttons) button.disabled = true;
      statusElement.textContent = desktopText(command === "choose_existing_config" ? "desktop.picking_config"
        : command === "choose_archive_folder" ? "desktop.picking_folder" : "desktop.creating");
      statusElement.classList.remove("error");
      try {
        const result = await tauriCore.invoke<{config_path: string} | null>(command);
        if (result === null) {
          statusElement.textContent = desktopText("desktop.nothing_chosen");
          for (const button of buttons) button.disabled = false;
          return;
        }
        statusElement.textContent = desktopText("desktop.starting", {path: result.config_path});
      } catch (error) {
        statusElement.textContent = error instanceof Error ? error.message : String(error);
        statusElement.classList.add("error");
        for (const button of buttons) button.disabled = false;
      }
    }

    root.addEventListener("click", event => {
      const button = event.target instanceof Element
        ? event.target.closest<HTMLButtonElement>("button[data-command]") : null;
      if (button?.dataset.command) void launch(button.dataset.command);
    });
  }

  if (typeof document !== "undefined" && document.getElementById("desktop-onboarding")) {
    void startDesktopOnboarding();
  }
}
