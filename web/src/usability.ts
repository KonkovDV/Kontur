export type DecisionAction =
  | "CONFIRM"
  | "REJECT"
  | "REQUEST_CLARIFICATION"
  | "ACKNOWLEDGE_MISSING_EVIDENCE";

export type FindingQuality =
  | "CANDIDATE"
  | "MISSING_EVIDENCE"
  | "CLARIFICATION_REQUIRED";

export type UsabilityDecision = {
  finding_id: string;
  finding_status: FindingQuality;
  action: DecisionAction;
  reason_code?: string;
  clicks_to_decision: number;
  elapsed_ms: number;
};

export type UsabilityExport = {
  schema_version: "kontur-usability-v1";
  participant_id: string;
  session_started_at: string;
  session_finished_at: string;
  duration_seconds: number;
  decisions: UsabilityDecision[];
  closes_gate_k: false;
  teaching_data: true;
  metrics: {
    findings_completed: number;
    expected_findings: number;
    session_complete: boolean;
    mean_clicks_per_finding: number;
    max_clicks_per_finding: number;
    within_three_clicks: boolean;
    within_thirty_minutes: boolean;
  };
};

export const EXPECTED_FINDINGS = 5;
const THIRTY_MINUTES_S = 30 * 60;

export function allowedActions(status: FindingQuality): readonly DecisionAction[] {
  if (status === "MISSING_EVIDENCE") {
    return ["ACKNOWLEDGE_MISSING_EVIDENCE"];
  }
  return ["CONFIRM", "REJECT", "REQUEST_CLARIFICATION"];
}

export function isActionAllowed(
  status: FindingQuality,
  action: DecisionAction,
): boolean {
  return allowedActions(status).includes(action);
}

export function buildUsabilityExport(
  participantId: string,
  startedAt: Date,
  finishedAt: Date,
  decisions: UsabilityDecision[],
  expectedFindings: number = EXPECTED_FINDINGS,
): UsabilityExport {
  const clickTotal = decisions.reduce(
    (total, decision) => total + decision.clicks_to_decision,
    0,
  );
  const maxClicks = decisions.reduce(
    (maximum, decision) => Math.max(maximum, decision.clicks_to_decision),
    0,
  );
  const durationSeconds = Math.max(
    0,
    Math.round((finishedAt.getTime() - startedAt.getTime()) / 1000),
  );
  const sessionComplete = decisions.length === expectedFindings;
  const withinThree =
    sessionComplete &&
    decisions.every((decision) => decision.clicks_to_decision <= 3);
  return {
    schema_version: "kontur-usability-v1",
    participant_id: participantId.trim() || "anonymous",
    session_started_at: startedAt.toISOString(),
    session_finished_at: finishedAt.toISOString(),
    duration_seconds: durationSeconds,
    decisions,
    closes_gate_k: false,
    teaching_data: true,
    metrics: {
      findings_completed: decisions.length,
      expected_findings: expectedFindings,
      session_complete: sessionComplete,
      mean_clicks_per_finding:
        decisions.length === 0
          ? 0
          : Number((clickTotal / decisions.length).toFixed(2)),
      max_clicks_per_finding: maxClicks,
      within_three_clicks: withinThree,
      within_thirty_minutes: sessionComplete && durationSeconds <= THIRTY_MINUTES_S,
    },
  };
}
