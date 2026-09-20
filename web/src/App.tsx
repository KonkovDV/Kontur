import { useMemo, useState } from "react";

import {
  EXPECTED_FINDINGS,
  buildUsabilityExport,
  isActionAllowed,
  type DecisionAction,
  type FindingQuality,
  type UsabilityDecision,
  type UsabilityExport,
} from "./usability";

const REASON_CODES = [
  "WRONG_REVISION_SELECTED",
  "APPROVED_CHANGE_EXISTS",
  "OCR_ERROR",
  "LINKAGE_ERROR",
  "PARAMETER_NOT_APPLICABLE",
  "SOURCE_QUALITY",
  "OTHER",
] as const;

type ReasonCode = (typeof REASON_CODES)[number];

type DemoFinding = {
  id: string;
  rule: string;
  status: FindingQuality;
  kind: string;
  expected: string;
  actual: string;
};

const DEMO_FINDINGS: DemoFinding[] = [
  {
    id: "demo-number-1",
    rule: "PZ-001",
    status: "CANDIDATE",
    kind: "Числовая проверка",
    expected: "1 240 м²",
    actual: "1 255 м²",
  },
  {
    id: "demo-text-1",
    rule: "KR-055",
    status: "CANDIDATE",
    kind: "Текстовая проверка",
    expected: "C25/30",
    actual: "B25",
  },
  {
    id: "demo-missing-1",
    rule: "IOS4-078",
    status: "MISSING_EVIDENCE",
    kind: "Неполный комплект",
    expected: "Акт испытаний",
    actual: "ИД отсутствует",
  },
  {
    id: "demo-number-2",
    rule: "AR-041",
    status: "CANDIDATE",
    kind: "Числовая проверка",
    expected: "900 мм",
    actual: "850 мм",
  },
  {
    id: "demo-text-2",
    rule: "PZ-015",
    status: "CANDIDATE",
    kind: "Текстовая проверка",
    expected: "жилое",
    actual: "апартаменты",
  },
];

if (DEMO_FINDINGS.length !== EXPECTED_FINDINGS) {
  throw new Error("учебная очередь должна содержать ровно пять находок");
}

function downloadJson(filename: string, payload: object) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

