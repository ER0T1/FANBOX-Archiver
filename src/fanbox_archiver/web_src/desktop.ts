namespace FanboxUI {
  interface DesktopTauriBridge {
    core: {
      invoke<T>(command: string): Promise<T>;
    };
  }

  interface DesktopWindow extends Window {
    __TAURI__?: DesktopTauriBridge;
  }

  function startDesktopOnboarding(): void {
    const root = document.getElementById("desktop-onboarding");
    const status = document.getElementById("desktop-status");
    if (!(root instanceof HTMLElement) || !(status instanceof HTMLElement)) return;
    const bridge = (window as DesktopWindow).__TAURI__;
    if (!bridge) {
      status.textContent = "此頁面必須由 FANBOX Archiver 桌面程式開啟。";
      status.classList.add("error");
      return;
    }
    const statusElement = status;
    const tauriCore = bridge.core;

    const buttons = [...root.querySelectorAll<HTMLButtonElement>("button[data-command]")];
    async function launch(command: string): Promise<void> {
      for (const button of buttons) button.disabled = true;
      statusElement.textContent = command === "choose_existing_config"
        ? "請選擇既有的 config.yaml…"
        : command === "choose_archive_folder" ? "請選擇既有的 FANBOX 封存資料夾…"
        : "正在建立新的本機資料…";
      statusElement.classList.remove("error");
      try {
        const result = await tauriCore.invoke<{config_path: string} | null>(command);
        if (result === null) {
          statusElement.textContent = "未選擇任何項目，你可以改用其他方式繼續。";
          for (const button of buttons) button.disabled = false;
          return;
        }
        statusElement.textContent = `正在啟動本機伺服器：${result.config_path}`;
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
    startDesktopOnboarding();
  }
}
