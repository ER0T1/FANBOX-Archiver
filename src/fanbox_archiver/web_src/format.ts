namespace FanboxUI {
  const taipeiDateTime = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Taipei", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  });
  const explicitOffset = /(?:Z|[+-]\d{2}:?\d{2})$/i;

  export function formatDate(value: string | null | undefined): string {
    if (!value) return "—";
    const text = String(value).trim();
    // Never let Date guess the host timezone for offset-less legacy values.
    if (!explicitOffset.test(text)) return `${text}（時區未標示）`;
    const date = new Date(text);
    if (Number.isNaN(date.valueOf())) return text;
    const parts = Object.fromEntries(taipeiDateTime.formatToParts(date).map(part => [part.type, part.value]));
    return `${parts.year}年${parts.month}月${parts.day}日 ${parts.hour}:${parts.minute}`;
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
    if (value === null || value === undefined) return "檔位未記錄";
    return Number(value) <= 0 ? "全體公開" : `¥${Number(value).toLocaleString()}`;
  }
}
