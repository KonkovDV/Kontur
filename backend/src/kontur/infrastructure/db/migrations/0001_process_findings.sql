-- Миграция 0001: таблица находок процесса (GAP-PROCESS-FINDINGS, Gate L)
--
-- Находки и комплектность после рестарта восстанавливаются из этой таблицы.
-- Отдельна от `checks` (финальный вердикт): здесь хранятся автоматические находки
-- до решения инспектора (АDR-0001: автомат не пишет CONFIRMED_VIOLATION).

CREATE TABLE IF NOT EXISTS process_findings (
    process_id          TEXT        NOT NULL REFERENCES processes (id),
    finding_id          TEXT        NOT NULL,
    rule_code           TEXT        NOT NULL,
    finding_status      TEXT        NOT NULL
                        CHECK (finding_status IN (
                            'CANDIDATE', 'AUTO_NO_DIFFERENCE', 'MISSING_EVIDENCE',
                            'NOT_COMPARABLE', 'LOW_QUALITY', 'ABSTAIN',
                            'CLARIFICATION_REQUIRED', 'SUSPICION'
                        )),
    evidence_group_id   TEXT,
    expected_value      TEXT,
    actual_value        TEXT,
    delta               TEXT,
    rationale           TEXT        NOT NULL DEFAULT '',
    review_priority     TEXT        NOT NULL DEFAULT 'HIGH'
                        CHECK (review_priority IN ('HIGH', 'MEDIUM', 'LOW')),
    matrix_version      TEXT        NOT NULL,
    missing_stage       TEXT        CHECK (missing_stage IN ('PD', 'RD', 'ID')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (process_id, finding_id)
);

CREATE INDEX IF NOT EXISTS process_findings_process_id
    ON process_findings (process_id);

COMMENT ON TABLE process_findings IS
    'Снимок автоматических находок процесса. '
    'Дедуп: ключ (process_id, finding_id). '
    'После решения инспектора запись переходит в checks.';
