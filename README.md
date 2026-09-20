# Контур — «Инспектор ИИ»

Сервис камеральной сверки проектной (ПД), рабочей (РД) и исполнительной (ИД)
документации по матрице из 132 контролируемых параметров.
Задача №10, Мосгосстройнадзор.

Репозиторий **приватный**. Стратегия, Red Team, вопросы организатору и черновик
матрицы не предназначены для публичного зеркала.

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
- Устаревшая или неутверждённая редакция **не может** быть эталоном.
- Пороги раздела 14 ТЗ (Character Accuracy ≥0,95; Exact Match ≥0,90; связка
  ≥0,95; локализация ≥0,95 при IoU≥0,50; Precision ≥0,90; Recall ≥0,80;
  F1 ≥0,85; FPR ≤0,10) — это **минимумы приёмки, а не заявленный результат**.
  Гармоника P=0,90 и R=0,80 ≈ 0,847 и **не** закрывает F1=0,85.
  До замера на frozen validation репозиторий не публикует ни одного числа.
- `РАЗМЕЧЕННЫЙ_TEST__213.zip` и каталог
  `РАЗМЕЧЕННЫЙ_TEST_HIDDEN_ОРГАНИЗАТОР_213` — карантин: не открывать, не
  подбирать по ним пороги ([`docs/DATASET_PACKAGE.md`](docs/DATASET_PACKAGE.md)).

## Состояние

Контракты, домен, executable-слайсы матрицы (не 132/132), persist находок,
GET `/protocol` и `/audit`. После загрузки PDF каскад L1–L7 **запускается**
(векторный слой → `READY`). OCR в запросе нет. Пороги ТЗ на frozen validation
**не измерены**. Организатор прислал TRAIN_PUBLIC и gold-seed из 15 проверок —
это не held-out val ([`docs/ORGANIZER_GOLD.md`](docs/ORGANIZER_GOLD.md)).

## Карта репозитория

```text
contracts/      OpenAPI 3.0 и JSON-схемы обмена (source of truth)
backend/        Python ≥3.11: домен, применение, инфраструктура, API
gateway/        Node.js BFF по требованию п.1.5 ТЗ
web/            React: двухпанельное рабочее место инспектора (каркас)
data/           Матрица 132, нормативный реестр, реестр поставки, карантин
docs/           ADR, план, трассируемость ТЗ, Red Team, вопросы организатору
```

## Старт

```bash
python -m venv .venv
. .venv/bin/activate                 # Windows: .venv\Scripts\activate
pip install -e "backend[dev]"
pytest backend/tests -q
ruff check backend scripts && mypy --strict backend/src
python scripts/check_contracts.py && python scripts/check_claims.py
docker compose up -d                 # postgres, redis, rabbitmq, minio
```

## Документы

| Тема | Файл |
|---|---|
| Правила для разработчика и ИИ-агента | [`AGENTS.md`](AGENTS.md) |
| План 15–29.09 с гейтами | [`docs/PLAN_2026_09.md`](docs/PLAN_2026_09.md) |
| Трассируемость ТЗ → артефакт → тест | [`docs/TZ_TRACEABILITY.md`](docs/TZ_TRACEABILITY.md) |
| Три контура готовности (не порог ТЗ) | [`docs/TZ_SCORECARD.md`](docs/TZ_SCORECARD.md) |
| Архитектурные решения | [`docs/adr/`](docs/adr/) |
| Состав переданного пакета данных | [`docs/DATASET_PACKAGE.md`](docs/DATASET_PACKAGE.md) |
| Публичный gold ≠ frozen val | [`docs/ORGANIZER_GOLD.md`](docs/ORGANIZER_GOLD.md) |
| Errata аудита «46% ТЗ» | [`docs/AUDITOR_ERRATA.md`](docs/AUDITOR_ERRATA.md) |
| План дальнейшей работы | [`docs/WORK_PLAN.md`](docs/WORK_PLAN.md) |
| Карантин датасета | [`docs/DATA_QUARANTINE.md`](docs/DATA_QUARANTINE.md) |
| Производительность и нагрузка | [`docs/PERFORMANCE.md`](docs/PERFORMANCE.md) |
| Вопросы организатору | [`docs/QUESTIONS_TO_ORGANIZER.md`](docs/QUESTIONS_TO_ORGANIZER.md) |
| Red Team и stop-ship | [`docs/RED_TEAM.md`](docs/RED_TEAM.md) |
| Нормативный реестр | [`docs/NORMATIVE_REGISTRY.md`](docs/NORMATIVE_REGISTRY.md) |
| SOTA / донор AeroBIM | [`docs/SOTA_AEROBIM_ANALYSIS.md`](docs/SOTA_AEROBIM_ANALYSIS.md) |
| Известные пробелы | [`docs/KNOWN_GAPS.md`](docs/KNOWN_GAPS.md) |
