# Дополнительные материалы

**Ссылка для формы:** https://github.com/KonkovDV/Kontur/tree/main/submission/05-additional

Гейты I/J/K/L открыты. Числа ниже — публичная разметка разработки
и инженерные прогоны. Это не порог ТЗ.

| Число | Где | Чем не является |
|---|---|---|
| 55 / 72 / 1 / 4 из 132 | [`coverage`](../../data/matrix/coverage_snapshot.json) | «все проверки исполняются» |
| 0 из 6 и 0 из 4 | [`GOLD_DIAGNOSIS.md`](../../docs/GOLD_DIAGNOSIS.md), режим location и режим code | порог раздела 14 |
| OCR `MEASURED` | [`METRICS.md`](../../docs/METRICS.md) | Character Accuracy не ниже 0,95 |
| healthz 200 из tar | [`DEMO_COLD_START.md`](../../docs/DEMO_COLD_START.md) | прогон с вынутым кабелем |
| k6 p95 на `/status` | [`METRICS.md`](../../docs/METRICS.md) | промышленный SLA |

Повтор Тюменской после метки и пар листов: остановка
«якорь или число не найдены», `unlabeled_positive` 0,
`tz_recall_met` false. Пороги комнат по этому прогону не подбирались.

| Материал | Роль |
|---|---|
| [`03-presentation/`](../03-presentation/README.md) | Папка для поля «Презентация»: PowerPoint и PDF |
| [`openapi.yaml`](../../contracts/openapi.yaml) | Контракт API |
| [`submission.schema.json`](../../contracts/schemas/submission.schema.json) | Схема ответа |
| [`demo_package/README.md`](../../examples/demo_package/README.md) | Раскладка учебного пакета |
| [`KNOWN_GAPS.md`](../../docs/KNOWN_GAPS.md) | Что не сделано |
