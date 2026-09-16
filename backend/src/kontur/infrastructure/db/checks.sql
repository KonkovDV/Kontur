-- Пост-проверки схемы: ограничения обязаны срабатывать, а не просто существовать.
-- Запуск: psql -v ON_ERROR_STOP=1 -f schema.sql -f checks.sql
--
-- Приём один и тот же: выполняем запрещённое действие; если СУБД его не
-- остановила, поднимаем SQLSTATE KNT99, который не перехватывается и валит
-- скрипт. Ожидаемый отказ перехватывается точечно — по коду, а не «по любой
-- ошибке», иначе тест зеленел бы и от опечатки в имени таблицы.

BEGIN;

INSERT INTO objects (id, name) VALUES ('obj-check', 'Объект для проверок схемы');
INSERT INTO evidence_groups (id, object_id, rule_code, matrix_version)
VALUES ('eg-check', 'obj-check', 'PZ-001', 'draft-0');
INSERT INTO object_splits (object_id, dataset_version, split)
VALUES ('obj-check', 'v1', 'train');
INSERT INTO protocols (
    id, object_id, version, matrix_version, dataset_version, model_version,
    input_manifest_hash, status, payload, finalized_at
) VALUES (
    'proto-check', 'obj-check', 1, 'draft-0', 'v1', 'm-0',
    'hash', 'PROTOCOL_FINALIZED', '{}'::jsonb, now()
);

-- 1. Финализированный протокол неизменяем.
DO $$
BEGIN
    UPDATE protocols SET payload = '{"tampered": true}'::jsonb WHERE id = 'proto-check';
    RAISE EXCEPTION 'финализированный протокол оказался изменяемым'
        USING ERRCODE = 'KNT99';
EXCEPTION
    WHEN SQLSTATE 'KNT01' THEN NULL;
END;
$$;

-- 2. Финализированный протокол не удаляется.
DO $$
BEGIN
    DELETE FROM protocols WHERE id = 'proto-check';
    RAISE EXCEPTION 'финализированный протокол удалился' USING ERRCODE = 'KNT99';
EXCEPTION
    WHEN SQLSTATE 'KNT01' THEN NULL;
END;
$$;

-- 3. Отмена финализации не может подменить payload в том же UPDATE.
DO $$
BEGIN
    PERFORM set_config('kontur.unfinalize_reason', 'ошибочная редакция', true);
    UPDATE protocols
       SET status = 'VERIFICATION_COMPLETED',
           finalized_at = NULL,
           payload = '{"tampered": true}'::jsonb
     WHERE id = 'proto-check';
    RAISE EXCEPTION 'отмена финализации изменила содержимое протокола'
        USING ERRCODE = 'KNT99';
EXCEPTION
    WHEN SQLSTATE 'KNT01' THEN
        PERFORM set_config('kontur.unfinalize_reason', '', true);
END;
$$;

-- 4. Отмена финализации возможна, но только с причиной и без правки payload.
DO $$
BEGIN
    PERFORM set_config('kontur.unfinalize_reason', 'ошибочно выбрана редакция РД', true);
    UPDATE protocols
       SET status = 'VERIFICATION_COMPLETED', finalized_at = NULL
     WHERE id = 'proto-check';
    PERFORM set_config('kontur.unfinalize_reason', '', true);
    IF (SELECT status FROM protocols WHERE id = 'proto-check') <> 'VERIFICATION_COMPLETED' THEN
        RAISE EXCEPTION 'отмена финализации супервизором не прошла' USING ERRCODE = 'KNT99';
    END IF;
    IF (SELECT payload FROM protocols WHERE id = 'proto-check') <> '{}'::jsonb THEN
        RAISE EXCEPTION 'payload изменился при отмене финализации' USING ERRCODE = 'KNT99';
    END IF;
END;
$$;

-- Протокол снова финализирован: дальнейшие проверки выгрузки требуют живой печати.
UPDATE protocols
   SET status = 'PROTOCOL_FINALIZED', finalized_at = now()
 WHERE id = 'proto-check';

-- 5. Машинный статус не может быть GOLD-меткой (ТЗ п. 9.4).
DO $$
BEGIN
    INSERT INTO dataset_items (
        id, evidence_group_id, gold_label, expert_id, reason_code,
        dataset_version, object_group_id, object_id
    ) VALUES (
        'ds-auto', 'eg-check', 'AUTO_NO_DIFFERENCE', 'exp-1', NULL,
        'v1', 'grp-1', 'obj-check'
    );
    RAISE EXCEPTION 'AUTO_NO_DIFFERENCE попал в GOLD' USING ERRCODE = 'KNT99';
EXCEPTION
    WHEN check_violation THEN NULL;
END;
$$;

-- 6. GOLD без ответственного эксперта не существует (ТЗ п. 9.4).
DO $$
BEGIN
    INSERT INTO dataset_items (
        id, evidence_group_id, gold_label, expert_id, reason_code,
        dataset_version, object_group_id, object_id
    ) VALUES (
        'ds-anon', 'eg-check', 'CONFIRMED_VIOLATION', '   ', NULL,
        'v1', 'grp-1', 'obj-check'
    );
    RAISE EXCEPTION 'GOLD-метка без expert_id прошла' USING ERRCODE = 'KNT99';
EXCEPTION
    WHEN check_violation THEN NULL;
END;
$$;

