-- Схема БД по сводке ТЗ п. 10. Postgres — source of truth;
-- поисковый индекс, векторное и графовое представления перестраиваемы из неё.
-- Скелет: типы и ключевые ограничения зафиксированы, детали полей дополняются.

CREATE TABLE objects (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    address         TEXT,
    customer        TEXT,
    contractor      TEXT,
    permit_number   TEXT
);

CREATE TABLE files (
    id                  TEXT PRIMARY KEY,
    object_id           TEXT NOT NULL REFERENCES objects (id),
    doc_stage           TEXT NOT NULL CHECK (doc_stage IN ('PD', 'RD', 'ID')),
    discipline          TEXT,
    document_code       TEXT,
    revision            TEXT,
    approval_status     TEXT NOT NULL DEFAULT 'UNKNOWN'
                        CHECK (approval_status IN ('APPROVED', 'NOT_APPROVED', 'UNKNOWN')),
    approval_date       DATE,
    predecessor_id      TEXT REFERENCES files (id),
    successor_id        TEXT REFERENCES files (id),
    file_hash           CHAR(64) NOT NULL,
    file_path           TEXT NOT NULL,
    uploaded_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Один content hash может быть и РД, и ИД. Дедуп — в пределах стадии.
    UNIQUE (object_id, file_hash, doc_stage)
);

CREATE TABLE params (
    id              SERIAL PRIMARY KEY,
    code            VARCHAR(20) NOT NULL,
    matrix_version  TEXT NOT NULL,
    section         VARCHAR(50) NOT NULL,
    parameter_name  VARCHAR(255) NOT NULL,
    unit            VARCHAR(20),
    source_pd       TEXT,
    source_rd       TEXT,
    source_id       TEXT,
    trigger_logic   TEXT,                -- справочно; исполняется compiled_rule
    compiled_rule   JSONB NOT NULL,      -- rule.schema.json
    coverage        TEXT NOT NULL
                    CHECK (coverage IN ('executable', 'extractor_missing',
                                        'source_missing', 'advisory', 'not_applicable')),
    review_priority VARCHAR(20) CHECK (review_priority IN ('HIGH', 'MEDIUM', 'LOW')),
    data_type       VARCHAR(20),
    min_value       DOUBLE PRECISION,
    max_value       DOUBLE PRECISION,
    regex_pattern   VARCHAR(255),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (code, matrix_version)
);

CREATE TABLE evidence_groups (
    id              TEXT PRIMARY KEY,
    object_id       TEXT NOT NULL REFERENCES objects (id),
    rule_code       VARCHAR(20) NOT NULL,
    matrix_version  TEXT NOT NULL
);

CREATE TABLE evidence_fragments (
    id                  TEXT PRIMARY KEY,
    evidence_group_id   TEXT NOT NULL REFERENCES evidence_groups (id),
    file_id             TEXT NOT NULL REFERENCES files (id),
    stage               TEXT NOT NULL,
    sheet_page          TEXT NOT NULL,
    polygon_source      JSONB NOT NULL,
    polygon_norm        JSONB NOT NULL,   -- [0;1] после CropBox, MediaBox, Rotate
    extracted_value     TEXT,
    raw_token           TEXT NOT NULL,
    engine              TEXT NOT NULL,
    engine_version      TEXT NOT NULL,
    grounded            BOOLEAN NOT NULL,
    confidence          DOUBLE PRECISION,
    role                TEXT NOT NULL CHECK (role IN ('expected', 'actual', 'context'))
);

