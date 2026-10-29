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
  assert.equal(second.view, "posts");
  assert.equal(second.postNavigation, null);
  assert.equal(second.activeJob, null);
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
});