-- 7. Отрицательный вердикт требует кодированной причины (ТЗ п. 9.3).
DO $$
BEGIN
    INSERT INTO dataset_items (
        id, evidence_group_id, gold_label, expert_id, reason_code,
        dataset_version, object_group_id, object_id
    ) VALUES (
        'ds-neg', 'eg-check', 'NEGATIVE_VERIFIED', 'exp-1', NULL,
        'v1', 'grp-1', 'obj-check'
    );
    RAISE EXCEPTION 'NEGATIVE_VERIFIED без reason_code прошёл' USING ERRCODE = 'KNT99';
EXCEPTION
    WHEN check_violation THEN NULL;
END;
$$;

-- 8. Подтверждённое нарушение без инспектора и комментария невозможно (п. 9.3).
INSERT INTO params (code, matrix_version, section, parameter_name, compiled_rule, coverage)
VALUES ('PZ-001', 'draft-0', 'ПЗ', 'Площадь застройки', '{}'::jsonb, 'extractor_missing');

DO $$
DECLARE
    param_id INTEGER;
BEGIN
    SELECT id INTO param_id FROM params WHERE code = 'PZ-001';
    INSERT INTO checks (
        id, param_id, object_id, evidence_group_id, completeness_status,
        finding_status, inspector_id, decided_at, comment
    ) VALUES (
        'chk-auto', param_id, 'obj-check', 'eg-check', 'UPLOADED',
        'CONFIRMED_VIOLATION', NULL, NULL, NULL
    );
    RAISE EXCEPTION 'CONFIRMED_VIOLATION без инспектора прошёл' USING ERRCODE = 'KNT99';
EXCEPTION
    WHEN check_violation THEN NULL;
END;
$$;

-- 9. Выгрузка в РиН до финализации запрещена (ТЗ п. 9.6).
DO $$
BEGIN
    INSERT INTO processes (
        id, object_id, process_state, scenario, matrix_version, model_version, sync_state
    ) VALUES (
        'prc-early', 'obj-check', 'VERIFYING', 'FULL', 'draft-0', 'm-0', 'SYNCING'
    );
    RAISE EXCEPTION 'синхронизация началась до финализации' USING ERRCODE = 'KNT99';
EXCEPTION
    WHEN check_violation THEN NULL;
    WHEN SQLSTATE 'KNT02' THEN NULL;
END;
$$;

-- 10. FINALIZED без человека и без протокола не существует (ТЗ п. 9.3).
DO $$
BEGIN
    INSERT INTO processes (
        id, object_id, process_state, scenario, matrix_version, model_version
    ) VALUES (
        'prc-ghost', 'obj-check', 'FINALIZED', 'FULL', 'draft-0', 'm-0'
    );
    RAISE EXCEPTION 'FINALIZED без подписи человека прошёл' USING ERRCODE = 'KNT99';
EXCEPTION
    WHEN check_violation THEN NULL;
END;
$$;

-- 11. Счётчик повторов ограничен ТЗ: 1 попытка + 2 повтора.
DO $$
BEGIN
    INSERT INTO processes (
        id, object_id, process_state, scenario, matrix_version, model_version, parse_attempts
    ) VALUES (
        'prc-loop', 'obj-check', 'PARSING', 'FULL', 'draft-0', 'm-0', 9
    );
    RAISE EXCEPTION 'бесконечные повторы разбора разрешены' USING ERRCODE = 'KNT99';
EXCEPTION
    WHEN check_violation THEN NULL;
END;
$$;

-- 12. Нормальный путь обязан проходить: процесс, протокол, GOLD-метка.
INSERT INTO processes (
    id, object_id, process_state, scenario, matrix_version, model_version,
    protocol_id, finalized_by, finalized_at, sync_state, sync_attempts
) VALUES (
    'prc-ok', 'obj-check', 'FINALIZED', 'FULL', 'draft-0', 'm-0',
    'proto-check', 'inspector-7', now(), 'PENDING_SYNC', 3
);

INSERT INTO dataset_items (
    id, evidence_group_id, gold_label, expert_id, reason_code,
    dataset_version, object_group_id, object_id
) VALUES (
    'ds-ok', 'eg-check', 'NEGATIVE_VERIFIED', 'exp-1', 'WRONG_REVISION_SELECTED',
    'v1', 'grp-1', 'obj-check'
);

-- 13. Выгрузка смотрит на статус протокола, не только на process_state.
INSERT INTO protocols (
    id, object_id, version, matrix_version, dataset_version, model_version,
    input_manifest_hash, status, payload
) VALUES (
    'proto-open', 'obj-check', 2, 'draft-0', 'v1', 'm-0',
    'hash-2', 'VERIFICATION_COMPLETED', '{}'::jsonb
);

DO $$
BEGIN
    INSERT INTO processes (
        id, object_id, process_state, scenario, matrix_version, model_version,
        protocol_id, finalized_by, finalized_at, sync_state
    ) VALUES (
        'prc-desync', 'obj-check', 'FINALIZED', 'FULL', 'draft-0', 'm-0',
        'proto-open', 'inspector-7', now(), 'PENDING_SYNC'
    );
    RAISE EXCEPTION 'синхронизация по незакрытому протоколу прошла'
        USING ERRCODE = 'KNT99';
EXCEPTION
    WHEN SQLSTATE 'KNT02' THEN NULL;
END;
$$;

ROLLBACK;
