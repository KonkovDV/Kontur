# Контур — «Инспектор ИИ»

Сервис камеральной сверки проектной (ПД), рабочей (РД) и исполнительной (ИД)
документации по матрице из 132 контролируемых параметров.
Задача №10, Мосгосстройнадзор.

Репозиторий публичный. Лицензия кода — Apache-2.0.

**Вход:** PDF, DOCX, XML. **Выход:** протокол с карточками доказательств и
решением инспектора. **Ядро продукта:** не распознавание текста, а
доказательная цепочка `актуальная редакция → доказательное извлечение →
атомарное исполняемое правило → решение инспектора`.

## Границы (действуют с первого коммита)

- `CONFIRMED_VIOLATION` присваивает **только инспектор**. Система формирует
  `CANDIDATE` и карточку доказательства.
- LLM/VLM **никогда** не пишут итоговый статус находки (ADR-0001).
- Предметная находка (`CANDIDATE` / `CONFIRMED_VIOLATION` /
  `NEGATIVE_VERIFIED` / внутренний `AUTO_NO_DIFFERENCE`) не сохраняется без
  `evidence_group_id`, источников с SHA-256 и координат (ADR-0002).
  `MISSING_EVIDENCE` и `NOT_APPLICABLE` могут существовать без фрагментов.
- Отсутствие стадии, документа или доказательства — **не** нарушение:
  `MISSING_EVIDENCE` / `NOT_APPLICABLE` / `NOT_COMPARABLE` /
  `CLARIFICATION_REQUIRED`.
- Система сверяет **ПД с РД и ИД**, а не проект с СНиП (ADR-0006).
- Комплектность на проводе — `PD_UPLOADED` / `RD_PARTIAL` / `ID_MISSING`.
  Процесс — `COMPLETED` / `FINALIZED`. Протокол — `VERIFICATION_COMPLETED` /
  `PROTOCOL_FINALIZED`. Это проекции, не одна простыня статусов (ADR-0005).
- Явная пометка «не утв.» не может быть эталоном. Одна ПД в комплекте без
  этой пометки — эталон с основанием `PACKAGE_DEFAULT` (ADR-0014).
- Пороги раздела 14 ТЗ (Character Accuracy ≥0,95; Exact Match ≥0,90; связка
  ≥0,95; локализация ≥0,95 при IoU≥0,50; Precision ≥0,90; Recall ≥0,80;
  F1 ≥0,85; FPR ≤0,10) — это **минимумы приёмки, а не заявленный результат**.
  Гармоника P=0,90 и R=0,80 ≈ 0,847 и **не** закрывает F1=0,85.
  До замера на frozen validation репозиторий не публикует ни одного числа.
- `РАЗМЕЧЕННЫЙ_TEST__213.zip` и каталог
  `РАЗМЕЧЕННЫЙ_TEST_HIDDEN_ОРГАНИЗАТОР_213` — карантин: не открывать, не
  подбирать по ним пороги ([`docs/DATASET_PACKAGE.md`](docs/DATASET_PACKAGE.md)).

## Состояние

Срез 23.09.2026. Гейты I/J/K/L **открыты**.
Coverage: 44 executable / 83 extractor_missing / 1 advisory / 4 source_missing из 132 объявленных.
OCR `MEASURED`: движок есть, порог не взят. Frozen val нет. РиН ACK нет. Freeze инфры до 29.09.

Полный бриф для ИИ с GitHub: [`docs/GH_SITUATION_2026_09_21.md`](docs/GH_SITUATION_2026_09_21.md),
шина нескольких агентов: [`docs/GH_AGENT_BUS.md`](docs/GH_AGENT_BUS.md),
затем [`docs/AGENT_HANDOFF.md`](docs/AGENT_HANDOFF.md) и
[`data/dataset/agent_handoff.json`](data/dataset/agent_handoff.json).
Организатор прислал TRAIN_PUBLIC и gold-seed — это не held-out val
([`docs/ORGANIZER_GOLD.md`](docs/ORGANIZER_GOLD.md)).

## Карта репозитория

```text
contracts/      OpenAPI 3.0 и JSON-схемы обмена (source of truth)
backend/        Python ≥3.11: домен, применение, инфраструктура, API
gateway/        Node.js BFF по требованию п.1.5 ТЗ
web/            React: двухпанельная evidence-карточка инспектора (Gate K открыт)
data/           Матрица 132, нормативный реестр, реестр поставки, карантин
docs/           ADR, план, трассируемость ТЗ, Red Team, вопросы организатору
```

