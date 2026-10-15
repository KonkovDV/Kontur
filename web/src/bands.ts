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

export type ZoomBox = { x0: number; y0: number; x1: number; y1: number };
export type ZoomTransform = { scale: number; txPct: number; tyPct: number };

/** Zoom-to-bbox: масштаб и сдвиг (в % от кадра), чтобы bbox [0;1] с полями занял кадр. */
export function zoomTransform(box: ZoomBox, pad = 0.05, maxScale = 8): ZoomTransform {
  const clamp = (v: number) => Math.min(1, Math.max(0, v));
  const x0 = clamp(box.x0 - pad);
  const y0 = clamp(box.y0 - pad);
  const x1 = clamp(box.x1 + pad);
  const y1 = clamp(box.y1 + pad);
  const span = Math.max(x1 - x0, y1 - y0, 1e-6);
  const scale = Math.min(maxScale, Math.max(1, 1 / span));
  const visible = 1 / scale;
  const left = Math.min(Math.max(0, x0), 1 - visible);
  const top = Math.min(Math.max(0, y0), 1 - visible);
  return { scale, txPct: -left * 100, tyPct: -top * 100 };
}

/** Следующий/предыдущий элемент очереди (циклично); null при пустой очереди. */
export function stepQueue(ids: string[], current: string | null, delta: 1 | -1): string | null {
  if (ids.length === 0) return null;
  const at = current === null ? -1 : ids.indexOf(current);
  if (at < 0) return delta === 1 ? ids[0] : ids[ids.length - 1];
  return ids[(at + delta + ids.length) % ids.length];
}

export type ConfidenceChip = { bucket: "high" | "mid" | "low" | "abstain"; label: string };

/** Чип уверенности: текст + числовой бакет, не только цвет (CVD-safe). Порог не калиброван на скрытом сете. */
export function confidenceChip(confidence: number | null | undefined, status?: string): ConfidenceChip {
  if (status === "ABSTAIN" || status === "LOW_QUALITY" || confidence === null || confidence === undefined || Number.isNaN(confidence)) {
    return { bucket: "abstain", label: "⊘ воздержание" };
  }
  const pct = Math.round(Math.min(1, Math.max(0, confidence)) * 100);
  if (pct >= 90) return { bucket: "high", label: `▲ ≥90% (${pct}%)` };
  if (pct >= 70) return { bucket: "mid", label: `◆ 70–89% (${pct}%)` };
  return { bucket: "low", label: `▼ <70% (${pct}%)` };
}

/** Следующий после решения: null, если в очереди не осталось других элементов (не переоткрывать закрытое). */
export function nextAfterDecision(ids: string[], current: string): string | null {
  const rest = ids.filter((id) => id !== current);
  if (rest.length === 0) return null;
  return stepQueue(ids, current, 1);
}

/** Хоткеи не срабатывают в полях ввода, contentEditable и во время IME-композиции. */
export function hotkeysSuppressed(
  target: { tagName?: string; isContentEditable?: boolean } | null,
  isComposing: boolean,
): boolean {
  if (isComposing) return true;
  if (!target) return false;
  if (target.isContentEditable) return true;
  return target.tagName === "INPUT" || target.tagName === "SELECT" || target.tagName === "TEXTAREA";
}
