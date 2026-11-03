import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(
  new URL("../../src/fanbox_archiver/site_assets/app.js", import.meta.url), "utf8",
);
const start = source.indexOf("  // The zone in effect when the archive was exported");
const end = source.indexOf("  const displayYear");
assert.ok(start > 0 && end > start, "static reader date helpers not found");

function reader(timezone) {
  const context = vm.createContext({Intl, Date, Number, Object, String, data: {timezone}});
  vm.runInContext(`${source.slice(start, end)}\nthis.formatDate = formatDate;`, context);
  return context.formatDate;
}

test("static reader shows the exported Asia/Taipei zone in 24-hour time", () => {
  const formatDate = reader("Asia/Taipei");
  assert.equal(formatDate("2026-11-02T15:59:59+00:00"), "2026年11月02日 23:59");
  assert.equal(formatDate("2026-11-02T16:00:00Z"), "2026年11月03日 00:00");
  assert.equal(formatDate("2026-11-03T01:00:00+09:00"), "2026年11月03日 00:00");
  assert.equal(formatDate("2026-11-02T16:00:00"), "2026-11-02T16:00:00（時區未標示）");
  assert.equal(formatDate(null), "—");
});

test("static reader follows a different exported zone", () => {
  const formatDate = reader("Asia/Tokyo");
  assert.equal(formatDate("2026-11-02T15:30:00Z"), "2026年11月03日 00:30");
  assert.equal(reader(undefined)("2026-11-02T15:30:00Z"), "2026年11月02日 23:30");
});
