namespace FanboxUI {
  /** A plural message maps CLDR categories to text; "other" is always present. */
  export type I18nMessage = string | Record<string, string>;

  export interface I18nCatalog {
    locale: string;
    intl: string;
    base: string;
    messages: Record<string, I18nMessage>;
  }

  const placeholder = /\{([a-z_][a-z0-9_]*)\}/g;
  // The server merges the zh-Hant fallback into every catalog, so a missing key here is a real gap:
  // it shows as the key itself (never blank) and is reported once.
  let catalog: I18nCatalog = {locale: "zh-Hant", intl: "zh-Hant", base: "zh-Hant", messages: {}};
  let numberFormat = new Intl.NumberFormat("zh-Hant");
  let pluralRules = new Intl.PluralRules("zh-Hant");
  const reported = new Set<string>();

  export function setI18nCatalog(value: unknown): void {
    if (!value || typeof value !== "object") return;
    const data = value as Partial<I18nCatalog>;
    if (!data.messages || typeof data.messages !== "object") return;
    catalog = {
      locale: String(data.locale || "zh-Hant"), intl: String(data.intl || "zh-Hant"),
      base: String(data.base || "zh-Hant"), messages: data.messages,
    };
    try {
      numberFormat = new Intl.NumberFormat(catalog.intl);
      pluralRules = new Intl.PluralRules(catalog.intl);
    } catch {
      numberFormat = new Intl.NumberFormat("zh-Hant");
      pluralRules = new Intl.PluralRules("zh-Hant");
    }
  }

  export function currentLocale(): string {
    return catalog.locale;
  }

  export function formatNumber(value: number): string {
    return numberFormat.format(value);
  }

  /** Translated text of `key`; numbers in `params` are formatted for the locale. */
  export function t(key: string, params: Record<string, string | number> = {}): string {
    let message = catalog.messages[key];
    if (message === undefined) {
      if (!reported.has(key)) {
        reported.add(key);
        globalThis.console?.warn?.(`[i18n] missing key: ${key}`);
      }
      return key;
    }
    if (typeof message !== "string") {
      const count = Number(params.count ?? 0);
      message = message[pluralRules.select(count)] ?? message.other ?? key;
    }
    return message.replace(placeholder, (match, name: string) => {
      const value = params[name];
      if (value === undefined) return match;
      return typeof value === "number" ? formatNumber(value) : value;
    });
  }

  /**
   * Translate static markup: `data-i18n="key"` sets the text, and
   * `data-i18n-attr="attr:key;attr:key"` sets attributes. The original zh-Hant text in the HTML
   * stays as the fallback when no catalog loaded.
   */
  export function applyI18n(root: ParentNode): void {
    if (!Object.keys(catalog.messages).length) return;
    for (const element of root.querySelectorAll<HTMLElement>("[data-i18n]")) {
      const key = element.dataset.i18n;
      if (key) element.textContent = t(key);
    }
    for (const element of root.querySelectorAll<HTMLElement>("[data-i18n-attr]")) {
      for (const pair of (element.dataset.i18nAttr ?? "").split(";")) {
        const [attribute, key] = pair.split(":").map(part => part.trim());
        if (attribute && key) element.setAttribute(attribute, t(key));
      }
    }
  }

  // /i18n.js (dynamic reader) runs before core.js and leaves the catalog on the window.
  setI18nCatalog((globalThis as {FanboxI18n?: unknown}).FanboxI18n);
}
