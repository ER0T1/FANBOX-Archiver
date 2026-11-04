namespace FanboxUI {
  /** Used only until the server provides the effective zone; development baseline. */
  const FALLBACK_TIME_ZONE = "Asia/Taipei";
  const buildFormatter = (zone: string): Intl.DateTimeFormat => new Intl.DateTimeFormat("en-CA", {
    timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  });
  let displayTimeZone = FALLBACK_TIME_ZONE;
  let dateTimeFormatter = buildFormatter(displayTimeZone);
  const explicitOffset = /(?:Z|[+-]\d{2}:?\d{2})$/i;
  // English month names and ordinals for `common.datetime` ("October 29th, 2026 20:28"); fixed
  // tables so the text never depends on the browser locale (same tables as the Python side).
  const MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August",
    "September", "October", "November", "December"] as const;
  const ordinalEn = (day: number): string => {
    const suffix = day % 100 >= 11 && day % 100 <= 13 ? "th" : ({1: "st", 2: "nd", 3: "rd"} as Record<number, string>)[day % 10] ?? "th";
    return `${day}${suffix}`;
  };

  /** Show every time in the zone the server resolved; never the browser's own zone. */
  export function setDisplayTimeZone(zone: string | null | undefined): void {
    if (!zone || zone === displayTimeZone) return;
    try {
      dateTimeFormatter = buildFormatter(zone);
      displayTimeZone = zone;
    } catch {
      // An unknown zone keeps the previous formatter rather than guessing.
    }
  }

  export function getDisplayTimeZone(): string {
    return displayTimeZone;
  }

  export function formatDate(value: string | null | undefined): string {
    if (!value) return "—";
    const text = String(value).trim();
    // Never let Date guess the host timezone for offset-less legacy values.
    if (!explicitOffset.test(text)) return t("common.timezone_unknown", {value: text});
    const date = new Date(text);
    if (Number.isNaN(date.valueOf())) return text;
    const parts = Object.fromEntries(dateTimeFormatter.formatToParts(date).map(part => [part.type, part.value]));
    const month = Number(parts.month), day = Number(parts.day);
    return t("common.datetime", {year: parts.year ?? "", month: parts.month ?? "", day: parts.day ?? "",
      hour: parts.hour ?? "", minute: parts.minute ?? "",
      month_name: MONTH_NAMES[month - 1] ?? "", day_ordinal: Number.isFinite(day) ? ordinalEn(day) : ""});
  }

  export function humanBytes(value: unknown): string {
    const bytes = Number(value ?? 0);
    if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
    const units = ["B", "KB", "MB", "GB", "TB"] as const;
    const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
    const scaled = bytes / (1024 ** index);
    const digits = index === 0 || scaled >= 100 ? 0 : scaled >= 10 ? 1 : 2;
    return `${scaled.toFixed(digits)} ${units[index]}`;
  }

  export function feeLabel(value: number | null | undefined): string {
    if (value === null || value === undefined) return t("common.fee_unknown");
    return Number(value) <= 0 ? t("common.fee_public") : t("common.fee_amount", {amount: Number(value)});
  }
}
