import { useEffect, useMemo, useState } from "react";

import { EvidenceViewer } from "./EvidenceViewer";
import { LiveWorkspace } from "./LiveWorkspace";
import demoCards from "./demo_cards.json";
import type { EvidenceCard } from "./evidence";
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

const DEMO_CARDS = demoCards as EvidenceCard[];
const DEMO_BANNER = import.meta.env.VITE_DEMO_BANNER ?? "";
const DEMO_TOKEN = import.meta.env.VITE_DEMO_TOKEN ?? "";

function qualityOf(status: string): FindingQuality | null {
  if (status === "CANDIDATE" || status === "MISSING_EVIDENCE") {
    return status;
  }
  return null;
}

if (DEMO_CARDS.length !== EXPECTED_FINDINGS) {
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
  const [mode, setMode] = useState<"live" | "recorder">(
    DEMO_TOKEN ? "live" : "recorder",
  );
  const [checkedIds, setCheckedIds] = useState<string[]>([]);
  const completeness = useMemo(
    () => ({ pd: "PD_UPLOADED", rd: "RD_PARTIAL", id: "ID_MISSING" }),
    [],
  );
  const findingCard = DEMO_CARDS[activeIndex];
  const inSession = startedAt !== null && finishedAt === null;
  const completed = finishedAt !== null;
  const quality = qualityOf(findingCard?.finding.finding_status ?? "");
  const isMissing = quality === "MISSING_EVIDENCE";
  const canReject = reason !== "" && inSession && quality === "CANDIDATE";

  function recordAuxiliaryClick() {
    if (inSession) setClicks((current) => current + 1);
  }

  function finishOrAdvance(nextDecisions: UsabilityDecision[], now: Date) {
    if (startedAt === null) return;
    setDecisions(nextDecisions);
    setClicks(0);
    setReason("");
    if (nextDecisions.length >= EXPECTED_FINDINGS) {
      setFinishedAt(now);
      setSession(
        buildUsabilityExport(participantId, startedAt, now, nextDecisions),
      );
      return;
    }
    const nextIndex = DEMO_CARDS.findIndex(
      (card) =>
        !nextDecisions.some(
          (item) => item.finding_id === card.finding.finding_id,
        ),
    );
    if (nextIndex >= 0) setActiveIndex(nextIndex);
  }

  function decide(action: DecisionAction) {
    if (!inSession || findingCard === undefined || startedAt === null) return;
    if (quality === null || !isActionAllowed(quality, action)) return;
    if (action === "REJECT" && reason === "") return;
    if (decisions.some((item) => item.finding_id === findingCard.finding.finding_id)) {
      return;
    }
    const now = new Date();
    const next: UsabilityDecision = {
      finding_id: findingCard.finding.finding_id,
      finding_status: quality,
      action,
      clicks_to_decision: clicks + 1,
      elapsed_ms: now.getTime() - startedAt.getTime(),
    };
    if (action === "REJECT") {
      next.reason_code = reason;
    }
    finishOrAdvance([...decisions, next], now);
  }

  function confirmChecked() {
    if (!inSession || startedAt === null || checkedIds.length === 0) return;
    const now = new Date();
    const extra: UsabilityDecision[] = [];
    for (const id of checkedIds) {
      if (decisions.some((item) => item.finding_id === id)) continue;
      if (extra.some((item) => item.finding_id === id)) continue;
      const card = DEMO_CARDS.find((item) => item.finding.finding_id === id);
      if (card === undefined || qualityOf(card.finding.finding_status) !== "CANDIDATE") {
        continue;
      }
      extra.push({
        finding_id: id,
        finding_status: "CANDIDATE",
        action: "CONFIRM",
        clicks_to_decision: 2,
        elapsed_ms: now.getTime() - startedAt.getTime(),
      });
    }
    if (extra.length === 0) return;
    setCheckedIds([]);
    finishOrAdvance([...decisions, ...extra], now);
  }

  useEffect(() => {
    if (!DEMO_TOKEN) return;
    const original = window.fetch.bind(window);
    window.fetch = (input, init) => {
      const headers = new Headers(init?.headers);
      if (!headers.has("Authorization")) {
        headers.set("Authorization", `Bearer ${DEMO_TOKEN}`);
      }
      return original(input, { ...init, headers });
    };
    return () => {
      window.fetch = original;
    };
  }, []);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (mode !== "recorder" || !inSession || event.metaKey || event.ctrlKey || event.altKey) {
        return;
      }
      const target = event.target;
      if (
        target instanceof HTMLElement &&
        (target.tagName === "INPUT" ||
          target.tagName === "SELECT" ||
          target.tagName === "TEXTAREA")
      ) {
        return;
      }
      const key = event.key.toLowerCase();
      if (key === "c") decide("CONFIRM");
      if (key === "r") decide("REJECT");
      if (key === "q") decide("REQUEST_CLARIFICATION");
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  return (
    <main className="workspace">
      {DEMO_BANNER ? <p className="demo-banner">{DEMO_BANNER}</p> : null}
      <nav className="mode-switch" aria-label="Режим экрана">
        <button
          type="button"
          aria-pressed={mode === "live"}
          onClick={() => setMode("live")}
        >
          Живой комплект
        </button>
        <button
          type="button"
          aria-pressed={mode === "recorder"}
          onClick={() => setMode("recorder")}
        >
          Учебный рекордер
        </button>
      </nav>
      {mode === "live" ? <LiveWorkspace token={DEMO_TOKEN} /> : null}
      {mode === "recorder" ? (
      <>
      <header className="workspace__header">
        <div>
          <h1>Инспектор ИИ</h1>
          <p>
            Учебный рекордер Gate K: пять карточек, три панели ПД / РД / ИД.
            Пустая стадия — нет фрагмента, не нарушение. Не закрывает гейт.
            «Подтвердить» не в фокусе. Клавиши C / R / Q.
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

      {inSession ? (
        <fieldset className="mass-confirm">
          <legend>Массовое подтверждение</legend>
          <p>
            Отметить можно только кандидатов. Отклонение остаётся на одной
            карточке и требует причину.
          </p>
          {DEMO_CARDS.map((card) => {
            const id = card.finding.finding_id;
            if (qualityOf(card.finding.finding_status) !== "CANDIDATE") return null;
            if (decisions.some((item) => item.finding_id === id)) return null;
            return (
              <label key={id}>
                <input
                  type="checkbox"
                  checked={checkedIds.includes(id)}
                  onChange={(event) => {
                    setCheckedIds((current) =>
                      event.target.checked
                        ? [...current, id]
                        : current.filter((item) => item !== id),
                    );
                  }}
                />
                {card.finding.rule_code}
              </label>
            );
          })}
          <button
            type="button"
            disabled={checkedIds.length === 0}
            onClick={confirmChecked}
          >
            Подтвердить отмеченные
          </button>
        </fieldset>
      ) : null}

      {findingCard && quality && inSession ? (
        <EvidenceViewer card={findingCard}>
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
                  Отклонить (R)
                </button>
                <button
                  type="button"
                  onClick={() => decide("REQUEST_CLARIFICATION")}
                >
                  Уточнить (Q)
                </button>
                <button
                  type="button"
                  className="action-secondary"
                  onClick={() => decide("CONFIRM")}
                >
                  Подтвердить (C)
                </button>
              </div>
            )}
            <small>
              Вспомогательных кликов: {clicks}. Кнопка решения добавит 1.
            </small>
        </EvidenceViewer>
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
      </>
      ) : null}
    </main>
  );
}
