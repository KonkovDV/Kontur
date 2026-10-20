# SOTA 2026-10-15 для Kontur (OCR/VLM, Document AI, HITL, RabbitMQ)

Автор: Red Team (research). Код не правлю. Срез: `KonkovDV/Kontur@main` **040db27** (15.10.2026, ~19:53 МСК). Дедлайн показа: **30.10.2026** (~2 недели).

Цель брифа: что взять из открытого SOTA 2025–2026 **до 30.10**, что отложить, чего избегать. Размеры: **S** ≤ 0,5 дня, **M** 1–2 дня, **L** 3+ дня. Бенчмарки не выдумываю: только опубликованные цифры со ссылками; где нет замера на корпусе Контура — пишу «не измеряли».

---

## 0. Что уже есть в Kontur (база, не повторять)

| Область | Факт в репо | Ключевые артефакты |
|---|---|---|
| OCR primary | `VECTOR_PDFIUM` (pypdfium2 текстовый слой) | `docs/OCR_BAKEOFF.md`, `pdfium_tokens.py` |
| OCR verifier | Tesseract-5 region-crop ×3; fallback/альтернатива — RapidOCR **eslav PP-OCRv5** (ONNX, lock SHA-256, runtime download запрещён) | `ocr_tesseract.py`, `ocr_rapid.py`, `ocr_weights.lock.json`, `vendor/ocr/` |
| Dual-read | `dual_read_required` → согласие primary/verifier, иначе ABSTAIN | `dual_read.py` |
| Gate I | SILVER n=5935; eslav tz_low ≈ **0,663** при пороге 0,95; **не GOLD**, порог не взят | `OCR_BAKEOFF.md`, `ocr_pilot.py` |
| VLM | GOT-OCR2_0 в бейк-оффе **отложен** (нет frozen-val, нет grounded-токенов) | `OCR_BAKEOFF.md`, ADR-0001 |
| Пайплайн doc AI | vector-first → OCR → экстракторы `exact_field` / `presence` / `number` / `element_table`; паспорт; нормализация NFC | `extractors/`, `passport.py`, `normalize.py` |
| Таблицы | Простая «марка + одно число» по токенам; Docling/Camelot — только в ROADMAP W5 «с лицензией OK» | `element_table.py`, `EXTRACTOR_ROADMAP.md` |
| HITL / evidence | Единица = `evidence_group`; polygon source+[0;1]; SHA-256; `CONFIRMED_VIOLATION` только инспектор; UI с оверлеем | ADR-0002, ADR-0007, `evidence_card.py`, `EvidencePane.tsx` |
| RabbitMQ | 3.13; durable **quorum** `kontur.rin.protocol`; transactional outbox (`FOR UPDATE SKIP LOCKED`); publisher confirms; retry 1/5/15 → `FAILED_TERMINAL`; `event_id` стабилен | ADR-0010, `outbox.py`, `outbox_worker.py`, `sync_relay.py` |
| Ограничение зачётного прогона | Облачные OCR/VLM **не входят** в зачётный прогон (ответ организатора 23); веса локально | `README.md`, `JURY_ONEPAGER.md` |

---

## 1. PDF OCR / VLM для стройчертежей и штампов

### 1.1. SOTA-ландшафт (источники)

**Классика + лёгкие VLM OCR (open-weight):**

