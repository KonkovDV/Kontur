# Синтетический комплект для `run_package`

PDF в репозиторий не кладутся. Каталог собирает тест
`backend/tests/test_run_package_cli.py` из учебного комплекта.

```text
<объект>/
  ПД/*.pdf
  РД/*.pdf
  ИД/*.pdf
```

Либо рядом `files_index.jsonl`: у каждой строки `object_id`, `stage`
(`PD`/`RD`/`ID` или `ПД`/`РД`/`ИД`) и `path`. `RD_ID_MIXED` пропускается.

```text
python -m kontur.cli.run_package --input <этот каталог> --out <каталог>
```
