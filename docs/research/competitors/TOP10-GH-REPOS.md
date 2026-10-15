# Топ‑10+ открытых GitHub-репозиториев для Контура

Срез: **15.10.2026 (MSK)**, редакция 3.
Каталог: `docs/research/competitors/` (не пересекается с JURY-доками).

**Якорь ТЗ (v1.1, текст из локального пакета ТЗ пользователя):** PDF/DOCX/XML;
матрица **132**; OCR CA≥**0,95**, EM≥**0,90**; bbox [0;1] после CropBox/Rotate;
HITL; MISSING_EVIDENCE≠нарушение; РиН только подтверждённое; модули §7 №1–12.
Задача — **не BIM-clash** (ADR-0006).

**Календарь ЛЦТ:** пост финалистов «Город»
[t.me/leaders_hack/967](https://t.me/leaders_hack/967) (15.10.2026, ~15:17 MSK);
ЛЦТ.Фест / награждение **30.10.2026** (чеки 1 000 000 / 600 000 / 400 000 ₽).
По Положению постановщик может взять **больше 10** команд в финал.

Клоны peers для разбора хранились локально у агента и в git не входят.
Связано: [COMPETITORS-OSINT-2026-10-15.md](COMPETITORS-OSINT-2026-10-15.md),
[`../../RESEARCH_OSINT_2026.md`](../../RESEARCH_OSINT_2026.md),
[`../../TZ_SCORECARD.md`](../../TZ_SCORECARD.md), [`../../METRICS.md`](../../METRICS.md).

## Топ по полезности Контуру (прямые peers №10 выше IFC)

| # | Репозиторий | ★ | Lic | Класс | Суть | Вердикт |
|---|---|---|---|---|---|---|
| 1 | [tbikbov/a13-inspector-lct2026](https://github.com/tbikbov/a13-inspector-lct2026) | 0 | — | peer A13 | Fastify+Python workers, Tesseract, LLM **off** по умолчанию, офлайн-пакет, честные §14 (OCR FAIL, F1 строгое не берёт порог), JURY-GUIDE | **Ближайший архитектурный peer** Контуру (fail-closed, LLM≠вердикт) |
| 2 | [midudar/ctrl_z_hackathon](https://github.com/midudar/ctrl_z_hackathon) | 0 | — | peer ctrl_z | Node+React+ml-service; HITL; OCR **кэш из Releases** (EasyOCR/Paddle заранее); claim train P1.00 R0.80 F1 0.89; ~19 params с извлечением | Сильный packaging; OCR в runtime на стенде без кэша слабый |
| 3 | [Evgen74/inspector-ai-public](https://github.com/Evgen74/inspector-ai-public) | 0 | — | peer | NestJS+ONNX PP-OCR; claim 75/132 content; «100/100» Тюменская; XML протокола ❌; скрытый тест остановлен | Эталон объёма ML; не копировать |
| 4 | [Namelomax/AIDocumentAnalize](https://github.com/Namelomax/AIDocumentAnalize) | 0 | — | peer | Offline tar+ClamAV; claim 99/132; OCR **1−CER 0,225** | Offline-pack ориентир; OCR-гейт открыт |
| 5 | [NikolaySalyakhutdinov/gos-stoidoc](https://github.com/NikolaySalyakhutdinov/gos-stoidoc) | 0 | — | peer | MiniLM-132; `drawing_dimension`≠searchable | Паттерн фильтра чертежных размеров |
| 6 | [IfcOpenShell/IfcOpenShell](https://github.com/IfcOpenShell/IfcOpenShell) (`ifcdiff`) | 2860 | LGPL-3.0 | паттерн | JSON IFC diff | Не dep PDF-пути |
| 7 | [mzat-dev/bimdiff](https://github.com/mzat-dev/bimdiff) | 4 | AGPL-3.0 | паттерн | `filter_noise`, severity | Только паттерны |
| 8 | [kaan36875/BIMDelta](https://github.com/kaan36875/BIMDelta) | 0 | MIT | паттерн | Tag fallback; PR Action | CI-комментарий к диффу |
| 9 | [CyberbuildLab/pcd-bim-matching-confidence](https://github.com/CyberbuildLab/pcd-bim-matching-confidence) + [rsasaki0109/bim-quality-checker](https://github.com/rsasaki0109/bim-quality-checker) | 7/0 | Apache/MIT | паттерн | multi-metric confidence; CI gate | На OCR/coverage матрицы |
| 10 | [buildingSMART/IDS](https://github.com/buildingSMART/IDS) + [BCF-API](https://github.com/buildingSMART/BCF-API) / [ThatOpen/engine_web-ifc](https://github.com/ThatOpen/engine_web-ifc) | — | bSI/MPL | паттерн/roadmap | IDS/BCF; WASM IFC | После демо №10 |

### Дополнительно разобраны (не топ‑10)

| Репо | Заметка |
|---|---|
| [Tanoklllmonbku/Hakaton-LDT](https://github.com/Tanoklllmonbku/Hakaton-LDT) + [Kaiman30/Hakaton-LDT-backend](https://github.com/Kaiman30/Hakaton-LDT-backend) | Ранний скелет: Go gateway/auth + архитектура Kafka/Saga в README; **нет** зрелого PDF-компаратора 132. MIT на backend |
| [Crooak/chakaton](https://github.com/Crooak/chakaton) | UI-макет figma-make, только mocks |
| [clashcontrol-io/ClashControl](https://github.com/clashcontrol-io/ClashControl) | SSPL; as-built UX — не копировать |
| [md-ward/ai-structural-reviewer](https://github.com/md-ward/ai-structural-reviewer) | Gemini cloud — отклонить |

Связь peer-репо с **именами** команд на постере / в карточках t.me/967 —
**не verified** (кроме самоназваний `ctrl_z`, `A13` в README).

## Сверка peers с ТЗ §7 (сжато)

| Модуль | Kontur | a13 | ctrl_z | inspector-ai | AIDocument | gos-stoidoc | Hakaton-LDT* | chakaton |
|---|---|---|---|---|---|---|---|---|
| 1 Загрузка | ✅ | ✅ Tess+AV | ✅ +OCR cache Rel. | ✅ ONNX | ✅+ClamAV | ✅ MiniLM | ◐ gateway | ❌ |
| 2 Сравнение | 55 exec | ◐ честные NOT_COMPARABLE | ~19 extract | ~75 content | ~99 decl. | seed 132 | ◐ arch only | ❌ |
| 3 HITL | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ? | UI |
| 5 Free search | ◐ | ✅ workers | ? | ◐ FREE | ◐ | ◐ | ? | ❌ |
| 6 РиН | mock | mock | ? | mock | mock | ? | ? | ❌ |
| OCR CA≥0,95 | Wilson 0,663 | FAIL (пишут) | claim 0,950 на 600 стр. SILVER* | ONNX | CER→0,225 | ? | — | — |
| XML протокол | в контракте | ? | ? | ❌ | ✅ claim | ? | — | — |

\*ctrl_z: OCR 0,950 — их замер EasyOCR vs text-layer SILVER; не скрытый тест орг.
\*Hakaton-LDT = frontend+backend pair.

## Перенять / отвергнуть

**Перенять:** A13-стиль честных FAIL по §14 + JURY-GUIDE; ctrl_z Releases-кэш как идея (но прозрачно маркировать «без кэша — нет сканов»); `drawing_dimension` filter; offline tar+AV; XML удержать; multi-metric confidence; CI coverage gate.

**Отвергнуть:** IFC в демо №10; cloud VLM; копирование peer-кода; путать claim F1 на train с скрытым тестом; «нет документа = нарушение».

## Метод

ТЗ v1.1; t.me/leaders_hack/967 (текст виджета 15.10); GitHub API+clone;
сверка ADR/scorecard. Карточки финалистов в Telegram — изображения, полный
текстовый список имён из поста **не извлечён** (только постер пользователя).
