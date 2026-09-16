import { useMemo, useState } from "react";

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

export function App() {
  const [reason, setReason] = useState<ReasonCode | "">("");
  const canReject = reason !== "";
  const completeness = useMemo(
    () => ({ pd: "PD_UPLOADED", rd: "RD_PARTIAL", id: "ID_MISSING" }),
    [],
  );

  return (
    <main className="workspace">
      <header className="workspace__header">
        <h1>Инспектор ИИ</h1>
        <p>
          Каркас рабочего места. «Подтвердить» не в фокусе. Отклонение без{" "}
          <code>reason_code</code> недоступно.
        </p>
      </header>

      <section className="completeness" aria-label="Комплектность">
        <span>ПД: {completeness.pd}</span>
        <span>РД: {completeness.rd}</span>
        <span>ИД: {completeness.id}</span>
      </section>

      <div className="panes">
        <section className="pane" aria-label="expected">
          <h2>Ожидаемое</h2>
          <p className="placeholder">Кроп источника появится после CoordinateMapper.</p>
        </section>
        <section className="card" aria-label="Карточка правила">
          <h2>AR-41</h2>
          <p>Статус: CANDIDATE</p>
          <p>Доказательство: eg-stub</p>
          <div className="actions">
            <button type="button" disabled={!canReject}>
              Отклонить
            </button>
            <button type="button">Запросить уточнение</button>
            <button type="button">Подтвердить</button>
          </div>
          <label>
            Причина отклонения
            <select
              value={reason}
              onChange={(event) => setReason(event.target.value as ReasonCode | "")}
            >
              <option value="">не выбрана</option>
              {REASON_CODES.map((code) => (
                <option key={code} value={code}>
                  {code}
                </option>
              ))}
            </select>
          </label>
        </section>
        <section className="pane" aria-label="actual">
          <h2>Фактическое</h2>
          <p className="placeholder">Кроп источника появится после CoordinateMapper.</p>
        </section>
      </div>

      <section className="quality" aria-label="Качество данных">
        <h2>Не нарушения</h2>
        <ul>
          <li>MISSING_EVIDENCE — нет ИД</li>
          <li>NOT_APPLICABLE — стадия не применима</li>
        </ul>
      </section>
    </main>
  );
}
