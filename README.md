# Контур — «Инспектор ИИ»

Сервис камеральной сверки проектной (ПД), рабочей (РД) и исполнительной (ИД)
документации по матрице из 132 контролируемых параметров.
Задача №10, Мосгосстройнадзор.

Репозиторий **приватный**. Стратегия, Red Team, вопросы организатору и черновик
матрицы не предназначены для публичного зеркала.

**Вход:** PDF, DOCX, XML.
**Выход:** протокол с карточками доказательств и решением инспектора.
**Ядро продукта:** не распознавание текста, а
доказательная цепочка `актуальная редакция → доказательное извлечение →
атомарное исполняемое правило → решение инспектора`.

## Границы (действуют с первого коммита)

- `CONFIRMED_VIOLATION` присваивает **только инспектор**. Система формирует
  `CANDIDATE` и карточку доказательства.
- LLM/VLM **никогда** не пишут итоговый статус находки (ADR-0001).
- Предметная находка не сохраняется без
  `evidence_group_id`, источников с SHA-256 и координат (ADR-0002).
- Отсутствие стадии, документа или доказательства — **не** нарушение.
- Система сверяет **ПД с РД и ИД**, а не проект с СНиП (ADR-0006).
- Устаревшая или неутверждённая редакция не может быть эталоном.
- Пороги раздела 14 ТЗ (P ≥ 0,90; R ≥ 0,80; F1 ≥ 0,85; FPR ≤ 0,10 и др.) —
  минимумы приёмки, не заявленный результат.
- `РАЗМЕЧЕННЫЙ_TEST__213.zip` — карантин: не открывать, не
  подбирать по ним пороги ([`docs/DATASET_PACKAGE.md`](docs/DATASET_PACKAGE.md)).

## Состояние на 17.09.2026

### Исполняемые правила (executable): **27 / 132**

| Группа | Правила | Статус |
|--------|--------|--------|
| PZ (Пожарная защита) | PZ-001…012, 013, 014–020, 021, 022, 023 | ✅ executable |
| AR (Архитектура) | AR-041 | ✅ executable |
| SPZU (СПЗУ) | SPZU-024 | ✅ executable |
| KR (Конструктив) | KR-055 | ✅ executable |
| Остальные | 105 правил | `extractor_missing` |

### Red Team (adversarial)

| Набор | Статус |
|------|--------|
| RT-A: архив-бомба отклоняется с reason_code | ✅ реализован (PR #13) |
| RT-B: белый текст блокирует автонаходку | ✅ реализован |
| RT-C × 2: OCR dual-read + LLM isolation | ⏳ xfail |
| RT-D: rename не меняет identity | ✅ реализован |
| RT-E: истёкшая нормативная редакция | ⏳ xfail |
| RT-F: неподписанный нормативный фрагмент | ⏳ xfail |
| RT-G: idempotency broker | ⏳ xfail |
| RT-H: cross-tenant access denied | ⏳ xfail |
| RT-I: approve не default action | ⏳ xfail |

**xfail stop-ship осталось:** 7 из 8. Цель: 0 к 28.09.

### Открытые PR

| PR | Содержание | Статус |
|----|------------|--------|
| #11 | KR-055 enum extractor | OPEN |
| #12 | PZ-013/015/021/022/023 → executable | OPEN |
| #13 | RT-A: intake validation (decompression bomb) | OPEN |
| #14 | Docker offline + README | OPEN |

## Карта репозитория

```text
contracts/      OpenAPI 3.0 и JSON-схемы обмена (source of truth)
backend/        Python ≥3.11: домен, применение, инфраструктура, API
gateway/        Node.js BFF по требованию п.1.5 ТЗ
web/            React: двухпанельное рабочее место инспектора (каркас)
data/           Матрица 132, нормативный реестр, реестр поставки, карантин
docs/           ADR, план, трассируемость ТЗ, Red Team, вопросы организатору
```

## Быстрый старт

```bash
python -m venv .venv
. .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -e "backend[dev]"
pytest backend/tests -q        # все тесты
make check                     # ruff + mypy
```

## Offline-старт (без интернета)

```bash
# 1. Один раз загрузить образы (нужен интернет):
make offline-pull

# 2. Запуск без интернета (на любой машине с загруженными образами):
make offline-up

# 3. Проверить контейнеры:
docker compose ps

# API: http://localhost:8000
# RabbitMQ UI: http://localhost:15672 (guest/guest)
# MinIO console: http://localhost:9001 (kontur/kontur-dev-secret)
# Gateway: http://localhost:3000
```

## Документы

| Тема | Файл |
|---|---|
| Правила для разработчика и ИИ-агента | [`AGENTS.md`](AGENTS.md) |
| План 15–29.09 с гейтами | [`docs/PLAN_2026_09.md`](docs/PLAN_2026_09.md) |
| Трассируемость ТЗ → артефакт → тест | [`docs/TZ_TRACEABILITY.md`](docs/TZ_TRACEABILITY.md) |
| Архитектурные решения | [`docs/adr/`](docs/adr/) |
| Состав переданного пакета данных | [`docs/DATASET_PACKAGE.md`](docs/DATASET_PACKAGE.md) |
| Карантин датасета | [`docs/DATA_QUARANTINE.md`](docs/DATA_QUARANTINE.md) |
| Производительность и нагрузка | [`docs/PERFORMANCE.md`](docs/PERFORMANCE.md) |
| Вопросы организатору | [`docs/QUESTIONS_TO_ORGANIZER.md`](docs/QUESTIONS_TO_ORGANIZER.md) |
| Red Team и stop-ship | [`docs/RED_TEAM.md`](docs/RED_TEAM.md) |
| Нормативный реестр | [`docs/NORMATIVE_REGISTRY.md`](docs/NORMATIVE_REGISTRY.md) |
| SOTA / донор AeroBIM | [`docs/SOTA_AEROBIM_ANALYSIS.md`](docs/SOTA_AEROBIM_ANALYSIS.md) |
| Известные пробелы | [`docs/KNOWN_GAPS.md`](docs/KNOWN_GAPS.md) |
