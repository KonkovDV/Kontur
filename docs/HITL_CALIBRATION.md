# Калибровка уверенности HITL (SILVER)

`backend/src/kontur/evaluation/calibration.py` + `scripts/hitl_calibration.py`.

- Вход: JSONL `{confidence, correct, split}` на SILVER/новых размеченных. Split `hidden` отвергается — **порог не подбирался на hidden**.
- Выход: `out/hitl_calibration_silver.json` (n, бакеты conf/acc, ECE, t_high, git sha, дата) и `out/hitl_reliability_silver.svg`.
- `t_high` — наименьший порог, где **верхняя** граница Уильсона доли ошибок в зоне ≥ t_high ≤ `--max-error-rate` (0,10) при n_zone ≥ `--min-n` (30).
- Нет выборки или ни один порог не проходит → `t_high = null`, `status = uncalibrated`.
- Всегда `is_gold = false`, `closes_gate = false`: Gate I/K отчёт не закрывает.

**Текущий статус (15.10.2026): uncalibrated.** Размеченной SILVER-выборки confidence↔correct нет, поэтому пороги чипов UI (90/70%) — некалиброванные эвристики, ниже порога — очередь инспектора, не авто-нарушение.

```
python scripts/hitl_calibration.py silver_samples.jsonl --out out/
```