| Модель / стек | Размер / лицензия | Языки / RU | Опубликованные ориентиры | Ссылка |
|---|---|---|---|---|
| **PaddleOCR-VL / VL-1.6** | ~0,9B, Apache-2.0 | **109 языков, явно Cyrillic/Russian** | OmniDocBench v1.6 overall **96,33%** (заявлено авторами/сравнениями 2026); компактный NaViT + ERNIE-4.5-0.3B | [PaddleOCR-VL docs](https://www.paddleocr.ai/latest/en/version3.x/algorithm/PaddleOCR-VL/PaddleOCR-VL.html), [HF PaddleOCR-VL-1.6](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6), [arxiv 2510.14528](https://arxiv.org/html/2510.14528v4) |
| **PP-OCRv5 eslav** (уже в Контуре) | mobile ONNX | Восточнославянский rec | На SILVER Контура: mean_ca ≈ 0,794, tz_low ≈ 0,663 (n=5935) — **наш** замер, не чужой бенч | `OCR_BAKEOFF.md`, [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) |
| **GOT-OCR 2.0** | ~580M, Apache-2.0 | 20+ | Силён на формулах/таблицах/форматированном тексте; VRAM ~3 GB FP16 (оценка Spheron) | [Spheron OCR/VLM 2026](https://www.spheron.network/blog/best-open-source-ocr-vlm-self-host-gpu-cloud-2026/), HF `ucaslcl/GOT-OCR2_0` |
| **DeepSeek-OCR** | ~3B MoE, MIT | ~100 | Высокий throughput на batch; OmniDocBench v1.6 для этого чекпоинта в обзоре **не приведён** | [Spheron 2026](https://www.spheron.network/blog/best-open-source-ocr-vlm-self-host-gpu-cloud-2026/) |
| **dots.ocr** | ~1,7B, MIT | ~100 | Структурированные формы; без OmniDocBench v1.6 в том же обзоре | то же |
| **Granite-Docling** | 258M, Apache-2.0 | В основном EN | Силён в связке с Docling/таблицами | то же, [Docling](https://github.com/docling-project/docling) |
| **MinerU 2.5** | decoupled VLM | — | Высокое разрешение, layout→content; arXiv 2509.22186 | [arxiv](https://arxiv.org/html/2509.22186) |

**Русский OCR-бенчмарк:** [MWS-Vision-Bench](https://huggingface.co/datasets/MTSAIR/MWS-Vision-Bench) / [mts-ai/MWS-Vision-Bench](https://github.com/mts-ai/MWS-Vision-Bench) — бизнес/тех документы, KIE, grounding, full-page OCR RU. **На Контуре не прогоняли** — полезен как внешняя калибровка, не как замена SILVER/GOLD.

**AEC / title block (чертежи):**

- Pipeline CNN (Faster R-CNN) → crop title block → LLM/VLM IE: arXiv [2504.08645](https://arxiv.org/abs/2504.08645) (EC3 2025). Авторы заявляют высокую точность детекции на vector + historical; цифры detection accuracy в абстракте/companion — **не переносим на ГОСТ-штампы без нашего замера**.
- Open-source VLM workflow на Qwen2.5-VL для title-block detection + schema extraction (scale, drawing name, route): [EC-3 2026 / Peng et al.](https://ec-3.org/publication/ec32026_252/).
- BlueprintSymVL (символы на чертежах): текущие VLM **не готовы** к автономному разбору плотных символов; HITL обязателен ([Chalmers PDF](https://research.chalmers.se/publication/549362/file/549362_Fulltext.pdf)).

**Стоимость CPU/GPU (ориентиры сторонних замеров, не Контур):**

- Spheron (заморозка цен 23.06.2026 в статье; live L40S ~$0,96/ч на 15.10.2026): PaddleOCR-VL-1.6 ~2 GB FP16, ~45 страниц в минуту на пике декодирования на L40S; полный проход около половины этой скорости; ~$5–8 / 10k pages на spot/on-demand. Источник: [Spheron 2026](https://www.spheron.network/blog/best-open-source-ocr-vlm-self-host-gpu-cloud-2026/).
- Контурский eslav ONNX: **CPU**, 5935 строк за ~88 с (1 поток) в образе — уже приемлемо для verifier/region-crop. GPU не обязателен до 30.10.

### 1.2. Adopt ≤ 30.10 / Defer / Avoid

| | Что | Размер | Зачем |
|---|---|---|---|
| **Adopt** | Двухстадийный штамп: (1) детерминированный crop зоны штампа по якорям ГОСТ / layout heuristic; (2) eslav/Tesseract **только на кропе** + dual-read; при disagreement → `LOW_QUALITY`/`ABSTAIN` | M | Закрывает GAP-STAMP частично без VLM; стыкуется с W1 exact_field паспорта |
| **Adopt** | Прогон **MWS-Vision-Bench** (public val) offline на eslav vs Tesseract — один JSON с n и CI, без заявления «порог взят» | S | Внешняя калибровка RU; честный слайд для показа |
| **Adopt** | Пилот PaddleOCR-VL-0.9B/1.6 **только offline**, на 50–100 кропах штампа, с обязательным grounding к pdfium-токенам; **не** в scoring path | M | Ответить на вопрос «почему не VLM» цифрой на *нашем* корпусе |
| **Defer** | Production VLM primary; fine-tune Qwen2.5-VL / PaddleOCR-VL на штампах | L+ | Нет GOLD, нет GPU в офлайн-сборке, нарушает «не арбитр» |
| **Defer** | Детектор title-block (Faster R-CNN) как отдельный сервис | L | ROI ниже, чем шаблоны ГОСТ + vector anchors до демо |
| **Avoid** | Облачный GPT-4o/Claude как экстрактор в зачётном прогоне | — | Запрет организатора; нет provenance |
| **Avoid** | End-to-end VLM без bbox/grounded tokens | — | Ломает ADR-0001/0002; BlueprintSymVL показывает галлюцинации |
| **Avoid** | Подгонка порога CA на hidden / замена SILVER на «красивый» срез | — | §14.2 ТЗ |

---

## 2. Document AI pipelines

### 2.1. SOTA-паттерны

1. **Vector/text-first, OCR second.** Контур уже здесь. Индустрия 2025–2026 подтверждает hybrid: native PDF → layout parser; scan → OCR/VLM ([Spheron hybrid note](https://www.spheron.network/blog/best-open-source-ocr-vlm-self-host-gpu-cloud-2026/), Docling NativePdfPipeline).
2. **Layout + tables:** [Docling](https://github.com/docling-project/docling) (IBM) — layout (Heron/Egret), TableFormer ACCURATE/FAST, reading order, provenance в DoclingDocument; DocEng 2026 talk. Альтернативы: MinerU2.5 (decoupled layout→parse), Camelot/tabula только на vector tables.
3. **Confidence / abstain:** selective prediction — при низком согласии dual-read или coverage=0 → ABSTAIN/LOW_QUALITY, не «угадай». Контур уже кодирует это в dual_read и статусах.
4. **Evaluation:** evidence_group как единица (ADR-0002); EM ключевых полей с n и Wilson CI; не page-level accuracy.

### 2.2. Что в Контуре vs дыры

- Есть: pdfium tokens/vectors/visual, CropBox/Rotate, dual-read, семейства экстракторов, element_table (простой), scorecard + EXTRACTOR_FAMILY_TRIAGE.
- Нет / partial: полноценный table structure (merged cells), Sentence-BERT якоря (§9.1), инкрементальный пересчёт, Docling в runtime.

### 2.3. Adopt / Defer / Avoid

| | Что | Размер |
|---|---|---|
| **Adopt** | W1 exact_field штампа (шифр, стадия, редакция, лист, помещение) + EM отчёт с n/CI на SILVER | M (уже в BRIEF_TZ_TOP20) |
| **Adopt** | Presence-каталог разделов (ZU-129, KR-063…) — детерминированные заголовки, не NLP | M |
| **Adopt** | Offline bake-off Docling TableFormer **ACCURATE** vs текущий `element_table` на 20–30 спецификациях ОВ/АР; лицензия Apache OK → решение W5 go/no-go | M |
| **Defer** | Вшить Docling в hot path до bake-off | L |
| **Defer** | all-MiniLM якоря (§9.1) — только если останется буфер после W1/W2 | M |
| **Avoid** | Объявлять executable без 5 веток триажа + фикстур | — |
| **Avoid** | LLM как компаратор параметров / арбитр редакции | — |
| **Avoid** | «% ТЗ закрыт» без scorecard dump | — |

---

## 3. HITL evidence (provenance, bbox, UX, audit, calibration)

### 3.1. SOTA-практики

- **Field-level citations:** page + bbox на каждое извлечённое поле; UI прыгает и подсвечивает ([Extend Citations](https://www.extend.ai/resources/product-spotlight-citations-reasoning), [Tensorlake field citations](https://dev.to/tensorlake/make-rag-provable-page-bbox-citations-for-all-extracted-data-4ipc)).
- **HITL routing:** низкая confidence / rule fail → очередь ревью; per-field diff + reviewer id + timestamp ([AWS GenAI-IDP HITL](https://aws-solutions-library-samples.github.io/accelerated-intelligent-document-processing-on-aws/human-review/), [Google Document AI HITL](https://codelabs.developers.google.com/codelabs/docai-hitl)).
- **Calibration:** 500–2000 своих документов; бакеты confidence → фактическая error rate; порог от риска, не от слайда вендора; перекалибровка ([Parseur HITL](https://parseur.com/blog/hitl-best-practices)).
- **Audit trail:** кто/что/когда/почему; corrections → будущий training set.

### 3.2. Контур уже силён здесь

EvidencePane с polygon_norm оверлеем, метаданные документа/утверждения, audit list, запрет авто-`CONFIRMED_VIOLATION`, `MISSING_EVIDENCE` ≠ нарушение, ADR-0007 (утверждение только с явным доказательством). Это **конкурентное преимущество** против «99/132 без evidence».

### 3.3. Adopt / Defer / Avoid

| | Что | Размер |
|---|---|---|
| **Adopt** | Demo UX: keyboard next/prev CANDIDATE; zoom-to-bbox одной клавишей; цветовой код confidence (согласован dual-read / LOW / ABSTAIN) | S–M |
| **Adopt** | Калибровочный отчёт: бакеты confidence × фактическая ошибка на SILVER (хотя бы EM ключевых полей); порог HITL задокументировать | S |
| **Adopt** | Snapshot e2e: finalize с открытым CANDIDATE → 409; audit после unfinalize с причиной | S |
| **Defer** | Feedback loop «правка инспектора → fine-tune OCR» | L (после GOLD) |
| **Defer** | Reasoning traces VLM рядом с citation | — не в зачёте |
| **Avoid** | Автоподтверждение нарушения по порогу ML | ADR + ТЗ |
| **Avoid** | Скрывать `extractor_missing` в UI | — |
| **Avoid** | Подмена эталона эвристикой «ГИП» без SELECT_REVISION | ADR-0007 |

---

## 4. RabbitMQ patterns

### 4.1. SOTA (официальные доки)

- **Quorum queues** — default для критичных durable очередей; Raft; publisher confirms; manual ack; poison → `delivery-limit` (default 20 с 4.0) + DLX; at-least-once dead-lettering при `dead-letter-strategy=at-least-once` + `overflow=reject-publish` ([Quorum Queues](https://www.rabbitmq.com/docs/quorum-queues), [DLX](https://www.rabbitmq.com/docs/dlx), [Reliability](https://www.rabbitmq.com/docs/reliability)).
- **Outbox / Inbox:** атомарно domain+outbox в PG → poll/worker → publish confirm; consumer **идемпотентен** (inbox по `event_id`); at-least-once, не exactly-once к брокеру ([Reliability](https://www.rabbitmq.com/docs/reliability); практический outbox+DLQ: [Level Up / outbox part 2](https://levelup.gitconnected.com/transactional-outbox-with-rabbitmq-part-2-handling-retries-dead-letter-queues-and-observability-d53217cf45e9)).
- **Streams:** append-only log, replay/audit/fan-out; **без DLX**; не замена work-queue для Rin protocol ([Streams](https://www.rabbitmq.com/docs/streams)).
- **Delayed retry** (RabbitMQ ≥ 4.3): linear backoff на quorum — у Контура сейчас **3.13**, свои паузы 1/5/15 мин в outbox worker — этого достаточно.

### 4.2. Контур vs пробелы

| Уже есть | Нет / слабо |
|---|---|
| Quorum `kontur.rin.protocol`, outbox SKIP LOCKED, confirms, SHA-256 payload, retry 1/5/15, FAILED_TERMINAL, стабильный `event_id` | Consumer **inbox** (дедуп) — заявлено в ADR/комментариях, в демо-пути проверить |
| Compose user `kontur`, отдельный relay container | DLX / dead-letter stream на poison; метрики глубины очереди в Prometheus (§13) |
| | Streams для audit replay (не нужны до 30.10) |

### 4.3. Adopt / Defer / Avoid

| | Что | Размер |
|---|---|---|
| **Adopt** | Явный **inbox** consumer: уникальный `event_id` → идемпотентная запись; тест «дважды publish → один эффект» | M |
| **Adopt** | DLX (или stream-sink) на `kontur.rin.protocol` + policy `delivery-limit`; UI/док: «сообщения не теряются молча» | S–M |
| **Adopt** | Prometheus gauge: outbox PENDING/DELIVERING/FAILED_TERMINAL + RabbitMQ queue depth (закрывает кусок §13) | S |
| **Defer** | Upgrade broker 3.13 → 4.x ради delayed-retry (свои 1/5/15 уже ок) | — риск до демо |
| **Defer** | Streams как audit log протокола | после финала |
| **Avoid** | Classic queue с тем же именем (ADR-0010: конфликт с volume) | — |
| **Avoid** | Заявлять «exactly-once до РиН» или «доставлено в ИАИС» по confirm брокера | ADR-0010 |
| **Avoid** | `delivery-limit=-1` без DLX | риск poison loop |

---

## 5. Top-10 adopt до 30.10 (impact / effort)

Ранжирование: влияние на показ (живой сценарий + evidence + честные метрики) и на закрытие ТЗ при минимальном риске для durable.

| # | Действие | Область | Размер | Impact | Effort | Почему сейчас |
|---|---|---|---|---|---|---|
| 1 | W1 exact_field штампа (5 полей) + dual-read + EM с n/CI | Doc AI / OCR | M | ★★★★★ | M | Максимум баллов «живой сценарий» + §14.3 |
| 2 | Demo HITL: zoom-to-bbox + keyboard queue CANDIDATE + цветовой confidence | HITL | S–M | ★★★★★ | S | Жюри смотрит UI 3–5 мин |
| 3 | Калибровка confidence → HITL threshold на SILVER (отчёт, не магия) | HITL | S | ★★★★ | S | Отличает от «99 без калибровки» |
| 4 | Stamp crop pipeline (GAP-STAMP) без VLM | OCR | M | ★★★★ | M | Поднимает verifier на штампах |
| 5 | Inbox идемпотентность + тест двойной доставки | RabbitMQ | M | ★★★★ | M | Честный Rin path на демо |
| 6 | Presence W2 (2–3 раздела с явными заголовками) | Doc AI | M | ★★★★ | M | Комплектность на протоколе |
| 7 | DLX/delivery-limit на quorum + метрика outbox | RabbitMQ | S | ★★★ | S | Не терять poison; §13 |
| 8 | Offline Docling table bake-off (go/no-go W5) | Doc AI | M | ★★★ | M | Не блокирует демо; готовит post-30.10 |
| 9 | MWS-Vision-Bench smoke (eslav vs tess) | OCR | S | ★★★ | S | Внешняя RU-калибровка на слайд |
| 10 | Offline PaddleOCR-VL pilot на 50–100 кропах штампа (не scoring) | OCR/VLM | M | ★★ | M | Ответ «почему hybrid, не VLM» с цифрой |

**Суммарно реально до 30.10:** #1–#7 обязательны; #8–#10 — если буфер после W1.

---

## 6. Чего не делать (короткий стоп-лист)

1. Не ставить VLM арбитром редакции/утверждения/нарушения.
2. Не тащить облачный Document AI в зачётный прогон.
3. Не апгрейдить RabbitMQ 4.x / PG18 / React 19 «ради SOTA» до финала.
4. Не объявлять Gate I/J закрытыми без n, 95% CI и GOLD.
5. Не подменять outbox confirm фразой «доставлено в РиН».
6. Не раздувать executable без EXTRACTOR_FAMILY_TRIAGE.

---

## 7. Источники (основные)

- Kontur: `docs/OCR_BAKEOFF.md`, ADR-0002/0007/0010, `EXTRACTOR_ROADMAP.md`, `JURY_ONEPAGER.md`, код `dual_read` / `outbox` / `EvidencePane`.
- [PaddleOCR-VL](https://www.paddleocr.ai/latest/en/version3.x/algorithm/PaddleOCR-VL/PaddleOCR-VL.html) · [HF VL-1.6](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6) · [arxiv 2510.14528](https://arxiv.org/html/2510.14528v4)
- [Spheron open OCR/VLM 2026](https://www.spheron.network/blog/best-open-source-ocr-vlm-self-host-gpu-cloud-2026/)
- [MWS-Vision-Bench](https://huggingface.co/datasets/MTSAIR/MWS-Vision-Bench) · [GitHub](https://github.com/mts-ai/MWS-Vision-Bench)
- Title blocks: [arxiv 2504.08645](https://arxiv.org/abs/2504.08645) · [EC-3 Qwen-VL](https://ec-3.org/publication/ec32026_252/) · [BlueprintSymVL](https://research.chalmers.se/publication/549362/file/549362_Fulltext.pdf)
- [Docling](https://github.com/docling-project/docling) · [MinerU2.5](https://arxiv.org/html/2509.22186)
- HITL: [Extend citations](https://www.extend.ai/resources/product-spotlight-citations-reasoning) · [AWS GenAI-IDP](https://aws-solutions-library-samples.github.io/accelerated-intelligent-document-processing-on-aws/human-review/) · [Parseur](https://parseur.com/blog/hitl-best-practices) · [Tensorlake](https://dev.to/tensorlake/make-rag-provable-page-bbox-citations-for-all-extracted-data-4ipc)
- RabbitMQ: [Quorum](https://www.rabbitmq.com/docs/quorum-queues) · [DLX](https://www.rabbitmq.com/docs/dlx) · [Streams](https://www.rabbitmq.com/docs/streams) · [Reliability](https://www.rabbitmq.com/docs/reliability)

---


> Статус на `main@5c768c9`: executable 59/132; Gate I/J/K/L = false. Чужие бенчмарки приведены со ссылками; на корпусе Контура замерено только то, что помечено «наш замер».