CREATE TABLE checks (
    id                  TEXT PRIMARY KEY,
    param_id            INTEGER NOT NULL REFERENCES params (id),
    object_id           TEXT NOT NULL REFERENCES objects (id),
    evidence_group_id   TEXT REFERENCES evidence_groups (id),
    expected_value      TEXT,
    actual_value        TEXT,
    delta               TEXT,
    completeness_status TEXT NOT NULL
                        CHECK (completeness_status IN ('UPLOADED', 'PARTIAL', 'MISSING')),
    finding_status      TEXT NOT NULL
                        CHECK (finding_status IN (
                            'CANDIDATE', 'CONFIRMED_VIOLATION', 'NEGATIVE_VERIFIED',
                            'AUTO_NO_DIFFERENCE', 'MISSING_EVIDENCE', 'NOT_APPLICABLE',
                            'NOT_COMPARABLE', 'LOW_QUALITY', 'ABSTAIN',
                            'CLARIFICATION_REQUIRED', 'SUSPICION'
                        )),
    review_priority     VARCHAR(20),
    inspector_id        TEXT,
    reason_code         TEXT,
    comment             TEXT,
    decided_at          TIMESTAMPTZ,
    CONSTRAINT violation_requires_human CHECK (
        finding_status <> 'CONFIRMED_VIOLATION'
        OR (inspector_id IS NOT NULL AND decided_at IS NOT NULL
            AND evidence_group_id IS NOT NULL
            AND comment IS NOT NULL AND btrim(comment) <> '')
    ),
    CONSTRAINT negative_requires_human CHECK (
        finding_status <> 'NEGATIVE_VERIFIED'
        OR (inspector_id IS NOT NULL AND decided_at IS NOT NULL
            AND reason_code IS NOT NULL AND btrim(reason_code) <> ''
            AND comment IS NOT NULL AND btrim(comment) <> '')
    ),
    CONSTRAINT candidate_requires_evidence CHECK (
        finding_status NOT IN (
            'CANDIDATE', 'CONFIRMED_VIOLATION', 'NEGATIVE_VERIFIED',
            'AUTO_NO_DIFFERENCE'
        )
        OR evidence_group_id IS NOT NULL
    ),
    CONSTRAINT rejection_requires_reason CHECK (
        finding_status <> 'NEGATIVE_VERIFIED' OR reason_code IS NOT NULL
    )
);

CREATE INDEX checks_object_status ON checks (object_id, finding_status);
CREATE INDEX files_object_stage ON files (object_id, doc_stage);

CREATE TABLE protocols (
    id                  TEXT PRIMARY KEY,
    object_id           TEXT NOT NULL REFERENCES objects (id),
    version             INTEGER NOT NULL,
    matrix_version      TEXT NOT NULL,
    dataset_version     TEXT NOT NULL,
    model_version       TEXT NOT NULL,
    input_manifest_hash TEXT NOT NULL,
    status              TEXT NOT NULL
                        CHECK (status IN (
                            'READY', 'VERIFYING',
                            'VERIFICATION_COMPLETED', 'PROTOCOL_FINALIZED'
                        )),
    payload             JSONB NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    finalized_at        TIMESTAMPTZ,
    supersedes_version  INTEGER,
    UNIQUE (object_id, version),
    CONSTRAINT finalized_has_timestamp CHECK (
        (status = 'PROTOCOL_FINALIZED' AND finalized_at IS NOT NULL)
        OR (status <> 'PROTOCOL_FINALIZED' AND finalized_at IS NULL)
    )
);

CREATE TABLE object_splits (
    object_id       TEXT NOT NULL REFERENCES objects (id),
    dataset_version TEXT NOT NULL,
    split           TEXT NOT NULL CHECK (split IN ('train', 'validation', 'test')),
    PRIMARY KEY (object_id, dataset_version)
);

CREATE TABLE dataset_items (
    id                  TEXT PRIMARY KEY,
    evidence_group_id   TEXT NOT NULL REFERENCES evidence_groups (id),
    gold_label          TEXT,
    expert_id           TEXT,
    reason_code         TEXT,
    dataset_version     TEXT NOT NULL,
    object_group_id     TEXT NOT NULL,
    object_id           TEXT NOT NULL REFERENCES objects (id),
    FOREIGN KEY (object_id, dataset_version)
        REFERENCES object_splits (object_id, dataset_version),
    UNIQUE (evidence_group_id, dataset_version)
);

CREATE TABLE audit_log (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    action      TEXT NOT NULL,
    object_id   TEXT,
    details     JSONB NOT NULL DEFAULT '{}',
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    ip_address  TEXT,
    user_agent  TEXT
);

CREATE INDEX audit_log_object_ts ON audit_log (object_id, timestamp);

-- Остальные таблицы сводки ТЗ п. 10 (Rejection_Log, Dispute_Log, Suspicions,
-- Logical_Rules, Normative_Base, ML_Retraining_Log, Monitoring_Metrics,
-- Model_Versions) добавляются миграциями по мере реализации модулей.
