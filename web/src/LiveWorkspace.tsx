import { useEffect, useMemo, useState } from "react";

import { EvidenceViewer } from "./EvidenceViewer";
import {
  STAGE_PANES,
  fragmentByStage,
  type EvidenceCard,
  type StagePane,
} from "./evidence";
import {
  buildUsabilityExport,
  type DecisionAction,
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
type DocStageName = "PD" | "RD" | "ID";
type Band = "open" | "closed" | "unchecked";

type CatalogDocument = {
  file_id: string;
  filename: string;
  doc_stage: string;
  section: string | null;
  cipher: string | null;
  revision: string | null;
  approval_status: string;
  approval_basis: string;
  actuality: string;
};

type FindingRow = {
  finding_id: string;
  rule_code: string;
  finding_status: string;
  section: string | null;
  rationale: string;
  evidence_group_id: string | null;
};

type ProcessStatus = {
  process_id: string;
  process_state: string;
  completeness: { pd: string; rd: string; id: string };
  protocol_status: string;
  sync_state: string;
  counters: {
    candidates: number;
    confirmed_violations: number;
    negative_verified: number;
    missing_evidence: number;
    clarification_required: number;
    suspicions: number;
  };
};

type AuditEvent = {
  actor_id: string;
  action: string;
  payload: Record<string, unknown>;
};

const CLOSED = new Set(["CONFIRMED_VIOLATION", "NEGATIVE_VERIFIED"]);
const OPEN = new Set(["CANDIDATE", "SUSPICION"]);

function bandOf(status: string): Band {
  if (CLOSED.has(status)) return "closed";
  if (OPEN.has(status)) return "open";
  return "unchecked";
}

function queueRank(status: string): number {
  if (status === "CANDIDATE") return 0;
  if (status === "SUSPICION") return 1;
  return 2;
}

function reviewable(status: string): boolean {
  return status === "CANDIDATE" || status === "CLARIFICATION_REQUIRED";
}

export function sessionFromToken(token: string): { subject: string; objectId: string } {
  const principal = token.split("/")[0] ?? "";
  const at = principal.indexOf("@");
  if (at < 0) {
    return {
      subject: principal || "inspector-1",
      objectId: "OBJ-DEMO-COLD-START",
    };
  }
  return {
    subject: principal.slice(0, at) || "inspector-1",
    objectId: principal.slice(at + 1) || "OBJ-DEMO-COLD-START",
  };
}

function detailText(body: unknown, fallback: string): string {
  if (!body || typeof body !== "object" || !("detail" in body)) return fallback;
  const detail = (body as { detail: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) =>
        item && typeof item === "object" && "msg" in item
          ? String((item as { msg: unknown }).msg)
          : "",
      )
      .filter(Boolean);
    if (messages.length > 0) return messages.join("; ");
  }
  return fallback;
}

async function readJson<T>(response: Response): Promise<T> {
  const text = await response.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text) as unknown;
    } catch {
      body = null;
    }
  }
  if (!response.ok) {
    throw new Error(detailText(body, text || response.statusText));
  }
  return body as T;
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

function saveBlob(filename: string, blob: Blob) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

type Props = {
  token: string;
};

