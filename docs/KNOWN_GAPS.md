# Известные пробелы

Честный реестр того, чего нет. Не путать со stop-ship: здесь можно идти
дальше, но нельзя притворяться, что слой готов.

| ID | Пробел | Почему не закрыто | Куда |
|---|---|---|---|
| RT-2609-21 | Замер юзабилити на 5 инспекторах | Форма есть, сессий нет | гейт K |
| GAP-PROCESS-FINDINGS | Находки и комплектность не в таблице `processes` | Снимок состояния есть; очередь инспектора после рестарта пуста | гейт L |
| GAP-OCR-ROT | Поворот и перекос скана | Векторный слой есть, OCR-пайплайна нет | гейт I |
| GAP-STAMP | Штамп поверх текста | Нет сегментации штампа | гейт I |
| GAP-DWG | Разбор DWG | Аудио и ТЗ расходятся; до ответа — `NOT_SUPPORTED` | вопрос 6 |
| GAP-EDIT | Журнал правок инспектора отдельной таблицей | Решение пишется в находку, отдельного `user_action_log` нет | гейт K |
| GAP-ISOLATE | PDF в дочернем процессе с таймаутом | pdfium в том же процессе | надёжность |
| GAP-RT-G-PIPELINE | `claim_finding_slot` вызывается из библиотеки, но не интегрирован в pipeline | oracle-тест проходит; дубли при at-least-once всё ещё возможны | гейт L / PR #24 |

Adversarial: RT-A/C/E/F/H/I закрыты регрессией. RT-G — xfail удалён (PR #22).

## Закрытые пробелы

| ID | Закрыт | Коммит |
|---|---|---|
| RT-2609-18 | CI фронтенда (npm/tsc) | 4669fe1 |
| RT-2609-19 | OpenAPI 3.0.3 → 3.1.0 | 671d8b8 |
| RT-2709-09 | character_accuracy: Wagner–Fischer CER + NFC-нормализация | ea75e70, bee1a1b |
| GAP-GATE-G | 132/132 правил в матрице; каталог + compile_matrix.py | b1c65e3 |
| GAP-ALL-OPERATORS | Все 12 операторов (delta, ge, lt, range, class_not_lower, present, …) | f08932d |
| GAP-GATE-H | Гейт H: ≥20 исполняемых правил (18×PZ + SPZU-024 + AR-041 = 20/20) | f08932d…406e97c |
| GAP-ENUM-EXTRACTOR | text/enum экстрактор; KR-055 и PZ-015/021/022/023 executable | PR #11/#12, локально |
| GAP-RT-G | Идемпотентность находки при at-least-once — `claim_finding_slot` в Redis | PR #22 (pending merge) |
| **GAP-IOS4** | **IOS4-078/079: executable extractor (number + regex)** | **PR #23 (pending merge)** |
