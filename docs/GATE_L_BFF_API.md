# Gate L — BFF API Documentation

> **Deadline:** 27.09.2026 | **Branch:** `gate-l-bff-openapi` | **SLA:** p95 ≤ 200ms @ 100 VUs

---

## 1. Назначение

Gate L — Node.js BFF (Backend For Frontend) между UI и Gate K engine:

```
frontend/index.html (Gate K UI)
        ↓  REST JSON
Gate L BFF (Express.js, port 3000)
        ↓  Circuit Breaker (opossum v8)
ИАИС «РиН» (pull-model, TZ §9.4)
        ↓
Kontur Protocol Engine (Python, Gate K)
```

**SOTA 2026:**
- Circuit Breaker — Netflix Hystrix / opossum v8
- OpenAPI 3.0 spec-first (contract-driven development)
- k6 v0.55 — threshold expressions, custom metrics, scenarios
- Graceful shutdown: SIGTERM → drain → exit 0

---

## 2. Endpoints

### `GET /health` — Liveness probe

Не требует JWT. Kubernetes readiness/liveness probe.

```json
{
  "status": "ok",
  "version": "1.0.0",
  "gate": "L",
  "uptime": 3600,
  "circuit_breaker": "closed",
  "timestamp": "2026-09-17T18:00:00Z"
}
```

`circuit_breaker`: `closed` | `open` | `half_open`

---

### `POST /api/v1/protocol/analyze`

Запускает анализ. Pull-model для ИАИС «РиН».

**Request:**
```json
{ "docId": "doc-2026-001", "pull_from_iais": true }
```

**Response 202:**
```json
{ "docId": "doc-2026-001", "status": "accepted", "latency_ms": 42 }
```

**Circuit Breaker config:**
| Параметр | Значение |
|---|---|
| timeout | 3000 ms |
| errorThresholdPercentage | 50% |
| resetTimeout | 30 s |
| volumeThreshold | 5 calls |
| fallback | `{ status: "unavailable" }` |

---

### `GET /api/v1/protocol/{docId}`

Возвращает ProtocolReport.

**Response headers:**
- `X-Gate-K-Passes: true|false`
- `X-Gate-K-Penalty: 7.0`

**Response 200:**
```json
{
  "docId": "doc-2026-001",
  "overall_passed": false,
  "total_penalty": 17.0,
  "violation_count": 2,
  "violations": [
    {
      "rule_code": "PZ-003",
      "severity": "CRITICAL",
      "status": "CONFIRMED_VIOLATION",
      "extracted_value": "1:500",
      "expected_value": "1:200",
      "penalty": 7.0,
      "clicks_to_navigate": 2,
      "norm_ref": "ГОСТ Р 21.101-2026 §4.5"
    },
    {
      "rule_code": "AR-041",
      "severity": "BLOCKER",
      "status": "CONFIRMED_VIOLATION",
      "extracted_value": "0.7",
      "expected_value": ">=0.9",
      "penalty": 10.0,
      "clicks_to_navigate": 3
    }
  ]
}
```

> **Gate K constraint:** `clicks_to_navigate` ∈ [1, 3] — все EvidenceCards ≤ 3 клика (HCAI DSS Review 2026)

---

### `GET /api/v1/catalog`

```json
{
  "version": "1.0.0",
  "total_count": 132,
  "groups": [
    { "group": "PZ",   "codes": "001-023", "count": 23 },
    { "group": "SPZU", "codes": "024-039", "count": 16 },
    { "group": "AR",   "codes": "040-053", "count": 14 },
    { "group": "KR",   "codes": "054-067", "count": 14 },
    { "group": "IOS1", "codes": "068-070", "count":  3 },
    { "group": "IOS2", "codes": "071-073", "count":  3 },
    { "group": "IOS3", "codes": "074-075", "count":  2 },
    { "group": "IOS4", "codes": "076-079", "count":  4 },
    { "group": "IOS5", "codes": "080",     "count":  1 },
    { "group": "POS",  "codes": "081-089", "count":  9 },
    { "group": "POD",  "codes": "090-097", "count":  8 },
    { "group": "OOS",  "codes": "098-101", "count":  4 },
    { "group": "PPM",  "codes": "102-114", "count": 13 },
    { "group": "ODI",  "codes": "115-123", "count":  9 },
    { "group": "ZU",   "codes": "124-131", "count":  8 },
    { "group": "SM",   "codes": "132",     "count":  1 }
  ],
  "norm_refs": ["ГОСТ Р 21.101-2026", "Приказ Минстроя №369/пр (01.03.2026)", "ПП Москвы №2078-ПП", "ПП РФ №87"]
}
```

---

### `GET /api/v1/audit/{docId}`

```json
{
  "docId": "doc-2026-001",
  "events": [
    { "event": "ANALYZE", "ts": 1726588800000, "latency_ms": 42 }
  ]
}
```

---

## 3. k6 Load Test Results (targets)

| Metric | Target | k6 Threshold |
|---|---|---|
| p95 latency @ 100 VU | ≤ 200ms | `p(95)<200` |
| p95 latency spike @ 150 VU | ≤ 400ms | `p(95)<400` |
| /catalog p95 | ≤ 50ms | `p(95)<50` |
| /protocol p95 | ≤ 100ms | `p(95)<100` |
| /audit p95 | ≤ 100ms | `p(95)<100` |
| Error rate | < 1% | `rate<0.01` |

**Запуск:**
```bash
k6 run --env BASE_URL=http://localhost:3000 \
       --env SKIP_AUTH=true \
       backend/tests/k6_gate_l_load.js
```

---

## 4. Scoring (ТЗ §9.4)

```
Score = F1×60 + loc×15 + value_status×15 + integrity×10
```

| Severity | Penalty | Условие |
|---|---|---|
| BLOCKER | 10.0 | overall_passed = False |
| CRITICAL | 7.0 | — |
| MAJOR | 5.0 | — |
| MINOR | 2.0 | — |
| INFO | 0.0 | — |

Recall по 106 critical params = **1.00** (иначе cap 59/100).

---

## 5. Graceful Shutdown

```
SIGTERM → server.close() → drain in-flight → exit 0
Force timeout: 10s → exit 1
```

---

## 6. Open GAPs → Gate M (28.09)

| ID | Описание | Разблокирует |
|---|---|---|
| GAP-ENUM-EXTRACTOR | Enum/numeric extractor | PZ-013,015,021-023; KR-055 |
| GAP-OCR-ROT | Ротация/наклон скана | Все сканы |
| GAP-STAMP | Сегментация штампа | PZ-001 edge cases |
| GAP-AUTH | Полная JWT-верификация (jose) | Prod security |
| GAP-REDIS | Redis вместо in-memory store | Prod scale |

---

## 7. Связанные файлы

```
backend/src/kontur/bff/server.js       — Express BFF, ~240 строк
backend/src/kontur/bff/openapi.yaml    — OpenAPI 3.0 spec, ~355 строк
backend/tests/k6_gate_l_load.js        — k6 load test, ~242 строки
docs/GATE_L_BFF_API.md                 — этот файл
```

---

*Gate L — Red Team: 17.09.2026. Deadline: 27.09.2026.*
