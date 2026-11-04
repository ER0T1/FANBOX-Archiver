import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(
  new URL("../../src/fanbox_archiver/web_assets/core.js", import.meta.url),
  "utf8",
);
// The server serves /i18n.js with the zh-Hant catalog before core.js; mirror that here.
const messages = JSON.parse(readFileSync(
  new URL("../../src/fanbox_archiver/locales/zh-Hant.json", import.meta.url), "utf8"));
delete messages.$comment;
const warnings = [];
const context = vm.createContext({
  Intl, console: {warn: message => warnings.push(message)},
  FanboxI18n: {locale: "zh-Hant", intl: "zh-Hant", base: "zh-Hant", messages},
});
vm.runInContext(source, context);
const ui = context.FanboxUI;

test("i18n translates, pluralises, formats numbers and reports missing keys once", () => {
  assert.equal(ui.currentLocale(), "zh-Hant");
  assert.equal(ui.t("nav.posts"), "投稿");
  assert.equal(ui.t("posts.total", {count: 12345}), "12,345 篇備份");
  assert.equal(ui.t("posts.card_meta", {creator: "Alice", post_id: "1000", count: 2}), "Alice · Post 1000 · 2 個版本");
  assert.equal(ui.t("common.page_position", {page: 1}), "目前第 1 頁，共 {pages} 頁");
  assert.equal(ui.feeLabel(0), "全體公開");
  assert.equal(ui.feeLabel(1200), "¥1,200");
  assert.equal(ui.feeLabel(null), "檔位未記錄");
  assert.equal(ui.t("missing.key"), "missing.key");
  assert.equal(ui.t("missing.key"), "missing.key");
  assert.deepEqual(warnings, ["[i18n] missing key: missing.key"]);

  ui.setI18nCatalog({locale: "qps-ploc", intl: "zh-Hant", base: "zh-Hant",
    messages: {"posts.total": {other: "［{count} 篇備份····］"}}});
  assert.equal(ui.t("posts.total", {count: 3}), "［3 篇備份····］");
  ui.setI18nCatalog({locale: "zh-Hant", intl: "zh-Hant", base: "zh-Hant", messages});
});

test("TypeScript core creates independent initial state", () => {
  const first = ui.createInitialState();
  const second = ui.createInitialState();
  first.page = 8;
  assert.equal(second.page, 1);
  assert.equal(second.tag, "");
  assert.equal(second.view, "posts");
  assert.equal(second.postNavigation, null);
  assert.equal(second.activeJob, null);
  assert.equal(second.backupScreen, "form");
  assert.equal(second.backupJobId, null);
});

test("backup creator helpers filter selected items and summarize scope", () => {
  const creators = [
    {creator_id: "alice", name: "Alice"},
    {creator_id: "bob-studio", name: "Bob Studio"},
  ];
  assert.deepEqual(
    Array.from(ui.filterBackupCreators(creators, "BOB", ["alice"]), item => item.creator_id),
    ["bob-studio"],
  );
  assert.equal(ui.jobCreatorLabel({request: {creators: []}}, creators), "全部創作者");
  assert.equal(
    ui.jobCreatorLabel({request: {creators: ["alice"]}}, creators),
    "Alice（@alice）",
  );
  assert.equal(
    ui.jobCreatorLabel({request: {creators: ["alice", "bob-studio"]}}, creators),
    "2 位創作者",
  );
  assert.deepEqual(Array.from(ui.requestCreators({creator: "alice"})), ["alice"]);
});

test("TypeScript core identifies active jobs and labels global work", () => {
  const backup = {kind: "backup", status: "running", request: {mode: "full", dry_run: false}};
  const verify = {kind: "verify", status: "completed", request: {}};
  assert.equal(ui.isActiveJob(backup), true);
  assert.equal(ui.isActiveJob(verify), false);
  assert.equal(ui.jobLabel(backup), "完整備份");
  assert.equal(ui.jobLabel(verify), "封存完整性驗證");
  assert.equal(ui.jobLabel({kind: "backup", status: "running", request: {trigger: "schedule"}}), "排程備份");
});

test("TypeScript core formats archive values", () => {
  assert.equal(ui.formatDate(null), "—");
  assert.equal(ui.humanBytes(12_137_079), "11.6 MB");
  assert.equal(ui.humanBytes(0), "0 B");
  assert.equal(ui.feeLabel(0), "全體公開");
  assert.equal(ui.feeLabel(300), "¥300");
  assert.equal(ui.feeLabel(null), "檔位未記錄");
  assert.equal(ui.stopReasonLabel("limit_reached"), "已達下載上限");
  assert.equal(ui.stopReasonLabel("backfill_completed"), "歷史回補已完成");
  assert.equal(ui.verificationPhaseLabel("fancards"), "驗證粉絲卡");
  assert.equal(ui.verificationPhaseLabel("unknown"), "驗證封存");
});

test("TypeScript core shows Asia/Taipei across midnight and refuses naive values", () => {
  assert.equal(ui.formatDate("2026-11-02T15:59:59+00:00"), "2026年11月02日 23:59");
  assert.equal(ui.formatDate("2026-11-02T16:00:00Z"), "2026年11月03日 00:00");
  assert.equal(ui.formatDate("2026-11-03T01:00:00+09:00"), "2026年11月03日 00:00");
  assert.equal(ui.formatDate("2026-11-02T16:00:00"), "2026-11-02T16:00:00（時區未標示）");
  assert.equal(ui.formatDate("2026-11-02"), "2026-11-02（時區未標示）");
});

test("TypeScript core follows the server's display zone, never the browser's", () => {
  assert.equal(ui.getDisplayTimeZone(), "Asia/Taipei");
  ui.setDisplayTimeZone("Asia/Tokyo");
  assert.equal(ui.formatDate("2026-11-02T15:30:00Z"), "2026年11月03日 00:30");
  ui.setDisplayTimeZone("Not/AZone");
  assert.equal(ui.getDisplayTimeZone(), "Asia/Tokyo");
  ui.setDisplayTimeZone("Asia/Taipei");
  assert.equal(ui.formatDate("2026-11-02T15:30:00Z"), "2026年11月02日 23:30");
});

test("fan card perk status classes reject unknown API values", () => {
  assert.equal(ui.perkStatusClass("accessible"), "perk-status status-accessible");
  assert.equal(ui.perkStatusClass("unavailable"), "perk-status status-unavailable");
  assert.equal(ui.perkStatusClass("unexpected value"), "perk-status status-unknown");
});

test("colour helpers compute WCAG contrast and validate imported palettes", () => {
  assert.equal(ui.contrastRatio("#000000", "#ffffff").toFixed(2), "21.00");
  assert.equal(ui.contrastRatio("#ffffff", "#ffffff").toFixed(2), "1.00");
  const keys = ["bg", "accent"];
  const parsed = ui.parseColorExport(JSON.stringify({format: "fanbox-archiver-colors", version: 1,
    light: {accent: "#AA00FF"}, dark: {}}), keys);
  assert.equal(parsed.light.accent, "#aa00ff");
  assert.throws(() => ui.parseColorExport("{", keys), /JSON/);
  assert.throws(() => ui.parseColorExport(JSON.stringify({light: {}}), keys), /配色檔/);
  assert.throws(() => ui.parseColorExport(JSON.stringify({format: "fanbox-archiver-colors",
    light: {"font-family": "#000000"}}), keys), /不支援/);
  assert.throws(() => ui.parseColorExport(JSON.stringify({format: "fanbox-archiver-colors",
    light: {accent: "url(x)"}}), keys), /#RRGGBB/);
});
