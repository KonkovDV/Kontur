# Топ‑10 открытых GitHub-репозиториев для Контура

Срез: **15.10.2026 (MSK)**. Цель — не «самые звёздные BIM-инструменты», а
то, что полезно **Контуру** (задача №10 ЛЦТ / Мосгосстройнадзор): сверка
ПД ↔ РД ↔ ИД по матрице 132 параметров, голова редакции, evidence
(файл / страница / SHA-256 / polygon), HITL-инспектор, офлайн‑стенд.

Контур сегодня — **документный** компаратор PDF/DOCX, не IFC-clash. IFC и
point cloud ниже — соседний контур (будущий цифровой двойник / сканы
площадки). Идеи оттуда переносим **паттернами**, не копируем код с
несовместимой лицензией.

Звёзды и даты обновления — по GitHub API на 15.10.2026. Клоны для разбора
кода: `/workspace/kontur-osint/repos/` на машине агента (не в git Контура).

## Критерии отбора

| Критерий | Вес для Контура |
|---|---|
| Семантический diff ревизий / стадий | высокий |
| Правила как данные (IDS / schema) | высокий |
| Confidence / quality gate для измерений | высокий |
| Evidence / issue export (BCF-подобные карточки) | средний |
| Viewer / clash / scan-to-BIM | низкий сейчас, средний на road map |
| Лицензия, пригодная госзаказчику / офлайну | отсекающий |

## Таблица топ‑10 (ранг = полезность Контуру)

