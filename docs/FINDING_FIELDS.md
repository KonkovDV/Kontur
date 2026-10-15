# Поля находки: измеренное значение, пункт нормы, страница/область

Сверка контракта с форматом «значение + норма + место» (как в отчётах Archistar/UpCodes).
Документ фиксирует, что есть и чего нет. Ничего здесь не закрывает гейты и не меняет счёт 59/132.
Соответствие проверяет тест `backend/tests/test_finding_fields_contract.py`: если контракт
изменится, тест упадёт, и таблицу нужно будет обновить.

| Что нужно | Где есть в контракте | Обязательно? | В `GET /processes/{id}/findings` |
|---|---|---|---|
| Измеренное значение | `finding.actual_value`, `finding.expected_value`, `finding.delta` | нет | **нет** |
| Единица измерения | только `evidence_group.fragments[].extracted.unit` | нет | **нет** |
| Пункт нормы | `finding.normative_refs[].identifier` + `.clause` | нет (сам список необязателен) | **нет** |
| Документ | `evidence_group.fragments[].document` (`file_id`, `file_hash`, `sheet`, `revision`) | да, внутри фрагмента | только через `evidence_group_id` |
| Страница | `evidence_group.fragments[].page` | да, внутри фрагмента | только через `evidence_group_id` |
| Область | `evidence_group.fragments[].polygon_source` / `polygon_norm` | да, внутри фрагмента | только через `evidence_group_id` |

## Пробелы

1. Список находок в API отдаёт только `finding_id`, `rule_code`, `finding_status`, `section`,
   `rationale`, `evidence_group_id`. Значение, норма и место видны только в карточке доказательства.
2. У `finding` нет собственного поля единицы: значение без единицы нельзя показать отдельно от фрагмента.
3. `normative_refs` и `evidence_group_id` у находки необязательны: схема пропускает находку без нормы и без места.

Как закрывать: отдельными PR и после решения по контракту, без изменения счёта матрицы.
