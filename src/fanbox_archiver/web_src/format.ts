namespace FanboxUI {
  const dateFormatter = new Intl.DateTimeFormat("zh-TW", {
    timeZone: "Asia/Taipei",
    dateStyle: "medium",
    timeStyle: "short",
  });

  export function formatDate(value: string | null | undefined): string {
    return value ? dateFormatter.format(new Date(value)) : "—";
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
