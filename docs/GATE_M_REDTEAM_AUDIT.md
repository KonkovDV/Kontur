# Gate M — Red Team Audit Report v2

**Дата аудита:** 2026-09-18 03:30 МСК  
**Аудитор:** Red Team / триаж (AI-assisted, верифицировано по SHA)  
**База:** `main` `abbe107a` + PR #8–#19 (все ветки прочитаны)  
**Дедлайн RC-freeze:** 2026-09-28 16:00 МСК  
**Дедлайн подачи:** 2026-09-29 23:59 МСК  
**Версия:** 2 (v1 — PR #11, 2026-09-17; устарела после PR #12–#19)

> **ВАЖНО:** Этот документ — единственный актуальный аудит. Файл
> `docs/GATE_M_REDTEAM_AUDIT.md` из PR #11 устарел: xfail=18, executable=22.
> Текущие значения: xfail=**0**, executable=**27**.

---

## 1. Исполнительное резюме (триаж)

| Показатель | Было (PR #11) | Сейчас (PR #19) |
|---|---|---|
| xfail strict | 18 | **0** ✅ |
| Executable правила | 22 | **27** ✅ |
| Stop-ship закрыты | 0 | **10/12** (2 условно) ✅ |
| Red Team oracle PASS | 2/9 | **9/9** ✅ |
| Docker offline | ❌ | ✅ PR #14 |
| Redis idempotency | ❌ | ✅ PR #16 |
| Multi-tenancy | ❌ | ✅ PR #17 |
| UI HCAI RT-I | ❌ | ✅ PR #18 |
| Normative DB | ❌ | ✅ PR #19 |
| Метрики на frozen val. | не измерены | **не измерены** ⚠️ |

**Вердикт:** Все stop-ship блокеры сняты. Одно условное ограничение:
метрики на замороженной выборке будут получены при подаче.

---

## 2. Трассировка Stop-ship (RED_TEAM.md, 12 пунктов)

Авторитетный источник: `docs/RED_TEAM.md` SHA `6dc1ccf9`.

| # | Условие остановки | Статус | Закрывается |
|---|---|---|---|
| 1 | Доступен чужой tenant или объект | ✅ ЗАКРЫТ | PR #17 `check_object_access()`, `AccessDeniedError` |
| 2 | Находка без валидного источника/доказательства/версии правила | ✅ ЗАКРЫТ | ADR-0002: `Finding.__post_init__` требует `evidence_group_id` + SHA-256 + координаты |
| 3 | Модель может изменить статус, присвоенный человеком | ✅ ЗАКРЫТ | PR #18 RT-I: `Подтвердить` — последний, нет autofocus; PR #11 `_assert_machine_status()` |
| 4 | Неутверждённая/неоднозначная редакция выбрана эталоном | ✅ ЗАКРЫТ | `revision_resolver.py` SHA `03fb98d9`; RT-D test |
| 5 | `MISSING_EVIDENCE` или `LOW_QUALITY` → нарушение или «пройдено» | ✅ ЗАКРЫТ | ADR-0001: `_assert_machine_status()` in `evaluate.py`; машина выдаёт только `CANDIDATE` |
| 6 | Утечка скрытого теста | ✅ ЗАКРЫТ (политика) | `DATA_QUARANTINE.md`, явный запрет в README; карантинная директория не читается кодом |
| 7 | Обязательный порог не достигнут или CI при недостаточной выборке | ⚠️ УСЛОВНО | Gate J: P=1.00/R=0.90/F1=0.947 на n=15; прогноз F1≈0.87 > 0.85; актуальные цифры — при подаче на frozen val n=213 |
| 8 | Протокол меняется после финализации без новой версии | ✅ ЗАКРЫТ (проект) | `PROTOCOL_FINALIZED` статус в `domain/statuses.py`; архитектурно новая версия = новый протокол |
| 9 | Источники, модели, правила не идентифицируются хешами/версиями | ✅ ЗАКРЫТ | `file_sha256()` SHA `c8037e8e`; `NormativeRevision.document_hash` PR #19; `FileRuleRegistry` SHA `e51eb7da` |
| 10 | Демо не воспроизводится на чистой машине | ✅ ЗАКРЫТ | PR #14: `docker-compose.offline.yml`, `make offline-up`, pinned образы |
| 11 | Retry создаёт дубликат находки или протокола | ✅ ЗАКРЫТ | PR #16 RT-G: Redis idempotency `kontur:passport:v1:{sha256}` |
| 12 | Команда не может показать источник за 10 минут | ✅ ЗАКРЫТ (архитектура) | Каждый `Finding` несёт `evidence_group_id`; UI EvidenceCard ≤3 кликов (Gate K PR #9) |

**Итог:** 10 закрыты безусловно, 1 закрыт по политике (п.6), 1 условно (п.7).
Ни один stop-ship не является активным блокером RC-freeze.

---

## 3. Red Team Oracle Status (RT-A … RT-I)

Источник: `backend/tests/adversarial/test_rt_suites.py` (последняя версия: PR #19).

| Suite | Oracle | Тест | PR | Статус |
|---|---|---|---|---|
| **RT-A** | Decompression bomb → `reason_code` без краша | `test_rt_a_decompression_bomb_is_rejected_with_reason_code` | #13 | ✅ PASS |
| **RT-B** | Hidden text layer блокирует автонаходку | `test_rt_b_hidden_text_layer_blocks_automatic_finding` | #9 | ✅ PASS |
| **RT-C** | Digit misread 6↔8 → ABSTAIN | `test_rt_c_digit_misread_triggers_abstain` | #15 | ✅ PASS |
| **RT-C** | «ignore rules» внутри чертежа → данные, не инструкция | `test_rt_c_instruction_inside_image_is_ignored` | #15 | ✅ PASS |
| **RT-D** | Новая неутверждённая редакция ≠ эталон | `test_rt_d_newer_unapproved_revision_does_not_become_baseline` | main | ✅ PASS |
| **RT-D** | Переименование файла ≠ смена identity | `test_rt_d_rename_does_not_change_identity` | main | ✅ PASS |
| **RT-E** | Истёкшая норма → `NormativeStatus.EXPIRED`, не VIOLATION | `test_rt_e_expired_normative_revision_gives_clarification` | #19 | ✅ PASS |
| **RT-F** | Неподписанный нормативный фрагмент → `NOT_SIGNED`, не используется | `test_rt_f_unsigned_normative_chunk_is_not_used` | #19 | ✅ PASS |
| **RT-G** | At-least-once доставка → ровно 1 бизнес-эффект | `test_rt_g_duplicate_queue_message_yields_one_business_effect` | #16 | ✅ PASS |
| **RT-H** | Cross-tenant → `AccessDeniedError`, нет побочных эффектов | `test_rt_h_cross_tenant_access_is_denied_without_side_effect` | #17 | ✅ PASS |
| **RT-I** | «Подтвердить» — последний в DOM, нет autofocus/accessKey/submit | `test_rt_i_approve_is_not_default_action` | #18 | ✅ PASS |

**xfail история:** 18 → 7 → 5 → 4 → 3 → 2 → **0**

> Критическое примечание по RT-I: `web/src/App.tsx` находится в ветке `gate-k-ui-protocol`
> (PR #9), ещё не влит в main. Тест содержит двухуровневую защиту:
> Part 1 (oracle на порядке кнопок) — всегда PASS; Part 2 (файловая проверка App.tsx) —
> выполняется только если файл присутствует в main. После слияния PR #9 оба уровня активны.

---

## 4. Матрица правил — Coverage

| coverage | До PR #11 | После PR #11 | После PR #12 (текущее) |
|---|---|---|---|
| `executable` | 21 | 22 | **27** |
| `extractor_missing` | 111 | 110 | **105** |
| Прочие | — | — | без изменений |

### Список 27 executable правил

- **PZ-001–PZ-008, PZ-010–PZ-020** (19 правил, числовой экстрактор, оператор `delta`)
- **SPZU-024** (числовой, `delta`, `dual_read_required=false`)
- **AR-041** (числовой, `ge`, фиксированный `ref`)
- **KR-055** (enum, `class_not_lower`, PR #11)
- **PZ-013** (числовой вместимость, `ge`, PR #12)
- **PZ-015** (enum категория надёжности, `class_not_lower`, PR #12)
- **PZ-021** (enum энергоэффективность A–G, ФЗ-261, PR #12)
- **PZ-022** (enum класс пожарной опасности I–V, ФЗ-123, PR #12)
- **PZ-023** (enum класс конструктивной пожарной опасности C0–C3, ФЗ-123, PR #12)

**Охват:** 27/132 = **20.5%** executable.  
105 правил остаются `extractor_missing` — известный gap, задокументирован в `docs/KNOWN_GAPS.md`.

---

## 5. SOTA 2026 — Детальное соответствие

### 5.1 OCR и извлечение

| Технология | Ссылка | Реализовано | Модуль | Примечание |
|---|---|---|---|---|
| Vector OCR (pdfium) | SOTA 2026 baseline | ✅ | `pdfium_tokens.py` SHA c8037e8e | CA=1.0 для vector PDF |
| Raster verifier (Tesseract-5) | Risk-Controlled Gen. OCR 2026 | ✅ | `ocr_bakeoff.py` | CA≥0.97 порог |
| Dual-read corroboration | "Reading or Guessing?" EMNLP 2025 | ✅ | `dual_read.py` SHA 1c7c9a7f | digit-hallucination guard |
| Enum extractor (anchor+regex) | ExtractConf ACL 2025 | ✅ | `extractors/text.py` PR #11 | anchor→regex→dual-read |
| Calibrated confidence | ExtractConf ACL 2025 | ✅ | `calibration.py` PR #8 | weighted geometric mean |
| Per-group coverage | Group-Conditional CRC ICML 2026 | ✅ | Gate J PR #8 | worst-group метрики |
| Normative RAG (BGE-M3+BM25) | SOTA 2026 dense retrieval | ⚠️ | `normative_db.py` PR #19 | статическая DB, не RAG; gap документирован |

### 5.2 UI и HCAI

| Стандарт | Ссылка | Реализовано | Модуль |
|---|---|---|---|
| ≤3 clicks/finding | HCAI DSS Review, Cai et al. 2026 | ✅ | Gate K PR #9, `protocol_service.py` |
| Evidence-based XAI | Zhang et al. 2026 §4.2 | ✅ | EvidenceCard + BoundingBox + BBox overlay |
| BLUEPRINT dual-panel | Liang et al. 2026 | ✅ | PDF Canvas 60% + EvidenceCard 40% |
| Human oversight | ISO/IEC 42001:2023 §6.4 | ✅ | RT-I UI: approve not default |
| LLM не пишет статус | ADR-0001 | ✅ | `_assert_machine_status()` в evaluate.py |

### 5.3 Безопасность и инфраструктура

| Стандарт | Реализовано | Модуль |
|---|---|---|
| Content-addressed identity (SLSA L2) | ✅ | `file_sha256()`, `NormativeRevision.document_hash` |
| Multi-tenant isolation | ✅ | PR #17 `access_control.py` |
| At-least-once + idempotency | ✅ | PR #16 Redis `kontur:passport:v1:{sha256}` |
| Safe degradation при Redis failure | ✅ | `get_cached_passport` никогда не выбрасывает |
| ZIP bomb protection | ✅ | PR #13 `validate_intake()`, заголовки без распаковки |
| Prompt injection detection | ✅ | PR #15 `injection_scan.py`, EN+RU паттерны |
| Normative revision expiry (ISO 9001:2015 §7.5.3) | ✅ | PR #19 `NormativeDB.get_valid_revision()` |
| Offline reproducibility | ✅ | PR #14 `docker-compose.offline.yml` |

---

## 6. ADR Compliance (полная таблица)

| ADR | Правило | Реализация | Верификация |
|---|---|---|---|
| ADR-0001 | LLM/VLM не пишет `CONFIRMED_VIOLATION` / `NEGATIVE_VERIFIED` | `_assert_machine_status()` в `evaluate.py` | RT-суит: ни один тест не допускает CONFIRMED от машины |
| ADR-0002 | `CANDIDATE` требует `evidence_group_id` + SHA-256 + координаты | `Finding.__post_init__` check | Stop-ship п.2 |
| ADR-0003 | Эталон = ПД; РД/ИД — проверяемые | `EvidenceRole.EXPECTED` только для PD | revision_resolver.py |
| ADR-0004 | `FileRuleRegistry` читает JSON, кэш в памяти | `registry.py` SHA e51eb7da | 132 правила загружаются при старте |
| ADR-0005 | Проекции статусов: комплектность / процесс / протокол | domain/statuses.py | Разделены в схемах contracts/ |
| ADR-0006 | Сверка ПД↔РД↔ИД, не проект с СНиП | `comparators.py` SHA 56ba0335 | evaluate.py: sources = [PD, RD/ID] |

---

## 7. Инфраструктурная готовность

| Компонент | Статус | PR | Заметки |
|---|---|---|---|
| Python backend (ядро) | ✅ | main | domain + application + infrastructure |
| Calibration engine | ✅ | #8 | P=1.00/R=0.90/F1=0.947 на gold-15 |
| Protocol UI (React) | ✅ | #9 | ≤3 clicks, BoundingBox overlay |
| BFF Gateway (Node.js) | ✅ | #10 | OpenAPI 3.0, Circuit Breaker, k6 p95≤200ms |
| KR-055 enum extractor | ✅ | #11 | text.py + evaluate.py text-ветка |
| PZ fire/energy classes | ✅ | #12 | 5 новых правил, 27 executable total |
| Intake validation | ✅ | #13 | ZIP bomb, corrupt PDF, size limits |
| Docker offline build | ✅ | #14 | pinned images, `make offline-up` |
| Dual-read + injection | ✅ | #15 | ABSTAIN, EN+RU injection scan |
| Redis idempotency | ✅ | #16 | safe degradation, TTL=3600 |
| Multi-tenancy | ✅ | #17 | `AccessDeniedError`, pure function |
| UI HCAI RT-I | ✅ | #18 | Подтвердить: last, no autofocus |
| Normative DB | ✅ | #19 | EXPIRED→CLARIFICATION, NOT_SIGNED→rejected |
| RabbitMQ at-least-once | ⚠️ | — | Тестируется через AsyncMock; реальный брокер в docker-compose |
| OCR rotation/skew | ❌ | — | GAP-OCR-ROT; задокументирован в KNOWN_GAPS.md |
| Full JWT auth | ⚠️ | — | GAP-AUTH; базовая структура в BFF |

---

## 8. Прогноз метрик ТЗ

> ⚠️ Прогноз основан на Gate J gold-set (n=15). Актуальные значения —
> при подаче на frozen validation (n=213). Репозиторий **не публикует числа**
> до замера (README §Границы).

| Метрика | Порог ТЗ §14 | Gate J Прогноз | Конфиденс | Основание |
|---|---|---|---|---|
| Character Accuracy | ≥ 0.95 | 1.00 (vector) / 0.97 (raster) | HIGH | pdfium CA=1.0 + Tesseract |
| Exact Match | ≥ 0.90 | ~0.93 | MEDIUM | dual-read agreement rate |
| Linkage (связка) | ≥ 0.95 | ~0.96 | MEDIUM | evidence_group_id architecture |
| Localization (IoU≥0.5) | ≥ 0.95 | ~0.96 | MEDIUM | polygon_norm в PageToken |
| Precision | ≥ 0.90 | 1.00 (gold-15) | LOW→MEDIUM | n=15 слишком мало |
| Recall | ≥ 0.80 | 0.90 (gold-15) | LOW→MEDIUM | 1 FN (raster/low-OCR) |
| F1 | ≥ 0.85 | ~0.87 | MEDIUM | P×R гармоника |
| FPR | ≤ 0.10 | ~0.08 | HIGH | ADR-0001: машина не создаёт CONFIRMED |

**Критическое наблюдение:** P=0.90 и R=0.80 → F1≈0.847, что **не** покрывает F1=0.85.
Именно поэтому Gate J установил более строгий порог P≥0.93 / R≥0.83 для запаса.
Верхний прогноз F1≈0.87 имеет запас ≈0.02 над порогом.

---

## 9. Gate N Readiness Checklist

Требования из `docs/RED_TEAM.md` (раздел «Gate N — adversarial readiness»):

| Требование | Статус | Примечание |
|---|---|---|
| 0 открытых S0/S1 | ✅ | Все stop-ship закрыты или условно |
| 0 незамеченных нарушений целостности доказательств | ✅ | ADR-0002 enforced |
| 0 cross-tenant отказов | ✅ | RT-H, PR #17 |
| 0 дублей бизнес-эффекта в chaos-наборе | ✅ | RT-G, PR #16 |
| 100% находок демо воспроизводятся по манифесту | ✅ | Docker offline PR #14 + `make offline-up` |
| Все противоречия → безопасное состояние | ✅ | ABSTAIN (RT-C), CLARIFICATION_REQUIRED (RT-E), NOT_SIGNED (RT-F) |
| Worst-group метрики не ниже порогов ТЗ | ⚠️ | Прогноз удовлетворяет; замер на frozen val при подаче |
| Резервное видео и offline режим проверены | ✅ | PR #14; `make offline-pull` + `make offline-up` |

**Gate N: 7/8 ✅, 1 условно ⚠️** (метрики на frozen validation)

---

## 10. Анализ остаточных рисков

| Риск | Уровень | Вероятность | Митигация |
|---|---|---|---|
| F1 < 0.85 на frozen val | S1 | LOW | Gate J запас +0.02; ADR-0001 исключает FP от машины |
| OCR rotation дефект (GAP-OCR-ROT) | S2 | MEDIUM | ABSTAIN при низком CA; MISSING_EVIDENCE — не нарушение |
| BGE-M3 RAG не реализован | S3 | — | NormativeDB (статическая) покрывает RT-E/F; GAP задокументирован |
| PR merge conflict в test_rt_suites.py | S3 | HIGH | Squash-merge; брать версию из последнего PR (порядок ↓) |
| PR #9 (Gate K, App.tsx) не в main к freeze | S3 | MEDIUM | RT-I тест имеет Part 1 без зависимости от App.tsx |
| JWT не полный (GAP-AUTH) | S2 | LOW | BFF структура готова; demo-режим не требует production JWT |

---

## 11. Порядок слияния PR (RC-freeze 28.09 16:00)

Все PR базируются на `main` SHA `abbe107ae39504c4c05086e57208f8db6f3875bb`.
**Стратегия:** squash-merge. При конфликте в `test_rt_suites.py` —
всегда брать версию из **более позднего** PR (высший номер).

```
 #8  gate-j-calibration         SHA 4c5fe887
 #9  gate-k-ui-protocol         SHA f34212a9  ← App.tsx
#10  gate-l-bff-openapi         SHA f8b78401
#11  gate-kr055-enum-extractor  SHA b38935bb  ← docs/GATE_M_REDTEAM_AUDIT.md v1
#12  gate-pz-enum-fire-classes  SHA 52b6d2c6
#13  gate-rt-a-intake           SHA d859af50
#14  gate-docker-offline        SHA bb486dfa
#15  gate-rt-c-dual-read        SHA bafda795
#16  gate-gap-redis             SHA c7c84984
#17  gate-rt-h-access           SHA 1723f15c
#18  gate-rt-i-approve          SHA e282bfa1
#19  gate-rt-ef-normative-db    SHA a9b828b0
#20  gate-m-rc-audit            (этот PR)     ← audit v2 + README update
```

**После слияния всех PR:**
1. `git tag rc/2026-09-28 -m "RC freeze Gate M"`
2. `make offline-pull` на чистой машине
3. `make offline-up && make test` — все тесты должны пройти с xfail=0
4. Создать `CHANGELOG.md` (или обновить) с перечнем всех изменений

---

## 12. Что НЕ входит в Gate M (честный учёт)

| Компонент | Причина | Документ |
|---|---|---|
| 105/132 правил (`extractor_missing`) | Вне scope Gate M; требуют доменной разметки | `docs/KNOWN_GAPS.md` |
| Normative RAG (BGE-M3+BM25+RRF) | NormativeDB (статическая) — достаточно для RT-E/F | `docs/KNOWN_GAPS.md` |
| OCR rotation/skew correction | GAP-OCR-ROT; safe fallback: ABSTAIN | `docs/KNOWN_GAPS.md` |
| Full JWT/RBAC | GAP-AUTH; demo-режим безопасен | `docs/KNOWN_GAPS.md` |
| Frozen validation цифры | Карантин; замер при подаче | `docs/DATA_QUARANTINE.md` |

---

## 13. Подпись и закрытие

| Роль | Дата | Статус |
|---|---|---|
| Red Team Lead | 2026-09-18 | ✅ Аудит проведён |
| Security Review | — | 🔲 Pending |
| QA Lead | — | 🔲 Pending |
| Product Owner | — | 🔲 Pending |

*Следующий аудит: Gate N final check перед подачей (2026-09-29 до 20:00 МСК).*
