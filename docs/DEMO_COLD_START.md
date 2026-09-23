# Холодный запуск демо (issue #78)

Репетиция 4-минутного сценария на чистой машине. Не Polar, не TEST_HIDDEN,
не закрытие гейтов I/J/K. Видео запасного демо пишет человек.

Доказуемая репетиция — in-process pytest (синтетические кириллические PDF),
не объект `10_Полярная_25_СОШ1100к7`. Coverage на момент среза:
44 executable / 83 extractor_missing / 1 advisory / 4 source_missing из 132
объявленных. Это разбивка, не заявление, что вся матрица executable.

## Что считается успехом

1. `docker compose up -d` поднимает postgres, redis, rabbitmq, minio, core,
   outbox-relay, inbox-consumer, gateway.
2. Загрузка ПД (черновик без штампа, затем утверждённая редакция), РД, ИД.
3. Паспорт читает штамп «Утвердил» + ФИО. Явный «не утв.» не эталон.
   Одна ПД без этой пометки — `PACKAGE_DEFAULT`. Две редакции ПД без
   successor — `CLARIFICATION_REQUIRED`, пока инспектор не назначит эталон.
   Голова — не последний загруженный файл. Разные шифры стадии — отдельные
   головы, не конфликт комплекта.
4. Три кандидата: `PZ-001`, `KR-055`, `AR-041`. Автомат не пишет
   `CONFIRMED_VIOLATION`.
5. Инспектор confirm/reject с комментарием; REJECT — с `reason_code`.
6. `verify` → `complete` → `finalize` → protocol v1 (`PROTOCOL_FINALIZED`).
   Прямой `complete` из `READY` — 409. Карман `AUTO_NO_DIFFERENCE` на провод ТЗ не выходит.
7. Outbox `PENDING`, destination `RIN`. Confirm брокера ≠ бизнес-ACK РиН.

Стоп: Polar как frozen val; открытие TEST_HIDDEN; «гейт K закрыт» без пяти
сессий; `KONTUR_ALLOW_INSECURE_DEV_AUTH` в production.

## Репетиция без Docker (CI и Windows)

```text
python -m pytest backend/tests/test_demo_cold_start.py -q --tb=short
python scripts/demo_cold_start.py
```

На Linux с GNU make: `make demo-rehearsal`.

## Compose на чистой машине

Нужны Docker Compose v2, Python ≥3.11, TTF с кириллицей (DejaVu/Arial).
JWT по умолчанию проверяется. Для локального прогона **только** на loopback:

```text
copy .env.example .env          # Windows; иначе cp
```

В `.env` для этой репетиции: `KONTUR_ALLOW_INSECURE_DEV_AUTH=true`.
Это не OIDC и не production. Порты ядра — `127.0.0.1:8000`.

```text
docker compose up -d
curl -s http://127.0.0.1:8000/api/v1/healthz
```

Токен legacy (тот же флаг): `inspector-1@OBJ-DEMO-COLD-START/INSPECTOR`.
Фикстуры PDF даёт pytest; для HTTP их можно выгрузить из теста или собрать
тем же `cyrillic_pdf`, что в `backend/tests/pdf_fixtures.py`.

Порядок загрузки (один `process_id` со второго запроса):

1. `doc_stage=PD` — черновик без штампа.
2. `doc_stage=PD` — утверждённый лист (эталон).
3. `doc_stage=RD` — расхождения по трём полям.
4. `doc_stage=ID` — совпадает с утверждённой ПД (стадия загружена, не эталон ПД).

Дальше: `GET .../status` → `GET .../findings/{id}/evidence-card` (ПД и РД с
polygon, пустая ИД — нет фрагмента) → `POST .../findings/{id}/review` на
`pipe-PZ-001`, `pipe-KR-055`, `pipe-AR-041` → `POST .../verify` →
`POST .../complete` → `POST .../finalize` → `GET .../protocol`.
В `sections` нет `preliminary_no_difference`. Явный «не утв.» не назначается эталоном.

Outbox остаётся `PENDING`, пока relay не подтвердит брокер. Это не `SYNCED`.

## Что это не закрывает

| Тема | Статус |
|---|---|
| Гейт I (OCR) | открыт, `ocr_text=MEASURED`, замер ниже порога |
| Гейт J (frozen val) | открыт; Polar не gold |
| Гейт K (пять сессий) | открыт; рекордер не сессии |
| Видео | человек |
| РиН ACK | нет sandbox-контракта |
