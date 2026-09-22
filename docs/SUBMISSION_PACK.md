# Пакет сдачи (issue #79)

Машиночитаемый evidence pack: git SHA, версии матрицы/датасета/модели,
coverage в разбивке, input_manifest, сервисы Compose (digest только если
задан), хеши моделей если есть, ссылка на CI run, ограничения, сырой Gate K
если сессии лежат в `out/usability/`, JSON ответа участника и протокол ТЗ.

Не frozen val, не GOLD OCR, не закрытие гейтов I/J/K/L. `AUTO_NO_DIFFERENCE`
на провод протокола не выходит. Объект Polar и TEST_HIDDEN в пакет не входят.

Схема: [`contracts/schemas/submission_pack.schema.json`](../contracts/schemas/submission_pack.schema.json).
Сборщик: `kontur.evaluation.submission_pack`. JSON участника собирается только
через `findings_to_submission` / `build_submission`.

## Собрать

```text
python scripts/export_submission_pack.py
```

Пишет `out/submission_pack.json` (каталог `out/` в gitignore). Без процесса
находки `protocol` и `submission` — `null`: это конверт провенанса. Объектный
JSON заполняется, когда в сборщик переданы findings.

Digest образов не угадывается. Чтобы включить:

```text
set KONTUR_DIGEST_CORE=sha256:...
set KONTUR_MODEL_SHA256=<64 hex>
```

В GitHub Actions подставляются `GITHUB_RUN_ID` / `GITHUB_SHA`.

На Linux: `make submission-pack`.

## Что пакет не утверждает

| Поле | Смысл |
|---|---|
| `coverage` | 44 executable, 83 extractor_missing, 1 advisory, 4 source_missing; не вся матрица executable |
| `closes_gate_k=false` | даже при сырых JSON рекордера |
| `models=[]` | моделей нет, пока нет `KONTUR_MODEL_SHA256` |
| `digests_available=false` | digest не снят с Docker |
| `protocol=null` | нет финализированного процесса в этом прогоне |
