export type Band = "open" | "closed" | "unchecked" | "attention";

const CLOSED = new Set(["CONFIRMED_VIOLATION", "NEGATIVE_VERIFIED"]);
const OPEN = new Set(["CANDIDATE", "SUSPICION"]);
const ATTENTION = new Set([
  "LOW_QUALITY",
  "ABSTAIN",
  "NOT_COMPARABLE",
  "NOT_APPLICABLE",
  "CLARIFICATION_REQUIRED",
]);
const REFUSAL = new Set(["LOW_QUALITY", "ABSTAIN", "NOT_COMPARABLE", "NOT_APPLICABLE"]);

export function bandOf(status: string): Band {
  if (CLOSED.has(status)) return "closed";
  if (OPEN.has(status)) return "open";
  if (ATTENTION.has(status)) return "attention";
  return "unchecked";
}

export function isCheckRefusal(status: string): boolean {
  return REFUSAL.has(status);
}
