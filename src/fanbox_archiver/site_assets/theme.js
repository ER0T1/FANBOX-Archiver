(() => {
  "use strict";

  const STORAGE_KEY = "fanbox-theme";
  const THEMES = ["auto", "dark", "light"];
  const ICONS = {auto:"◐", dark:"☾", light:"☀"};
  const LABELS = {auto:"跟隨系統", dark:"深色", light:"淺色"};
  const channel = "BroadcastChannel" in window ? new BroadcastChannel("fanbox-theme") : null;
  // The theme chosen in the app's settings when this site was exported; a visitor's own choice wins.
  const DEFAULT_THEME = (() => {
    const value = document.querySelector('meta[name="fanbox-default-theme"]')?.getAttribute("content");
    return THEMES.includes(value) ? value : "auto";
  })();

  function urlTheme() {
    try {
      const value = new URL(location.href).searchParams.get("theme");
      return THEMES.includes(value) ? value : null;
    } catch (_) {
      return null;
    }
  }

  function storedTheme() {
    const linked = urlTheme();
    if (linked) return linked;
    try {
      const value = localStorage.getItem(STORAGE_KEY);
      return THEMES.includes(value) ? value : DEFAULT_THEME;
    } catch (_) {
      return DEFAULT_THEME;
    }
  }

  function updateLocation(theme) {
    try {
      const url = new URL(location.href);
      if (theme === DEFAULT_THEME) url.searchParams.delete("theme");
      else url.searchParams.set("theme", theme);
      history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
    } catch (_) {
      // Some file:// viewers restrict History API access.
    }
  }

  function updateLinks(theme) {
    document.querySelectorAll("a[href]").forEach(link => {
      try {
        const url = new URL(link.getAttribute("href"), location.href);
        if (!url.pathname.toLowerCase().endsWith(".html")) return;
        if (url.protocol !== location.protocol || (location.protocol !== "file:" && url.origin !== location.origin)) return;
        if (theme === DEFAULT_THEME) url.searchParams.delete("theme");
        else url.searchParams.set("theme", theme);
        link.href = url.href;
      } catch (_) {
        // Ignore malformed or non-navigation links.
      }
    });
  }

  function updateButtons(theme) {
    document.querySelectorAll("[data-theme-toggle]").forEach(button => {
      button.textContent = ICONS[theme];
      button.title = `目前：${LABELS[theme]}；點擊切換主題`;
      button.setAttribute("aria-label", button.title);
    });
  }

  function apply(theme = storedTheme()) {
    const value = THEMES.includes(theme) ? theme : DEFAULT_THEME;
    document.documentElement.dataset.theme = value;
    updateLocation(value);
    updateButtons(value);
    updateLinks(value);
    return value;
  }

  function cycle() {
    const current = apply();
    const next = THEMES[(THEMES.indexOf(current) + 1) % THEMES.length];
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch (_) {
      // file:// environments can disable storage; the current page still switches.
    }
    apply(next);
    if (channel) channel.postMessage(next);
  }

  function bindAll() {
    document.querySelectorAll("[data-theme-toggle]").forEach(button => {
      if (button.dataset.themeBound === "true") return;
      button.dataset.themeBound = "true";
      button.addEventListener("click", cycle);
    });
    apply();
  }

  window.FanboxTheme = {apply, bindAll, cycle, current: storedTheme};
  apply();
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bindAll);
  else bindAll();
  window.addEventListener("pageshow", bindAll);
  window.addEventListener("focus", () => apply());
  window.addEventListener("storage", event => {
    if (event.key === STORAGE_KEY || event.key === null) {
      apply(THEMES.includes(event.newValue) ? event.newValue : DEFAULT_THEME);
    }
  });
  if (channel) {
    channel.addEventListener("message", event => {
      if (THEMES.includes(event.data)) apply(event.data);
    });
  }
})();