| # | Репозиторий | ★ | Лицензия | Язык | Зачем Контуру | Вердикт |
|---|---|---|---|---|---|---|
| 1 | [IfcOpenShell/IfcOpenShell](https://github.com/IfcOpenShell/IfcOpenShell) (+ пакет `ifcdiff`) | 2860 | LGPL-3.0 | C++/Python | Эталонный IFC: `ifcdiff` сравнивает геометрию, свойства, связи, контейнеры; JSON-выход | **Паттерны** (канонизация сущности, precision). В PDF-путь не тащить как dep |
| 2 | [buildingSMART/IDS](https://github.com/buildingSMART/IDS) | 325 | buildingSMART (NOASSERTION) | C#/XML | Стандарт «правила как данные» для IFC. Параллель к `data/matrix/` и ADR-0004 | **Изучить схему** IDS 1.0; матрицу 132 не подменять IDS, но держать экспорт/импорт в уме |
| 3 | [mzat-dev/bimdiff](https://github.com/mzat-dev/bimdiff) | 4 | **AGPL-3.0** | Python | Semantic diff: GlobalId, Pset, geometry summary, severity, `filter_noise`, JSON/CSV/HTML | **Паттерны UX/API** (шум экспорта, severity). Код AGPL в продукт **не** копировать |
| 4 | [kaan36875/BIMDelta](https://github.com/kaan36875/BIMDelta) | 0 | MIT | Python/TS | Diff + fallback matching по Tag при смене GlobalId; GitHub Action с комментарием PR; monorepo FastAPI+web | **Перенять**: стабильный ключ сопоставления + CI-комментарий к диффу (для матрицы/корпуса) |
| 5 | [buildingSMART/BCF-API](https://github.com/buildingSMART/BCF-API) | 240 | buildingSMART | spec | Контракт issue/viewpoint. Карточка Контура (evidence_group) ближе к BCF topic, чем к «сырому LLM» | **Маппинг** finding → BCF-подобное поле при выгрузке в РиН (после sandbox) |
| 6 | [CyberbuildLab/pcd-bim-matching-confidence](https://github.com/CyberbuildLab/pcd-bim-matching-confidence) | 7 | Apache-2.0 | Python | Confidence = coverage × distance × distribution (KL); статья *Automation in Construction* 181 (2026) | **Перенять метрики уверенности** на экстракторы/OCR (не только scan↔IFC) |
| 7 | [rsasaki0109/bim-quality-checker](https://github.com/rsasaki0109/bim-quality-checker) | 0 | MIT | Python | Chamfer, coverage, per-element; reusable workflow `bim-quality-gate.yml` | **Перенять CI quality gate** для coverage матрицы / SILVER OCR (порог + PR comment) |
| 8 | [ThatOpen/engine_web-ifc](https://github.com/ThatOpen/engine_web-ifc) | 1063 | MPL-2.0 | TS | Клиентский парсер IFC (WASM). База viewer'ов ThatOpen / ClashControl | **Держать** как кандидат viewer-слоя, если появится IFC-вход |
| 9 | [clashcontrol-io/ClashControl](https://github.com/clashcontrol-io/ClashControl) | 20 | **SSPL v1** | HTML/JS | As-built: point cloud↔IFC, ICP, heatmap, auto-BCF, AI provenance chip, offline PWA | **UX идеи** (heatmap отклонений, chip «ИИ + модель + время»). SSPL — **не** в продукт |
| 10 | [louistrue/ids-flow](https://github.com/louistrue/ids-flow) | 27 | AGPL-3.0 | TS | Визуальный редактор IDS → XML | **UI-паттерн** редактора правил для матрицы 132. Код AGPL не копировать |

### Ближайший запас (не вошли в 10, но смотрели)

| Репозиторий | ★ | Заметка |
|---|---|---|
| [xeokit/xeokit-bim-viewer](https://github.com/xeokit/xeokit-bim-viewer) | 568 | AGPL viewer + point cloud; мощный, лицензия тяжёлая |
| [ThatOpen/web-ifc-viewer](https://github.com/ThatOpen/web-ifc-viewer) | 1037 | Toolkit поверх web-ifc |
| [bimrocket/bimrocket](https://github.com/bimrocket/bimrocket) | 100 | CDE-like: IFC + BCF в БД |
| [ibuilder/massing](https://github.com/ibuilder/massing) | 123 | Self-hosted AEC + IDS authoring (MIT) — широкий scope, не фокус №10 |
| [OpenAEC-Foundation/OpenAEC-BIM-validator](https://github.com/OpenAEC-Foundation/OpenAEC-BIM-validator) | 2 | IDS validate → 3D → BCF в браузере |
| [Jamazi4/ifcdiff](https://github.com/Jamazi4/ifcdiff) | 0 | Client-only 3D IFC diff (Next+web-ifc) |
| [md-ward/ai-structural-reviewer](https://github.com/md-ward/ai-structural-reviewer) | 0 | PDF drawing AI через **Gemini cloud** — для офлайн/госзаказа Контура **отклонить** |
| [opensourceBIM/BCF-Forum](https://github.com/opensourceBIM/BCF-Forum) | 35 | Устарел (обновление 2024), только как исторический BCF 2.0 |

Русскоязычный поиск (`нормоконтроль`, `исполнительная документация`, `Мосгосстройнадзор`) по GitHub API 15.10 либо пуст, либо упёрся в rate limit после серии запросов. Отдельного «открытого Контура-клона» в выдаче не найдено.

## Что перенять прямо сейчас (без IFC в runtime)

1. **Шум ревизии** (`bimdiff.filter_noise`): в ПД/РД штамп/метаданные/невидимый текст дают ложные «изменения». У Контура уже есть знак триггера и голова редакции — добавить явный список «шумных» полей штампа в ADR/тестах.
2. **Severity / confidence**: severity по доле изменённых сущностей (bimdiff) + coverage/distance/distribution (CyberbuildLab) → для OCR/экстрактора вместо одного порога 0,95.
3. **CI quality gate** (bim-quality-checker workflow): отдельный job «matrix coverage ≥ N executable» и «SILVER OCR Wilson low ≥ …» с комментарием в PR.
4. **Стабильный ключ сопоставления** (BIMDelta Tag fallback): аналог `comparison_key` / шифра штампа — уже есть; усилить тестами «переименовали файл, GlobalId/шифр тот же».
5. **BCF-shaped finding**: поля topic/viewpoint ↔ `evidence_group_id` + page + polygon — контракт на будущее для РиН.

## Что отвергнуть

| Идея | Почему |
|---|---|
| Тянуть AGPL/SSPL код в vendor | Лицензия Контура для заказчика закрытая; AGPL/SSPL заражают SaaS |
| Cloud VLM (Gemini и аналоги) в зачётный прогон | Ответ организатора 23; офлайн обязателен |
| Подменить матрицу 132 проверкой «проект vs СНиП» | ADR-0006: сверка документов, не норм. TimDoc/RomanAI/Цифровой нормоконтроль — другой продукт |
| Clash hard/soft как ядро №10 | ТЗ — камеральная сверка томов ПД/РД/ИД, не коллизии MEP |
| Копировать ClashControl as-built целиком | SSPL + другой объект (scan↔IFC), не PDF-матрица |

## SOTA-паттерны (академический слой)

| Паттерн | Источник | Следствие для Контура |
|---|---|---|
| Canonical entity → match by stable id → field diff | IfcDiff, bimdiff, BIMDelta | Уже близко: шифр/голова редакции → правило → evidence |
| Bounding-box hash, затем дорогая геометрия | bimdiff | Для PDF: сначала vector text layer, затем OCR crop (уже так) |
| Opt-in noise filter | bimdiff | Явный реестр «шум штампа / CropBox / Rotate» |
| Multi-metric confidence | CyberbuildLab 2026 DOI 10.1016/j.autcon.2025.106636 | Не один `score`, а набор индексов + ABSTAIN |
| IDS as delivery contract | buildingSMART IDS | Матрица остаётся своей; IDS — опциональный export для BIM-заказчиков |
| AI provenance chip | ClashControl | Любой LLM-черновик: модель, endpoint, timestamp в аудите (ADR-0001) |

## Как проверяли

- GitHub REST `GET /repos/{owner}/{repo}` и `search/repositories` (часть запросов — rate limit 403).
- README через `raw.githubusercontent.com` и shallow clone пяти репозиториев в `/workspace/kontur-osint/repos/`.
- Сверка с ADR Контура (`0001`, `0004`, `0006`) и `docs/SOTA_AEROBIM_ANALYSIS.md`.

Непереверено первоисточником: коммерческие цифры «accuracy 86%» у конкурентов (см. COMPETITORS). Постер финалистов ЛЦТ — отдельный файл COMPETITORS.
