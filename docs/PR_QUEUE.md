# Очередь открытых PR (18.09.2026)

Все 14 PR независимо от `origin/main` `abbe107`. GitHub пишет MERGEABLE;
последовательно они конфликтуют на `test_rt_suites.py`, `README.md`,
`text.py`, `GATE_M_REDTEAM_AUDIT.md`.

Не мержить пачкой. Не принимать описания PR как факт состояния `main`.
Коммита в этом дереве нет: годные куски влиты локально.

## Проверка локальной сборки (после разбора)

- `ruff check backend scripts` — чисто
- `mypy --strict backend/src` — чисто
- `pytest backend/tests` — 540 passed, 1 xfailed (`RT-G`)
- `scripts/check_claims.py` / `check_contracts.py` — чисто
- `compile_matrix.py` — 132 правила, 28 override-файлов, **26 executable**
  (20 гейта H + KR-055 + PZ-013/015/021/022/023). IOS4-078/079 остаются
  `extractor_missing` (GAP-IOS4).

На `abbe107` в `data/matrix/rules/` executable был только PZ-001
(overrides не были прогнаны через compile). Тесты гейта H читают
скомпилированные `rules/`, поэтому «20 executable» на голом main не
соблюдалось. Это не молчаливая правка каталога: coverage берётся из
уже существовавших `overrides/`.

## Не брать

| PR | Почему |
|---|---|
| #8 Gate J | Четыре файла — одна строка base64. Пороги P/R/F1 на n=15 не публикуем |
| #10 Gate L BFF | Дубль `gateway/`. OpenAPI 3.0.3 при контракте 3.1.0 |
| #13 `infrastructure/intake.py` | Второй приём с кодами вне контракта. Zip-бомба влита в `application/intake.py` как `CORRUPTED_FILE` |
| #20 / #21 docs | Пишут xfail=0 и 27 executable до merge. Пороги без frozen corpus |

## Брать по частям (уже в локальном дереве, без коммита)

| PR | Что взято | Что отброшено / поправлено |
|---|---|---|
| #11 KR-055 | `text.py`, ветка enum в `evaluate.py`, KR-055 executable, E2E | цифры «21→22», прогноз F1 как замер |
| #12 PZ-013/015/021–023 | overrides + `regex=null` → `LOW_QUALITY`, E2E | правка generated `rules/*.json` в обход override |
| #14 Docker | `Makefile` (`python` на Windows), `docker-compose.offline.yml`, `scripts/docker-pull.sh` | перезапись `docker-compose.yml` и README |
| #15 RT-C | `injection_scan.py` + oracle в `test_rt_suites.py` | отдельный `test_dual_read.py`, если дублирует гейт I |
| #16 Redis | `cache.py` (паспорт по SHA-256), клиент через Protocol | снятие xfail RT-G: кэш ≠ идемпотентность находки |
| #17 RT-H | `access_control.py` | — |
| #18 RT-I | oracle против `web/src/App.tsx` | README «27/132» |
| #19 RT-E/F | `normative_db.py` как overlay, без вердикта матрицы | заявление «все stop-ship закрыты» |

Дополнительно, чтобы гейт H и compile сошлись:

- у number-override добавлены `decimal_comma` / `strip_unit` (скелет каталога
  без запятой не разбирает «5000,0»);
- `extract_number` берёт первую непустую группу regex (альтернативы мм|м);
- `dual_read_required=false` соблюдается и на числовой ветке;
- regex AR-041 принимает значение без суффикса «м» (синтетика гейта H).

## Отложить

| PR | Почему |
|---|---|
| #9 Gate K | Живой HTML, но `FindingStatus.COMPLIANT` и отдельный `kontur.protocol` расходятся с доменом. UI уже каркас в `web/` |

## Конфликты файлов

- `backend/tests/adversarial/test_rt_suites.py`: #13, #15, #16, #17, #18, #19
- `README.md`: #14, #18, #20
- `extractors/text.py`: #11, #12
- `docs/GATE_M_REDTEAM_AUDIT.md`: #11, #20