export function App() {
  const [participantId, setParticipantId] = useState("");
  const [startedAt, setStartedAt] = useState<Date | null>(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const [reason, setReason] = useState<ReasonCode | "">("");
  const [clicks, setClicks] = useState(0);
  const [decisions, setDecisions] = useState<UsabilityDecision[]>([]);
  const [finishedAt, setFinishedAt] = useState<Date | null>(null);
  const [session, setSession] = useState<UsabilityExport | null>(null);
  const completeness = useMemo(
    () => ({ pd: "PD_UPLOADED", rd: "RD_PARTIAL", id: "ID_MISSING" }),
    [],
  );
  const finding = DEMO_FINDINGS[activeIndex];
  const inSession = startedAt !== null && finishedAt === null;
  const completed = finishedAt !== null;
  const isMissing = finding?.status === "MISSING_EVIDENCE";
  const canReject = reason !== "" && inSession && !isMissing;

  function recordAuxiliaryClick() {
    if (inSession) setClicks((current) => current + 1);
  }

  function decide(action: DecisionAction) {
    if (!inSession || finding === undefined || startedAt === null) return;
    if (!isActionAllowed(finding.status, action)) return;
    if (action === "REJECT" && reason === "") return;
    const now = new Date();
    const next: UsabilityDecision = {
      finding_id: finding.id,
      finding_status: finding.status,
      action,
      clicks_to_decision: clicks + 1,
      elapsed_ms: now.getTime() - startedAt.getTime(),
    };
    if (action === "REJECT") {
      next.reason_code = reason;
    }
    const nextDecisions = [...decisions, next];
    setDecisions(nextDecisions);
    setClicks(0);
    setReason("");
    if (nextDecisions.length === EXPECTED_FINDINGS) {
      setFinishedAt(now);
      setSession(
        buildUsabilityExport(participantId, startedAt, now, nextDecisions),
      );
    } else {
      setActiveIndex((current) => current + 1);
    }
  }

  return (
    <main className="workspace">
      <header className="workspace__header">
        <div>
          <h1>Инспектор ИИ</h1>
          <p>
            Учебный рекордер Gate K: пять карточек, счётчик кликов, JSON. Не
            закрывает гейт. «Подтвердить» не в фокусе.{" "}
            <code>MISSING_EVIDENCE</code> нельзя подтвердить как нарушение.
          </p>
        </div>
        <label className="participant">
          Код участника
          <input
            value={participantId}
            onChange={(event) => setParticipantId(event.target.value)}
            placeholder="inspector-01"
            disabled={completed}
          />
        </label>
      </header>

      <section className="completeness" aria-label="Комплектность">
        <span>ПД: {completeness.pd}</span>
        <span>РД: {completeness.rd}</span>
        <span>ИД: {completeness.id}</span>
        <strong>
          Прогресс: {decisions.length}/{EXPECTED_FINDINGS}
        </strong>
      </section>

      {startedAt === null ? (
        <section className="summary" aria-label="Старт сессии">
          <h2>Перед замером</h2>
          <p>
            Инструктаж не входит в 30 минут. Таймер стартует по кнопке ниже.
            Загрузка PDF в этом срезе не измеряется: очередь учебная.
          </p>
          <button type="button" onClick={() => setStartedAt(new Date())}>
            Начать учебную сессию
          </button>
        </section>
      ) : null}

      {finding && inSession ? (
        <div className="panes">
          <section className="pane" aria-label="expected">
            <h2>Ожидаемое</h2>
            <p className="evidence">{finding.expected}</p>
          </section>
          <section className="card" aria-label="Карточка правила">
            <p className="eyebrow">{finding.kind}</p>
            <h2>{finding.rule}</h2>
            <p>Статус: {finding.status}</p>
            <p>Доказательство: {finding.id}</p>
            {isMissing ? (
              <p className="missing-hint">
                Нет документа стадии — это не нарушение. Подтвердить и отклонить
                недоступны.
              </p>
            ) : (
              <label>
                Причина отклонения
                <select
                  value={reason}
                  onChange={(event) => {
                    setReason(event.target.value as ReasonCode | "");
                    recordAuxiliaryClick();
                  }}
                >
                  <option value="">не выбрана</option>
                  {REASON_CODES.map((code) => (
                    <option key={code} value={code}>
                      {code}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {isMissing ? (
              <div className="actions">
                <button
                  type="button"
                  onClick={() => decide("ACKNOWLEDGE_MISSING_EVIDENCE")}
                >
                  Принять: нет документа
                </button>
              </div>
            ) : (
              <div className="actions">
                <button
                  type="button"
                  disabled={!canReject}
                  onClick={() => decide("REJECT")}
                >
                  Отклонить
                </button>
                <button
                  type="button"
                  onClick={() => decide("REQUEST_CLARIFICATION")}
                >
                  Уточнить
                </button>
                <button type="button" onClick={() => decide("CONFIRM")}>
                  Подтвердить
                </button>
              </div>
            )}
            <small>
              Вспомогательных кликов: {clicks}. Кнопка решения добавит 1.
            </small>
          </section>
          <section className="pane" aria-label="actual">
            <h2>Фактическое</h2>
            <p className="evidence">{finding.actual}</p>
          </section>
        </div>
      ) : null}

      {session ? (
        <section className="summary" aria-live="polite">
          <h2>Сессия завершена</h2>
          <dl>
            <div>
              <dt>Время</dt>
              <dd>{session.duration_seconds} с</dd>
            </div>
            <div>
              <dt>Среднее кликов</dt>
              <dd>{session.metrics.mean_clicks_per_finding}</dd>
            </div>
            <div>
              <dt>Максимум кликов</dt>
              <dd>{session.metrics.max_clicks_per_finding}</dd>
            </div>
          </dl>
          <p className={session.metrics.within_three_clicks ? "pass" : "fail"}>
            ≤3 кликов на каждую: {session.metrics.within_three_clicks ? "да" : "нет"}
          </p>
          <p className={session.metrics.within_thirty_minutes ? "pass" : "fail"}>
            ≤30 минут: {session.metrics.within_thirty_minutes ? "да" : "нет"}
          </p>
          <p>JSON не закрывает Gate K.</p>
          <button
            type="button"
            onClick={() =>
              downloadJson(`usability-${session.participant_id}.json`, session)
            }
          >
            Скачать JSON-протокол
          </button>
        </section>
      ) : null}

      <section className="quality" aria-label="Ограничения замера">
        <h2>Важно</h2>
        <ul>
          <li>Это учебные данные, не TRAIN_PUBLIC и не скрытый тест.</li>
          <li>JSON не закрывает Gate K без пяти очных сессий инспекторов.</li>
          <li>MISSING_EVIDENCE не является нарушением.</li>
        </ul>
      </section>
    </main>
  );
}