## Старт за пять минут

Нужны Docker Compose v2 и свободные порты на `127.0.0.1`: `3000` (интерфейс и API),
`8000` (ядро), `5432`, `6379`, `5672`, `9000`. GNU make не нужен.
GPU не нужен: в образ не входит драйвер NVIDIA.

```text
docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d --build
```

Открыть http://127.0.0.1:3000 . Проверка ядра через шлюз:
http://127.0.0.1:3000/api/v1/healthz . На учебном стенде плашка «учебный стенд»
и токен `inspector-1@OBJ-DEMO-COLD-START/INSPECTOR`. Это не учётная запись
продакшена. Кнопка «Учебный комплект» или `python scripts/load_demo_kit.py`
кладёт синтетические ПД, РД и ИД в этот объект. Эталон назначает инспектор.
После финализации кнопка «Передать в РиН (mock)» ставит очередь `PENDING_SYNC`.
ACK РиН нет.
Документы организатора на стенд не класть.

Без сети после того, как образы уже скачаны:
[`docker-compose.offline.yml`](docker-compose.offline.yml) и
[`docs/DEMO_COLD_START.md`](docs/DEMO_COLD_START.md).

Проверка кода без Docker, из корня репозитория:

```text
pip install -e "backend[dev]"
pytest backend/tests -q
python scripts/check_claims.py
```

## Документы

| Тема | Файл |
|---|---|
| Правила для разработчика и ИИ-агента | [`AGENTS.md`](AGENTS.md) |
| Срез 21.09 для ИИ с GitHub | [`docs/GH_SITUATION_2026_09_21.md`](docs/GH_SITUATION_2026_09_21.md) |
| Шина нескольких ИИ (Issues + `gh`) | [`docs/GH_AGENT_BUS.md`](docs/GH_AGENT_BUS.md) |
| Handoff следующего агента | [`docs/AGENT_HANDOFF.md`](docs/AGENT_HANDOFF.md) |
| План 15–29.09 с гейтами | [`docs/PLAN_2026_09.md`](docs/PLAN_2026_09.md) |
| Трассируемость ТЗ → артефакт → тест | [`docs/TZ_TRACEABILITY.md`](docs/TZ_TRACEABILITY.md) |
| Три контура готовности (не порог ТЗ) | [`docs/TZ_SCORECARD.md`](docs/TZ_SCORECARD.md) |
| OSINT Document AI, срез 21.09.2026 | [`docs/RESEARCH_OSINT_2026.md`](docs/RESEARCH_OSINT_2026.md) |
| Архитектурные решения | [`docs/adr/`](docs/adr/) |
| Состав переданного пакета данных | [`docs/DATASET_PACKAGE.md`](docs/DATASET_PACKAGE.md) |
| Публичный gold ≠ frozen val | [`docs/ORGANIZER_GOLD.md`](docs/ORGANIZER_GOLD.md) |
| Errata аудита «46% ТЗ» | [`docs/AUDITOR_ERRATA.md`](docs/AUDITOR_ERRATA.md) |
| План дальнейшей работы | [`docs/WORK_PLAN.md`](docs/WORK_PLAN.md) |
| Холодный запуск демо (#78) | [`docs/DEMO_COLD_START.md`](docs/DEMO_COLD_START.md) |
| Пакет сдачи (#79) | [`docs/SUBMISSION_PACK.md`](docs/SUBMISSION_PACK.md) |
| Карантин датасета | [`docs/DATA_QUARANTINE.md`](docs/DATA_QUARANTINE.md) |
| Производительность и нагрузка | [`docs/PERFORMANCE.md`](docs/PERFORMANCE.md) |
| Вопросы организатору | [`docs/QUESTIONS_TO_ORGANIZER.md`](docs/QUESTIONS_TO_ORGANIZER.md) |
| Red Team и stop-ship | [`docs/RED_TEAM.md`](docs/RED_TEAM.md) |
| Нормативный реестр | [`docs/NORMATIVE_REGISTRY.md`](docs/NORMATIVE_REGISTRY.md) |
| SOTA / донор AeroBIM | [`docs/SOTA_AEROBIM_ANALYSIS.md`](docs/SOTA_AEROBIM_ANALYSIS.md) |
| Известные пробелы | [`docs/KNOWN_GAPS.md`](docs/KNOWN_GAPS.md) |
