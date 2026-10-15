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

const { zoomTransform, stepQueue } = require("../dist/bands.cjs");

test("zoomTransform keeps bbox inside the frame and never shrinks the page", () => {
  const full = zoomTransform({ x0: 0, y0: 0, x1: 1, y1: 1 });
  assert.equal(full.scale, 1);
  const z = zoomTransform({ x0: 0.8, y0: 0.85, x1: 0.95, y1: 0.95 });
  assert.ok(z.scale > 1 && z.scale <= 8);
  const left = -z.txPct / 100;
  const top = -z.tyPct / 100;
  assert.ok(left <= 0.8 && left + 1 / z.scale >= 0.95);
  assert.ok(top <= 0.85 && top + 1 / z.scale >= 0.95);
  assert.ok(left + 1 / z.scale <= 1 + 1e-9);
  assert.equal(zoomTransform({ x0: 0.5, y0: 0.5, x1: 0.5, y1: 0.5 }, 0).scale, 8);
});

test("stepQueue cycles and handles empty/unknown", () => {
  assert.equal(stepQueue([], null, 1), null);
  assert.equal(stepQueue(["a", "b"], null, 1), "a");
  assert.equal(stepQueue(["a", "b"], null, -1), "b");
  assert.equal(stepQueue(["a", "b"], "b", 1), "a");
  assert.equal(stepQueue(["a", "b"], "a", -1), "b");
});

const { confidenceChip } = require("../dist/bands.cjs");

test("confidenceChip buckets are textual and abstain wins", () => {
  assert.equal(confidenceChip(0.95).bucket, "high");
  assert.equal(confidenceChip(0.75).bucket, "mid");
  assert.equal(confidenceChip(0.2).bucket, "low");
  assert.equal(confidenceChip(0.99, "ABSTAIN").bucket, "abstain");
  assert.equal(confidenceChip(undefined).bucket, "abstain");
  assert.match(confidenceChip(0.95).label, /90/);
});

const { nextAfterDecision, hotkeysSuppressed } = require("../dist/bands.cjs");

test("confidenceChip: LOW_QUALITY/ABSTAIN status overrides high confidence", () => {
  assert.equal(confidenceChip(0.97, "LOW_QUALITY").bucket, "abstain");
  assert.match(confidenceChip(0.97, "ABSTAIN").label, /⊘/);
  assert.equal(confidenceChip(0.97, "CANDIDATE").bucket, "high");
});

test("nextAfterDecision: empty queue does not reopen closed finding", () => {
  assert.equal(nextAfterDecision(["a"], "a"), null);
  assert.equal(nextAfterDecision([], "a"), null);
  assert.equal(nextAfterDecision(["a", "b"], "a"), "b");
});

test("hotkeysSuppressed: inputs, contentEditable, IME", () => {
  assert.equal(hotkeysSuppressed({ tagName: "TEXTAREA" }, false), true);
  assert.equal(hotkeysSuppressed({ tagName: "DIV", isContentEditable: true }, false), true);
  assert.equal(hotkeysSuppressed({ tagName: "DIV" }, true), true);
  assert.equal(hotkeysSuppressed({ tagName: "DIV" }, false), false);
  assert.equal(hotkeysSuppressed(null, false), false);
});
