# Документация

**Ссылка для формы:** https://github.com/KonkovDV/Kontur/tree/main/submission/02-documentation

Жюри начинает с README. Ниже — документы, на которые опирается сдача.
Гейты I/J/K/L открыты.

| Документ | Роль |
|---|---|
| [`README.md`](../../README.md) | Одна команда запуска, что работает и чего нет |
| [`ARCHITECTURE.md`](../../docs/ARCHITECTURE.md) | Три контура: код, приёмка, промышленный контур |
| [`METRICS.md`](../../docs/METRICS.md) | Пороги раздела 14 как пороги, не как результат |
| [`KNOWN_GAPS.md`](../../docs/KNOWN_GAPS.md) | Открытые пробелы |
| [`DEMO_COLD_START.md`](../../docs/DEMO_COLD_START.md) | Холодный запуск из tar. Сеть хоста не отключалась |
| [`ORGANIZER_ANSWERS_2026_09_26.md`](../../docs/ORGANIZER_ANSWERS_2026_09_26.md) | Ответы организатора, которые есть в репозитории |
| [`openapi.yaml`](../../contracts/openapi.yaml) | Контракт API |
| [`submission.schema.json`](../../contracts/schemas/submission.schema.json) | Схема ответа участника |

Покрытие матрицы — 55 executable, 72 extractor_missing, 1 advisory,
4 source_missing из 132. Это не заявление, что все параметры исполняются.
