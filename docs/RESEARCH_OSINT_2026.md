# OSINT / Document AI: зафиксированный срез 20.09.2026

Исследовательская записка. **Не** bake-off Kontur, **не** закрытие гейтов I/J,
**не** выбор production-модели. GPU-прогон на ПД/РД/ИД не выполнялся.
Hidden test не открывался. Публичные SOTA-цифры на порог ТЗ не переносятся.

Полная программа трёх контуров: [`TZ_COMPLETION.md`](TZ_COMPLETION.md),
[`TZ_SCORECARD.md`](TZ_SCORECARD.md). Протокол: [ADR-0009](adr/0009-atomic-protocol-materialization.md).

## Поправки к внешнему memo

1. SHA `695d9c7` / «PR #64 открыт» — устарели. #64 влит; scorecard/lock — PR #65.
2. `assemble_protocol()` **намеренно** без `kind`/`assembled`: схема ТЗ
   `additionalProperties: false`. Predicate
   `kind IS DISTINCT FROM 'materialized'` **запрещён** — отклонит валидный протокол.
3. Fail-closed sync: `PROTOCOL_FINALIZED` + hex `payload_sha256` + отказ
   placeholder / `assembled=false`. Missing `assembled` — штатный JSON.
4. `version` передаётся в `assemble_protocol`, не зашит как 1.
5. Три контура готовности ведутся JSON-чеклистом, без процента «по ТЗ».

## Независимо проверенные источники (поиск 20.09.2026)

| Источник | Что подтверждено | Что остаётся claim |
|---|---|---|
| OmniDocBench, CVPR 2025, Open Access | бенчмарк PDF parsing, 19 layout categories, репозиторий OpenDataLab | неприменимость к российским ПД/РД/ИД — экспертная оценка, не метрика ТЗ |
| PaddleOCR-VL 0.9B, Apache-2.0, HF `PaddlePaddle/PaddleOCR-VL` | компактная multilingual модель, в карточке указана кириллица/русский | SOTA и качество штампов АЭК — self-reported, нужен GOLD Kontur |
| MinerU2.5, arXiv:2509.22186, 1.2B | coarse-to-fine: layout на даунскейле, recognition на native crop | лицензия кода/весов проверяется **на конкретный digest**, не по README |

Гибрид vector-first + OCR/layout cascade + VLM как второй читатель согласуется с
ADR-0001. VLM не юридический арбитр. OmniDocBench не заменяет object-level GOLD.

## Bake-off (ещё не запускался)

Кандидаты на **один** frozen GOLD Kontur, не на leaderboard: pdfium (канон
вектора), Tesseract (независимый crop), PaddleOCR-VL, MinerU2.5, Docling как
adapter baseline, Qwen2.5-VL только advisory. Решение — ADR после замера:
качество, устойчивость, latency, VRAM, детерминизм, лицензия digest.

## Stop-the-line (дополнительно к AGENTS.md)

Не называть GHA `/status` p95 production SLA. Не подменять Gate K рекордером.
Не грузить pickle/`trust_remote_code` без review. Не заявлять УКЭП без
провайдера и sandbox-контракта в репозитории.
