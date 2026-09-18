# Очередь PR — закрыта, остаётся только `main`

Разбор 18.09.2026. Уникальные куски влиты в `main` коммитами `4a10ce8` и
последующим. Ветки и PR не оставляем.

## Что вошло в `main`

| PR | Решение |
|---|---|
| #11 KR-055, #12 PZ enum/number | overrides + enum/text экстрактор |
| #13 zip-бомба | только `CORRUPTED_FILE` в `application/intake.py` |
| #14 Docker | Makefile, offline compose, `docker-pull.sh` |
| #15–#19 RT модули | injection/cache/access/normative + оракулы; не README и не xfail=0 |
| #23 IOS4-078/079 | overrides + compile, не правка generated `rules/` в обход |
| #24 RT-G | `put_finding` по `evidence_group_id`; review ищет по `finding_id` |

## Что не брали

| PR | Почему |
|---|---|
| #8 Gate J | base64, пороги на n=15 |
| #9 Gate K | `COMPLIANT`, отдельный `kontur.protocol` |
| #10 Gate L BFF | дубль gateway, OpenAPI 3.0.3 |
| #13 целиком | коды вне контракта |
| #20 / #21 docs | xfail=0 и 27 executable до merge |
| #22 Redis SETNX | не встроен в пайплайн; при ошибке Redis отбрасывает находку |

Не публиковать F1/P/R и recall критических на frozen val. IOS4 на синтетике
не равен площади мм² и не закрывает гейт J.
