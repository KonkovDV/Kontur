export type DecisionAction = "CONFIRM" | "REJECT" | "REQUEST_CLARIFICATION";

export type UsabilityDecision = {
  finding_id: string;
  action: DecisionAction;
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
  metrics: {
    findings_completed: number;
    mean_clicks_per_finding: number;
    max_clicks_per_finding: number;
    within_three_clicks: boolean;
    within_thirty_minutes: boolean;
  };
};

export function buildUsabilityExport(
  participantId: string,
  startedAt: Date,
  finishedAt: Date,
  decisions: UsabilityDecision[],
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
  return {
    schema_version: "kontur-usability-v1",
    participant_id: participantId.trim() || "anonymous",
    session_started_at: startedAt.toISOString(),
    session_finished_at: finishedAt.toISOString(),
    duration_seconds: durationSeconds,
    decisions,
    metrics: {
      findings_completed: decisions.length,
      mean_clicks_per_finding:
        decisions.length === 0 ? 0 : Number((clickTotal / decisions.length).toFixed(2)),
      max_clicks_per_finding: maxClicks,
      within_three_clicks: decisions.every(
        (decision) => decision.clicks_to_decision <= 3,
      ),
      within_thirty_minutes: durationSeconds <= 30 * 60,
    },
  };
}