export function LiveWorkspace({ token }: Props) {
  const session = useMemo(() => sessionFromToken(token), [token]);
  const [files, setFiles] = useState<Partial<Record<DocStageName, File>>>({});
  const [processId, setProcessId] = useState<string | null>(null);
  const [processDraft, setProcessDraft] = useState("");
  const [documents, setDocuments] = useState<CatalogDocument[]>([]);
  const [findings, setFindings] = useState<FindingRow[]>([]);
  const [status, setStatus] = useState<ProcessStatus | null>(null);
  const [band, setBand] = useState<Band>("open");
  const [sectionFilter, setSectionFilter] = useState("");
  const [activeId, setActiveId] = useState<string | null>(null);
  const [card, setCard] = useState<EvidenceCard | null>(null);
  const [pageImages, setPageImages] = useState<Partial<Record<StagePane, string>>>({});
  const [etalonComment, setEtalonComment] = useState("");
  const [comment, setComment] = useState("");
  const [reason, setReason] = useState<ReasonCode | "">("");
  const [clicks, setClicks] = useState(0);
  const [startedAt, setStartedAt] = useState<Date | null>(null);
  const [decisions, setDecisions] = useState<UsabilityDecision[]>([]);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [protocolNote, setProtocolNote] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const sections = [
    ...new Set(findings.flatMap((item) => (item.section ? [item.section] : []))),
  ].sort((left, right) => left.localeCompare(right, "ru"));
  const visible = findings
    .filter((item) => bandOf(item.finding_status) === band)
    .filter((item) => sectionFilter === "" || item.section === sectionFilter)
    .sort(
      (left, right) =>
        queueRank(left.finding_status) - queueRank(right.finding_status) ||
        left.rule_code.localeCompare(right.rule_code, "ru"),
    );
  const counts = {
    open: findings.filter((item) => bandOf(item.finding_status) === "open").length,
    closed: findings.filter((item) => bandOf(item.finding_status) === "closed").length,
    unchecked: findings.filter((item) => bandOf(item.finding_status) === "unchecked")
      .length,
  };
  const active = findings.find((item) => item.finding_id === activeId) ?? null;
  const canReview = active !== null && reviewable(active.finding_status) && comment.trim() !== "";
  const canReject = canReview && reason !== "";
  const blockingQueue =
    (status?.counters.candidates ?? 0) > 0 || (status?.counters.suspicions ?? 0) > 0;

  async function refresh(nextProcessId: string) {
    const [listedDocs, listedFindings, nextStatus] = await Promise.all([
      readJson<{ documents: CatalogDocument[] }>(
        await fetch(`/api/v1/processes/${nextProcessId}/documents`),
      ),
      readJson<{ findings: FindingRow[] }>(
        await fetch(`/api/v1/processes/${nextProcessId}/findings`),
      ),
      readJson<ProcessStatus>(await fetch(`/api/v1/processes/${nextProcessId}/status`)),
    ]);
    setDocuments(listedDocs.documents);
    setFindings(listedFindings.findings);
    setStatus(nextStatus);
  }

  async function openFinding(findingId: string) {
    if (!processId) return;
    setActiveId(findingId);
    setClicks(1);
    setComment("");
    setReason("");
    setError("");
    const next = await readJson<EvidenceCard>(
      await fetch(`/api/v1/processes/${processId}/findings/${findingId}/evidence-card`),
    );
    setCard(next);
  }

  useEffect(() => {
    if (!processId || !card) return;
    let cancelled = false;
    const created: string[] = [];
    void (async () => {
      const next: Partial<Record<StagePane, string>> = {};
      for (const stage of STAGE_PANES) {
        const fragment = fragmentByStage(card, stage);
        if (!fragment) continue;
        const response = await fetch(
          `/api/v1/processes/${processId}/files/${fragment.document.file_id}/pages/${fragment.page}.png`,
        );
        if (!response.ok) continue;
        const url = URL.createObjectURL(await response.blob());
        created.push(url);
        next[stage] = url;
      }
      if (cancelled) {
        created.forEach((url) => URL.revokeObjectURL(url));
        return;
      }
      setPageImages(next);
    })();
    return () => {
      cancelled = true;
      created.forEach((url) => URL.revokeObjectURL(url));
      setPageImages({});
    };
  }, [processId, card]);

  async function uploadKit() {
    const chosen = (["PD", "RD", "ID"] as const).filter((stage) => files[stage]);
    if (chosen.length === 0) {
      setError("Выберите PDF хотя бы одной стадии.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      let current = processId;
      for (const stage of chosen) {
        const file = files[stage];
        if (!file) continue;
        const form = new FormData();
        form.set("object_id", session.objectId);
        form.set("doc_stage", stage);
        if (current) form.set("process_id", current);
        form.append("files", file);
        const receipt = await readJson<{ process_id: string }>(
          await fetch("/api/v1/documents/upload", { method: "POST", body: form }),
        );
        current = receipt.process_id;
        setProcessId(current);
      }
      if (current) {
        if (startedAt === null) setStartedAt(new Date());
        await refresh(current);
      }
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "загрузка не прошла");
    } finally {
      setBusy(false);
    }
  }

  async function loadTutorialKit() {
    setBusy(true);
    setError("");
    setCard(null);
    setActiveId(null);
    setPageImages({});
    try {
      const receipt = await readJson<{ process_id: string; note: string }>(
        await fetch("/api/v1/demo/kit", { method: "POST" }),
      );
      setProcessId(receipt.process_id);
      setProtocolNote(receipt.note);
      if (startedAt === null) setStartedAt(new Date());
      await refresh(receipt.process_id);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "учебный комплект не загружен");
    } finally {
      setBusy(false);
    }
  }

  async function assignEtalon(fileId: string) {
    if (!processId || etalonComment.trim() === "") return;
    setBusy(true);
    setError("");
    try {
      await readJson(
        await fetch(`/api/v1/processes/${processId}/revisions/${fileId}/select`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            inspector_id: session.subject,
            comment: etalonComment.trim(),
          }),
        }),
      );
      await refresh(processId);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "эталон не назначен");
    } finally {
      setBusy(false);
    }
  }

  function recordDecision(action: DecisionAction) {
    if (!active || startedAt === null) return;
    if (action === "ACKNOWLEDGE_MISSING_EVIDENCE") return;
    if (!reviewable(active.finding_status)) return;
    const now = new Date();
    const findingStatus =
      active.finding_status === "CLARIFICATION_REQUIRED"
        ? "CLARIFICATION_REQUIRED"
        : "CANDIDATE";
    const next: UsabilityDecision = {
      finding_id: active.finding_id,
      finding_status: findingStatus,
      action,
      clicks_to_decision: clicks + 1,
      elapsed_ms: now.getTime() - startedAt.getTime(),
    };
    if (action === "REJECT") next.reason_code = reason;
    setDecisions((current) => [
      ...current.filter((item) => item.finding_id !== active.finding_id),
      next,
    ]);
    setClicks(0);
  }

  async function decide(action: "CONFIRM" | "REJECT" | "REQUEST_CLARIFICATION") {
    if (!processId || !active || !canReview) return;
    if (action === "REJECT" && reason === "") return;
    setBusy(true);
    setError("");
    try {
      await readJson(
        await fetch(`/api/v1/findings/${active.finding_id}/review`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            action,
            inspector_id: session.subject,
            comment: comment.trim(),
            ...(action === "REJECT" ? { reason_code: reason } : {}),
          }),
        }),
      );
      recordDecision(action);
      await refresh(processId);
      await openFinding(active.finding_id);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "решение не принято");
    } finally {
      setBusy(false);
    }
  }

  async function postProcess(
    id: string,
    path: "verify" | "complete" | "finalize",
  ): Promise<ProcessStatus> {
    return readJson<ProcessStatus>(
      await fetch(`/api/v1/processes/${id}/${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ inspector_id: session.subject }),
      }),
    );
  }

  async function finalizeProtocol() {
    if (!processId) return;
    if (blockingQueue) {
      setError("сначала закройте кандидатов и подозрения");
      return;
    }
    setBusy(true);
    setError("");
    setProtocolNote("");
    try {
      let state = status?.process_state;
      if (state === "READY") {
        state = (await postProcess(processId, "verify")).process_state;
      }
      if (state === "VERIFYING") {
        state = (await postProcess(processId, "complete")).process_state;
      }
      if (state === "COMPLETED") {
        await postProcess(processId, "finalize");
      }
      const protocol = await readJson<object>(
        await fetch(`/api/v1/processes/${processId}/protocol`),
      );
      downloadJson(`protocol-${processId}.json`, protocol);
      const log = await readJson<{ events: AuditEvent[] }>(
        await fetch(`/api/v1/processes/${processId}/audit`),
      );
      downloadJson(`audit-${processId}.json`, log);
      setAudit(log.events);
      await refresh(processId);
      setProtocolNote("Протокол и журнал скачаны. РиН не подтверждался.");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "протокол не собран");
    } finally {
      setBusy(false);
    }
  }

  async function downloadProtocol(kind: "docx" | "xml" | "pdf") {
    if (!processId) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`/api/v1/processes/${processId}/protocol.${kind}`);
      if (!response.ok) {
        const body = (await response.json()) as { detail?: string };
        throw new Error(body.detail ?? "файл протокола не собран");
      }
      saveBlob(`protocol-${processId}.${kind}`, await response.blob());
      setProtocolNote(
        kind === "pdf"
          ? "PDF не ожидается."
          : `Скачан protocol.${kind}. Подтверждений РиН нет.`,
      );
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "файл протокола не собран");
    } finally {
      setBusy(false);
    }
  }

  async function queueRinMock() {
    if (!processId || status?.process_state !== "FINALIZED") return;
    setBusy(true);
    setError("");
    try {
      const queued = await readJson<string>(
        await fetch(`/api/v1/inspection/${processId}`, { method: "POST" }),
      );
      await refresh(processId);
      setProtocolNote(
        queued === "PENDING_SYNC"
          ? "Протокол в очереди выгрузки. ACK РиН нет."
          : `Состояние выгрузки: ${queued}. ACK РиН нет.`,
      );
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "очередь РиН не принята");
    } finally {
      setBusy(false);
    }
  }

  function downloadClicks() {
    if (startedAt === null || decisions.length === 0) return;
    const payload: UsabilityExport = buildUsabilityExport(
      session.subject,
      startedAt,
      new Date(),
      decisions,
      decisions.length,
    );
    downloadJson(`usability-live-${processId ?? "process"}.json`, payload);
  }

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (busy || event.metaKey || event.ctrlKey || event.altKey) return;
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
      if (key === "c") void decide("CONFIRM");
      if (key === "r") void decide("REJECT");
      if (key === "q") void decide("REQUEST_CLARIFICATION");
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  return (
    <>
      <header className="workspace__header">
        <div>
          <h1>Инспектор ИИ</h1>
          <p>
            Живой комплект объекта {session.objectId}. Инспектор {session.subject}.
            {token ? "" : " Токен демо не задан: запросы уйдут без Authorization."}
            Решение по одной находке. Массового подтверждения и массового отказа нет.
            Пустая стадия — не нарушение. Экран не закрывает Gate K.
          </p>
        </div>
      </header>

      {error ? (
        <p className="fail" role="alert">
          {error}
        </p>
      ) : null}

      <section className="summary" aria-label="Загрузка по стадии">
        <h2>Загрузка</h2>
        <div className="stage-upload">
          {(["PD", "RD", "ID"] as const).map((stage) => (
            <label key={stage}>
              {stage}
              <input
                type="file"
                accept="application/pdf,.pdf"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  setFiles((current) => ({ ...current, [stage]: file }));
                }}
              />
            </label>
          ))}
        </div>
        <button type="button" disabled={busy} onClick={() => void uploadKit()}>
          {busy ? "Считаю комплект…" : "Загрузить комплект"}
        </button>
        <button type="button" disabled={busy} onClick={() => void loadTutorialKit()}>
          Учебный комплект
        </button>
        {protocolNote ? <p>{protocolNote}</p> : null}
        <label>
          Открыть уже загруженный процесс
          <input
            value={processDraft}
            onChange={(event) => setProcessDraft(event.target.value)}
            placeholder="process_id"
          />
        </label>
        <button
          type="button"
          disabled={busy || processDraft.trim() === ""}
          onClick={() => {
            const next = processDraft.trim();
            setBusy(true);
            setError("");
            setCard(null);
            setActiveId(null);
            setPageImages({});
            setProcessId(next);
            if (startedAt === null) setStartedAt(new Date());
            void refresh(next)
              .catch((exc: unknown) => {
                setError(exc instanceof Error ? exc.message : "процесс не открыт");
              })
              .finally(() => setBusy(false));
          }}
        >
          Открыть процесс
        </button>
      </section>

      {status ? (
        <section className="completeness" aria-label="Комплектность">
          <span>ПД: {status.completeness.pd}</span>
          <span>РД: {status.completeness.rd}</span>
          <span>ИД: {status.completeness.id}</span>
          <span>Процесс: {status.process_state}</span>
          <span>Протокол: {status.protocol_status}</span>
          <strong>
            РиН mock: {status.sync_state}. ACK нет.
          </strong>
        </section>
      ) : null}

      {documents.length > 0 ? (
        <section className="summary" aria-label="Комплект">
          <h2>Комплект</h2>
          <p>
            Назначить эталоном можно, пока процесс в READY и по находкам ещё нет
            решений. Штамп «не утв.» этой кнопкой не перекрывается.
          </p>
          <label>
            Комментарий к назначению эталона
            <input
              value={etalonComment}
              onChange={(event) => setEtalonComment(event.target.value)}
            />
          </label>
          <table className="kit">
            <thead>
              <tr>
                <th>Стадия</th>
                <th>Файл</th>
                <th>Шифр</th>
                <th>Редакция</th>
                <th>Утверждение</th>
                <th>Актуальность</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {documents.map((item) => (
                <tr key={item.file_id}>
                  <td>{item.doc_stage}</td>
                  <td>{item.filename}</td>
                  <td>{item.cipher ?? "—"}</td>
                  <td>{item.revision ?? "—"}</td>
                  <td>
                    {item.approval_status} / {item.approval_basis}
                  </td>
                  <td>{item.actuality}</td>
                  <td>
                    <button
                      type="button"
                      disabled={
                        busy ||
                        status?.process_state !== "READY" ||
                        item.approval_status === "NOT_APPROVED" ||
                        etalonComment.trim() === ""
                      }
                      onClick={() => void assignEtalon(item.file_id)}
                    >
                      Назначить эталоном
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}

      {findings.length > 0 ? (
        <section className="summary" aria-label="Находки">
          <h2>Находки</h2>
          <div className="band" role="tablist">
            <button type="button" aria-pressed={band === "closed"} onClick={() => setBand("closed")}>
              Закрыто {counts.closed}
            </button>
            <button type="button" aria-pressed={band === "open"} onClick={() => setBand("open")}>
              Осталось {counts.open}
            </button>
            <button
              type="button"
              aria-pressed={band === "unchecked"}
              onClick={() => setBand("unchecked")}
            >
              Не проверялось {counts.unchecked}
            </button>
          </div>
          <label>
            Раздел матрицы
            <select
              value={sectionFilter}
              onChange={(event) => setSectionFilter(event.target.value)}
            >
              <option value="">все</option>
              {sections.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <ul className="finding-list">
            {visible.map((item) => (
              <li key={item.finding_id}>
                <button
                  type="button"
                  className={item.finding_id === activeId ? "is-active" : undefined}
                  onClick={() => void openFinding(item.finding_id)}
                >
                  {item.rule_code}
                  {item.section ? ` · ${item.section}` : ""} · {item.finding_status}
                  {item.rationale ? ` · ${item.rationale}` : ""}
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {card && active ? (
        <EvidenceViewer card={card} pageImages={pageImages}>
          {active.finding_status === "MISSING_EVIDENCE" ? (
            <p className="missing-hint">
              Нет документа стадии — это не нарушение. Подтвердить нельзя.
            </p>
          ) : null}
          {active.finding_status === "SUSPICION" ? (
            <p className="missing-hint">
              Подозрение блокирует финализацию. Кнопки решения для него нет.
            </p>
          ) : null}
          {reviewable(active.finding_status) ? (
            <>
              <label>
                Комментарий инспектора
                <textarea
                  value={comment}
                  onChange={(event) => setComment(event.target.value)}
                />
              </label>
              <label>
                Причина отклонения
                <select
                  value={reason}
                  onChange={(event) => {
                    setReason(event.target.value as ReasonCode | "");
                    setClicks((current) => current + 1);
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
              <div className="actions">
                <button
                  type="button"
                  disabled={busy || !canReject}
                  onClick={() => void decide("REJECT")}
                >
                  Отклонить (R)
                </button>
                <button
                  type="button"
                  disabled={busy || !canReview}
                  onClick={() => void decide("REQUEST_CLARIFICATION")}
                >
                  Уточнить (Q)
                </button>
                <button
                  type="button"
                  className="action-secondary"
                  disabled={busy || !canReview}
                  onClick={() => void decide("CONFIRM")}
                >
                  Подтвердить (C)
                </button>
              </div>
              <small>Кликов до решения: {clicks}. Кнопка решения добавит 1.</small>
            </>
          ) : null}
        </EvidenceViewer>
      ) : null}

      {processId ? (
        <section className="summary" aria-label="Протокол">
          <h2>Протокол</h2>
          <p>
            Финализация ждёт, пока не останется кандидатов и подозрений. Уточнение
            и отсутствие документа финализацию не держат.
          </p>
          <p>
            Осталось кандидатов: {status?.counters.candidates ?? "—"}, подозрений:{" "}
            {status?.counters.suspicions ?? "—"}.
          </p>
          <button
            type="button"
            disabled={busy || blockingQueue}
            onClick={() => void finalizeProtocol()}
          >
            Собрать и скачать протокол
          </button>
          <button type="button" disabled={busy || !processId} onClick={() => void downloadProtocol("docx")}>
            Скачать DOCX
          </button>
          <button type="button" disabled={busy || !processId} onClick={() => void downloadProtocol("xml")}>
            Скачать XML
          </button>
          <button type="button" disabled={busy || !processId} onClick={() => void downloadProtocol("pdf")}>
            Скачать PDF
          </button>
          <p>PDF протокола нет: GAP-PROTOCOL-PDF. DOCX и XML собираются из того же JSON.</p>
          <button
            type="button"
            disabled={
              busy ||
              status?.process_state !== "FINALIZED" ||
              status.sync_state !== "NOT_REQUESTED"
            }
            onClick={() => void queueRinMock()}
          >
            Передать в РиН (mock)
          </button>
          {protocolNote ? <p>{protocolNote}</p> : null}
          {audit.length > 0 ? (
            <>
              <h3>Журнал процесса</h3>
              <ul className="audit">
                {audit.map((event, index) => (
                  <li key={`${event.action}-${index}`}>
                    {event.actor_id}: {event.action}
                  </li>
                ))}
              </ul>
            </>
          ) : null}
          <button
            type="button"
            disabled={decisions.length === 0}
            onClick={downloadClicks}
          >
            Скачать клики живого прогона
          </button>
          <p className="gate-note">JSON кликов не закрывает Gate K.</p>
        </section>
      ) : null}
    </>
  );
}
