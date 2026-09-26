const assert = require("node:assert/strict");
const test = require("node:test");

const { bandOf, isCheckRefusal } = require("../dist/bands.cjs");

test("quality statuses land in attention, not in unchecked", () => {
  for (const status of [
    "LOW_QUALITY",
    "ABSTAIN",
    "NOT_COMPARABLE",
    "NOT_APPLICABLE",
    "CLARIFICATION_REQUIRED",
  ]) {
    assert.equal(bandOf(status), "attention");
  }
  assert.equal(bandOf("CANDIDATE"), "open");
  assert.equal(bandOf("SUSPICION"), "open");
  assert.equal(bandOf("CONFIRMED_VIOLATION"), "closed");
  assert.equal(bandOf("NEGATIVE_VERIFIED"), "closed");
  assert.equal(bandOf("MISSING_EVIDENCE"), "unchecked");
  assert.equal(bandOf("AUTO_NO_DIFFERENCE"), "unchecked");
});

test("a refusal is not a confirmation", () => {
  assert.equal(isCheckRefusal("LOW_QUALITY"), true);
  assert.equal(isCheckRefusal("ABSTAIN"), true);
  assert.equal(isCheckRefusal("CLARIFICATION_REQUIRED"), false);
  assert.equal(isCheckRefusal("CANDIDATE"), false);
});
