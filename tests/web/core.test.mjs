import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(
  new URL("../../src/fanbox_archiver/web_assets/core.js", import.meta.url),
  "utf8",
);
const context = vm.createContext({Intl});
vm.runInContext(source, context);
const ui = context.FanboxUI;

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
});

test("fan card perk status classes reject unknown API values", () => {
  assert.equal(ui.perkStatusClass("accessible"), "perk-status status-accessible");
  assert.equal(ui.perkStatusClass("unavailable"), "perk-status status-unavailable");
  assert.equal(ui.perkStatusClass("unexpected value"), "perk-status status-unknown");
});
