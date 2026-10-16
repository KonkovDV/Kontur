# Пример JSON

Собрано `python scripts/export_submission_example.py` из
`demo_sheet_files()`. Документов организатора здесь нет.
Оба файла проходят `submission.schema.json` и `protocol.schema.json`.
Строк `CONFIRMED_VIOLATION` и `AUTO_NO_DIFFERENCE` нет.
`versions.git_sha` — SHA репозитория в момент сборки, не номер влития этого пакета.
Сборка воспроизводима: PDF комплекта с постоянными CreationDate и /ID, `protocol_id` постоянный.
CI запускает `python scripts/export_submission_example.py --check`: файлы должны совпасть со
свежей сборкой (кроме `versions.git_sha`).
`sections.completeness` — таблица (1) комплектности, 47 строк `STAGE_UPLOADED_NOT_VERIFIED`
с `counts_as_violation: false`. Это не находки и не нарушения.

| Папка | Исход |
|---|---|
| [`unattended/`](unattended/submission.json) | Как пакетный прогон: инспектор эталон не выбирал. 132 строки `COMPARISON_IMPOSSIBLE`, `violation_count` 0. [Протокол](unattended/protocol.json) |
| [`after_etalon_select/`](after_etalon_select/submission.json) | Инспектор назначил файл `f-pd`. PZ-001, KR-055 и AR-041 стали кандидатами и на проводе ответа помечены `VIOLATION_PRESENT`. Решения инспектора по ним нет: в протоколе `confirmed` пуст, `violation_count` 0. [Протокол](after_etalon_select/protocol.json) |
