import assert from "node:assert/strict";
import test from "node:test";

// Node's type-stripping test runner requires the explicit TypeScript extension.
// @ts-expect-error TS5097 is intentional for this direct Node test import.
import { EpochLatchMap } from "../../src/lib/epoch-latch-map.ts";

test("an older observation cannot clear a newer latch for the same key", () => {
  const latches = new EpochLatchMap<string, string>();

  assert.equal(latches.epoch("tenant-1"), null);
  const olderEpoch = latches.mark("tenant-1", "older");
  const newerEpoch = latches.mark("tenant-1", "newer");

  assert.ok(newerEpoch > olderEpoch);
  assert.equal(latches.clear("tenant-1", olderEpoch), false);
  assert.equal(latches.epoch("tenant-1"), newerEpoch);
  assert.equal(latches.value("tenant-1"), "newer");
  assert.equal(latches.clear("tenant-1", newerEpoch), true);
  assert.equal(latches.epoch("tenant-1"), null);
});
