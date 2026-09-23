import type { ReactNode } from "react";

import { EvidencePane } from "./EvidencePane";
import {
  STAGE_PANES,
  fragmentByStage,
  toleranceLabel,
  type EvidenceCard,
  type EvidenceRole,
  type StagePane,
} from "./evidence";

const STAGE_TITLE: Record<(typeof STAGE_PANES)[number], string> = {
  PD: "ПД",
  RD: "РД",
  ID: "ИД",
};

const STAGE_ROLE: Record<(typeof STAGE_PANES)[number], EvidenceRole> = {
  PD: "expected",
  RD: "actual",
  ID: "context",
};

type Props = {
  card: EvidenceCard;
  pageImages?: Partial<Record<StagePane, string>>;
  children?: ReactNode;
};

export function EvidenceViewer({ card, pageImages, children }: Props) {
  const finding = card.finding;
  const decision = finding.inspector_decision;
  return (
    <div className="panes panes--stack">
      <div className="stage-row">
        {STAGE_PANES.map((stage) => (
          <EvidencePane
            key={stage}
            title={STAGE_TITLE[stage]}
            role={STAGE_ROLE[stage]}
            fragment={fragmentByStage(card, stage)}
            pageImageUrl={pageImages?.[stage]}
          />
        ))}
      </div>
      <section className="card" aria-label="Карточка правила">
        <p className="eyebrow">{card.rule.name ?? "правило матрицы"}</p>
        <h2>{finding.rule_code}</h2>
        <p>Статус: {finding.finding_status}</p>
        <p>Расхождение: {finding.disagreement_kind ?? "—"}</p>
        <p>Допуск: {toleranceLabel(card)}</p>
        <p>
          Значения: {String(finding.expected_value ?? "—")} →{" "}
          {String(finding.actual_value ?? "—")}
          {finding.delta !== undefined && finding.delta !== null
            ? ` (Δ ${String(finding.delta)})`
            : ""}
        </p>
        {finding.rationale ? <p className="rationale">{finding.rationale}</p> : null}
        {decision ? (
          <p>
            Решение: {decision.action} / {decision.inspector_id}
            {decision.reason_code ? ` / ${decision.reason_code}` : ""}
          </p>
        ) : (
          <p>Решение инспектора: нет (автомат не пишет CONFIRMED_VIOLATION)</p>
        )}
        <h3>Audit</h3>
        {card.audit.length === 0 ? (
          <p className="missing-hint">Журнал пуст для этой находки.</p>
        ) : (
          <ul className="audit">
            {card.audit.map((event, index) => (
              <li key={`${event.action}-${index}`}>
                {event.actor_id}: {event.action}
              </li>
            ))}
          </ul>
        )}
        <p className="gate-note">карточка не закрывает Gate K</p>
        {children}
      </section>
    </div>
  );
}
