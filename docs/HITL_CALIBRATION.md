# Калибровка уверенности HITL (SILVER)

`backend/src/kontur/evaluation/calibration.py` + `scripts/hitl_calibration.py`.

Замороженные пороги UI: `data/calibration/hitl_thresholds.v1.json`
(+ зеркало `web/src/config/hitl_thresholds.v1.json`, sha256 рядом).

- Вход CLI: JSONL `{confidence, correct, split}` на SILVER/новых размеченных. Split `hidden` отвергается — **порог не подбирался на hidden**.
- Выход CLI: `out/hitl_calibration_silver.json` (n, бакеты conf/acc, ECE, t_high, git sha, дата) и `out/hitl_reliability_silver.svg`. Целевые артефакты брифа — `reports/calibration/` (follow-up).
- `t_high` — наименьший порог, где **верхняя** граница Уильсона доли ошибок в зоне ≥ t_high ≤ `--max-error-rate` (0,10) при n_zone ≥ `--min-n` (30).
- Нет выборки или ни один порог не проходит → `t_high = null`, `status = uncalibrated`.
- Всегда `is_gold = false`, `closes_gate = false`: Gate I/K отчёт не закрывает.

**Текущий статус (15.10.2026): uncalibrated / insufficient_data.**
В `hitl_thresholds.v1.json`: `t_high = null`, `t_low = null`, `calibrated = false`.
UI-чипы (`web/src/bands.ts`) читают файл: при отсутствии калибровки берут fallback 0,90/0,70 и **обязательно** суффикс «не калибр.». Это не заявление Exact Match ≥0,90 и не закрытие Gate I.

Повторный подбор порогов = новый `version`, не тихая правка того же файла. Смена JSON без смены version ломает sha256-тест.

```
python scripts/hitl_calibration.py silver_samples.jsonl --out out/
```

## Outbox / РиН payload (§9.6, TOP20 #13)

`protocol_for_rin` + `payload_sha256` считаются от **отфильтрованного** тела
(только `CONFIRMED_VIOLATION` / `NEGATIVE_VERIFIED`). Строки `integration_outbox`,
материализованные **до** этого фильтра, хранят sha полного протокола: при
повторной materialize того же `protocol_id` будет `payload_sha256 mismatch`.

Миграция: только **новые** finalize после мержа фильтра; старые PENDING outbox —
ручной `retry_failed_sync` **не** пересчитывает sha. При необходимости —
явная rematerialize/новый protocol version, не silent rewrite.
