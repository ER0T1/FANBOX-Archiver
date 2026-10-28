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
});

test("TypeScript core formats archive values", () => {
  assert.equal(ui.formatDate(null), "—");
  assert.equal(ui.humanBytes(12_137_079), "11.6 MB");
  assert.equal(ui.humanBytes(0), "0 B");
  assert.equal(ui.feeLabel(0), "全體公開");
  assert.equal(ui.feeLabel(300), "¥300");
  assert.equal(ui.feeLabel(null), "檔位未記錄");
});
