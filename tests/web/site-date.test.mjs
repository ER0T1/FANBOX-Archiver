import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(
  new URL("../../src/fanbox_archiver/site_assets/app.js", import.meta.url), "utf8",
);
const start = source.indexOf("  const taipeiDateTime");
const end = source.indexOf("  const taipeiYear");
assert.ok(start > 0 && end > start, "static reader date helpers not found");
const context = vm.createContext({Intl, Date, Number, Object, String});
vm.runInContext(`${source.slice(start, end)}\nthis.formatDate = formatDate;`, context);

test("static reader matches the GUI Asia/Taipei date contract", () => {
  assert.equal(context.formatDate("2026-11-02T15:59:59+00:00"), "2026年11月02日 23:59");
  assert.equal(context.formatDate("2026-11-02T16:00:00Z"), "2026年11月03日 00:00");
  assert.equal(context.formatDate("2026-11-03T01:00:00+09:00"), "2026年11月03日 00:00");
  assert.equal(context.formatDate("2026-11-02T16:00:00"), "2026-11-02T16:00:00（時區未標示）");
  assert.equal(context.formatDate(null), "—");
});
