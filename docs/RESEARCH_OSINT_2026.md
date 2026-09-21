# OSINT / Document AI: срез 21.09.2026

Исследовательская записка. **Не** bake-off Kontur, **не** закрытие гейтов I/J,
**не** выбор production-модели. GPU-прогон на ПД/РД/ИД не выполнялся.
Hidden test не открывался. Публичные SOTA-цифры на порог ТЗ не переносятся.

Полная программа трёх контуров: [`TZ_COMPLETION.md`](TZ_COMPLETION.md),
[`TZ_SCORECARD.md`](TZ_SCORECARD.md). Протокол: [ADR-0009](adr/0009-atomic-protocol-materialization.md).
План: [`WORK_PLAN.md`](WORK_PLAN.md) — freeze инфраструктуры до 29.09.

## Поправки к внешним memo

1. SHA `695d9c7` / «PR #64 открыт» — устарели. `main` на атомарном протоколе,
   outbox/inbox, JWT boundaries (PR #64–#73).
2. `assemble_protocol()` **намеренно** без `kind`/`assembled`: схема ТЗ
   `additionalProperties: false`. Predicate
   `kind IS DISTINCT FROM 'materialized'` **запрещён**.
3. Fail-closed sync: `PROTOCOL_FINALIZED` + hex `payload_sha256`. Missing
   `assembled` — штатный JSON.
4. Publisher confirm брокера **не** `SYNCED` (ADR-0011). Inbox ACK — локальное
   получение, не бизнес-ACK РиН (ADR-0012).
5. Три контура готовности ведутся JSON-чеклистом, без процента «по ТЗ».
6. **PaddleOCR-VL:** в первичных карточках уверенно подтверждена линейка
   **1.5** (0.9B, OmniDocBench v1.5 self-reported). Упоминание 1.6 требует
   повторной проверки model card, лицензии и доступности весов.
7. OmniDocBench / ParseBench не репрезентируют российские ПД/РД/ИД и не
   заменяют object-level GOLD. Оценка — символы, поля, таблицы, reading
   order, bbox, semantic mapping, правило; не «качество Markdown».
8. MinerU2.5 (coarse layout + native crop) логичен для A0/A1, но только с
   фиксацией digest кода/весов, лицензии, VRAM и русского AEC GOLD.
9. Docling — MIT baseline/adapter с bbox, не доменная модель Kontur.
10. Prompt injection в PDF (OWASP indirect/multimodal): содержимое документа
    — недоверенные данные; VLM без tool/write; текст не в system prompt;
    schema-constrained candidate + deterministic validation.

## Независимо проверенные источники (поиск 20–21.09.2026)

| Источник | Что подтверждено | Что остаётся claim |
|---|---|---|
| OmniDocBench, CVPR 2025 | бенчмарк PDF parsing | неприменимость к АЭК РФ — экспертная оценка |
| ParseBench 2026 | Markdown ≠ grounding | порог ТЗ не переносится |
| PaddleOCR-VL 1.5, 0.9B, Apache-2.0 | multilingual parsing, в карточке кириллица | SOTA штампов АЭК — self-reported |
| MinerU2.5, arXiv:2509.22186 | coarse-to-fine native crop | лицензия/digest проверяется на конкретный артефакт |
| AECV-Bench / DrawingVQA / AEC-Bench | OCR лучше spatial/cross-sheet | не замер Kontur |
| OWASP LLM/document injection | PDF как недоверенный ввод | свой adversarial pack ещё не собран |

Гибрид vector-first + OCR/layout cascade + VLM как второй читатель согласуется с
ADR-0001. VLM не юридический арбитр.

## Bake-off (ещё не запускался)

Кандидаты на **один** frozen GOLD Kontur: pdfium (канон вектора), Tesseract
(независимый crop), PaddleOCR-VL-1.5, MinerU2.5, Docling как adapter,
Qwen2.5-VL только advisory. Главная метрика bake-off — **silent numeric
error**, не Markdown. n=50–100 разрешённых страниц, не TEST_HIDDEN.

## Дисбаланс на 21.09.2026

Транспорт и протокол сильнее, чем обнаружение расхождений: 29 executable /
103 extractor_missing. Critical path до 29.09 — вертикальный срез
PDF → evidence → инспектор → протокол, не новые брокерные компоненты.

## Stop-the-line (дополнительно к AGENTS.md)

Не называть GHA `/status` p95 production SLA. Не подменять Gate K рекордером.
Не грузить pickle/`trust_remote_code` без review. Не заявлять УКЭП без
провайдера и sandbox-контракта в репозитории. Не закрывать I/J по SILVER
или n=6. Не добавлять production-инфру вместо вертикального среза.
