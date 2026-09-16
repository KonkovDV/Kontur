# ADR-0005. Раздельные домены статусов

**Статус:** принято 15.09.2026, уточнено 16.09.2026.

## Контекст

ТЗ различает статусы загрузки документов (п. 9.1), статусы процесса (п. 9.1),
статусы протокола верификации (п. 9.3), статусы находки, статусы качества
данных и статусы синхронизации с ИАИС «РиН». Их смешение — основная причина
ложных нарушений: «нет ИД» превращается в «нарушение».

П. 9.1 пишет `COMPLETED` / `FINALIZED`. П. 9.3 пишет
`VERIFICATION_COMPLETED` / `PROTOCOL_FINALIZED`. Это один жизненный цикл
и две проекции на провод, а не две независимые машины.

П. 9.2 допускает автоматическое «расхождения нет». П. 9.3 отдаёт
`NEGATIVE_VERIFIED` инспектору. До ответа организатора (вопрос 8)
автомат пишет только внутренний `AUTO_NO_DIFFERENCE`.

## Решение

Шесть независимых словарей; хранится пять машин, шестой словарь — проекция:

1. **Комплектность (внутри):** `UPLOADED | PARTIAL | MISSING`.
   **На проводе п. 9.1:** `PD_/RD_/ID_` × те же три значения
   (`tz_upload_status`).
2. **Процесс:** `PENDING → PARSING → READY → VERIFYING → COMPLETED → FINALIZED`.
   Из `FINALIZED` нет исходящих переходов. Отмена — отдельная операция
   `unfinalize(current, actor, reason)`: только супервизор и только из `FINALIZED`,
   с непустой причиной; результат `COMPLETED`. Новая версия протокола и запись
   аудита — обязанность `review.unfinalize_process`.
3. **Протокол (проекция п. 9.3):** `READY | VERIFYING |
   VERIFICATION_COMPLETED | PROTOCOL_FINALIZED`. Не хранится второй машиной.
4. **Находка (предмет):** `CANDIDATE → CONFIRMED_VIOLATION | NEGATIVE_VERIFIED |
   CLARIFICATION_REQUIRED`; отдельно `SUSPICION`. Внутренний
   `AUTO_NO_DIFFERENCE` на провод ТЗ и в РиН не сериализуется.
5. **Качество данных:** `MISSING_EVIDENCE | NOT_APPLICABLE | NOT_COMPARABLE |
   LOW_QUALITY | ABSTAIN` — не нарушения и не «пройдено».
   `NOT_APPLICABLE → CANDIDATE` разрешён только инспектору (п. 9.2:
   подтверждение применимости). Автомат этот переход не делает.
6. **Синхронизация:** `NOT_REQUESTED | PENDING_SYNC | SYNCING | SYNCED |
   RETRY_WAIT | FAILED_TERMINAL`. Недоступность РиН не отменяет решение.

Запрещённые переходы проверяет доменная машина, а не UI. `SPLIT` не является
атомарным действием верификации: составной кандидат дробится отдельно.
Пустой пакет (все стадии `MISSING`) — не сценарий сверки, а ошибка входа.

`CANDIDATE`, `CONFIRMED_VIOLATION`, `NEGATIVE_VERIFIED` и
`AUTO_NO_DIFFERENCE` требуют `evidence_group_id`. `MISSING_EVIDENCE` и
`NOT_APPLICABLE` могут существовать без фрагментов: отсутствие доказательства
сериализуется, а не маскируется.

## Последствия

В сводное число нарушений входит ровно один статус — `CONFIRMED_VIOLATION`.
Контракт Gate B: `contracts/openapi.yaml`, JSON-схемы, `status_map.py`.
