# OSINT конкурентов и финалистов ЛЦТ — Контур

Срез: **15.10.2026 (MSK)**, редакция 3.
Путь: `docs/research/competitors/` (отдельно от JURY-onepager / сдачи).

## Официальные даты и пост финалистов

| Факт | Источник | Статус |
|---|---|---|
| Пост финалистов направления **«Город»** | [t.me/leaders_hack/967](https://t.me/leaders_hack/967) | **verified** виджет: 15.10.2026 12:17 UTC (**15:17 MSK**) |
| Текст поста | «Эти команды готовы менять город… листай карточки… Следующая остановка — **ЛЦТ.Фест 30 октября**… чеки на 1 000 000, 600 000 и 400 000 рублей» | verified из HTML-виджета t.me/s |
| Положение: можно **>10** команд в финал | тот же пост + зеркало tg.me | verified |
| ЛЦТ.Фест / награждение | **30.10.2026** | verified (пост 967); питчи финалистов в ряде источников — **23.10** (ITMO/новости, search) |
| Имена команд в посте 967 | Карточки-изображения, OCR списка из виджета не извлекали | имена ниже — с **постера** пользователя (кросс с №10) |

Постер пользователя «ФИНАЛИСТЫ ЗАДАЧИ «ГОРОД» №10» согласуется с официальным
раскрытием финалистов «Город» в тот же день; **построчное** равенство постер ↔
карточки Telegram без OCR карточек не доказано.

Связано: [TOP10-GH-REPOS.md](TOP10-GH-REPOS.md),
[`../../RESEARCH_OSINT_2026.md`](../../RESEARCH_OSINT_2026.md),
[`../../SOTA_AEROBIM_ANALYSIS.md`](../../SOTA_AEROBIM_ANALYSIS.md),
[`../../TZ_SCORECARD.md`](../../TZ_SCORECARD.md).
Пакет ТЗ (локальные вложения пользователя) в git не копируется.

## 0. Якорь ТЗ v1.1 (с чем сравниваем peers)

| Требование | Следствие |
|---|---|
| Вход ПД/РД/ИД PDF (+DOCX/XML) | IFC/clash ≠ peer №10 |
| Матрица 132 | Смотрим executable vs «132 строки в JSON» |
| CA≥0,95; EM≥0,90; IoU≥0,50; P≥0,90; R≥0,80; F1≥0,85 | Без замера / ниже порога — гейт открыт |
| HITL: CONFIRMED_VIOLATION только инспектор | LLM-вердикт = провал |
| MISSING_EVIDENCE ≠ нарушение | антипаттерн |
| Офлайн / без внешних API на зачёте | cloud OCR/VLM — дисквалификация пути |

Контур сейчас: 55 executable / 72 extractor_missing; gold 0/6; OCR Wilson low 0,663;
гейты I/J/K/L открыты.

## 1. Финалисты с постера №10

| # | Команда | GH / сайт | Статус |
|---|---|---|---|
| 1 | ИИ Друны | не найдено по имени | постер-verified |
| 2 | Один(нет) в поле воин | не найдено | постер-verified |
| 3 | Броняшки | не найдено | постер-verified |
| 4 | mltech2 | Слабый сигнал: аккаунт [ML-Tech2](https://github.com/ML-Tech2) (0 public repos). Репо `MLTech*` на GH — курсы NTU, не команда | **слабый сигнал**; №10-репо не найдено |
| 5 | Цифровые двойники | новости МГСУ ≠ ЛЦТ №10 | гипотеза |
| 6 | НАДЗОРИУМ | не найдено | постер-verified |
| 7 | SOM | слишком общее | не атрибутировано |
| 8 | Серьезный подход | Победитель ЛЦТ **2024** (задача Банка России, деперсонализация данных) — verified по открытым итогам; публичного репо под задачу **№10 2026** не найдено | постер-verified 2026; ЛЦТ-2024 winner **verified**; репо №10 — нет |
| 9 | project Casablanca | casablanca-project = Hapi | ложное совпадение |
| 10 | МГСУ - Строим будущее | вуз verified; состав №10 нет | постер-verified имя |

**По именам с постера публичных репо почти нет.** Ниже — peers по **постановке ТЗ**;
не утверждать тождество с строками постера без доказательства.

## 2. Прямые GH-peers задачи №10

Детали и таблица §7 — в [TOP10-GH-REPOS.md](TOP10-GH-REPOS.md).

| Репо | Команда (self) | Стек | Матрица (claim) | OCR vs CA≥0,95 | РиН | Риск жюри |
|---|---|---|---|---|---|---|
| [tbikbov/a13-inspector-lct2026](https://github.com/tbikbov/a13-inspector-lct2026) | A13 | Fastify, Python workers, Tess, LLM off | 132; NOT_COMPARABLE честно | **FAIL** (пишут); stamp CA не взят | mock | Честность плюс; пороги §14 не закрыты |
| [midudar/ctrl_z_hackathon](https://github.com/midudar/ctrl_z_hackathon) | ctrl_z | Node/React/ml-service | ~19 extract; skeleton 132 | claim **0,950** SILVER 600 стр.* | ? | Без Releases-кэша сканы ИД пустые |
| [Evgen74/inspector-ai-public](https://github.com/Evgen74/inspector-ai-public) | — | Nest+ONNX | ~75 content | ONNX; наш SILVER не гоняли | mock | Скрытый тест остановлен; XML❌; runs∉git |
| [Namelomax/AIDocumentAnalize](https://github.com/Namelomax/AIDocumentAnalize) | — | Docker+optional vLLM | ~99/132 | **1−CER 0,225** | mock | OCR-гейт; demo passwords |
| [NikolaySalyakhutdinov/gos-stoidoc](https://github.com/NikolaySalyakhutdinov/gos-stoidoc) | — | Express+MiniLM | seed 132 | tesseract | очередь | Cloud Run в README |
| [Tanoklllmonbku/Hakaton-LDT](https://github.com/Tanoklllmonbku/Hakaton-LDT) + [Kaiman30/Hakaton-LDT-backend](https://github.com/Kaiman30/Hakaton-LDT-backend) | — | Go microservices skeleton | arch README | — | — | Ранняя стадия; не полный компаратор |
| [Crooak/chakaton](https://github.com/Crooak/chakaton) | — | Vite mocks | UI 132 | нет | нет | UI-only |

\*Не скрытый тест организатора.

### Vs Контур (честно)

| Тема | Контур | Сильнейшие peers |
|---|---|---|
| Архитектура вердикта | ADR-0001 | A13 / ctrl_z совпадают по духу |
| Executable | 55 | inspector ~75 / AIDocument ~99 (другие метрики!) |
| Public gold | 0/6 | ctrl_z / inspector claim на train — другой протокол |
| OCR | Wilson 0,663 | A13 FAIL; AIDocument провал; ctrl_z claim 0,95 на SILVER |
| Offline pack | compose.offline | A13 organizer tar; AIDocument images.tar |
| XML протокола | в контракте | inspector: нет — удержать преимущество |
| Документация жюри | submission/ | A13 JURY-GUIDE — ориентир формы |

## 3. Российский нормоконтроль (путают с №10)

| Продукт | Vs ТЗ №10 | Статус |
|---|---|---|
| Цифровой нормоконтроль (ДГП) | ГОСТ Р 21.101, не стадии ПД↔РД↔ИД | mos.ru verified |
| TimDoc / RomanAI / Коллегиум | нормы / CDE | сайты verified; цифры accuracy — claim |
| AI Engineering Control / Axis / Чекарь | смежно | частично / search-only |

## 4. Международные BIM/CDE

Forma, Solibri, BIMcollab, PlanRadar, Helonic — координация/IFC/поле;
не матрица 132. Паттерны IDS/BCF — в TOP10.

## 5. Murder Board (сжато)

**Для спикера (Precision / HITL / покрытие).** Жюри услышит «у них 99 параметров, у вас 55». Ответ односложный не годится: **99 и 55 — разные метрики**. У peers «99/132» часто значит «строка в ответе / декларативный YAML / текстовой якорь», а не закрытый порог §14 на скрытом тесте. Контур считает **55 executable** экстракторов, которые реально сравнивают стадии; остальное — `extractor_missing` и честный отказ, а не ложное нарушение. Precision и Recall ТЗ меряются по **evidence_group** после HITL: автомат пишет только `CANDIDATE`, `CONFIRMED_VIOLATION` ставит инспектор (ADR-0001). Гонка за чужим «F1 0,89 на train» без общего gold и без порога CA≥0,95 — ложный KPI; на питче держим свои n, Wilson и открытые гейты I/J/K/L.

| Роль | Вывод |
|---|---|
| Юрист | Слайд ADR-0006: мы ≠ нормоконтроль / ≠ экспертиза СП |
| Банкир | Пилот XML ИД Мосгосстройнадзора — стык |
| ИБ | Офлайн; не светить demo passwords; не vendor AGPL/SSPL |
| Пользователь | ≤3 клика / ≤30 мин (ТЗ §9.3) — гейт K |
| Триаж | Peers много; гонка за чужим F1 без общего gold — low ROI; OCR-гейт общий |
| Red Team | Не приписывать GH-peers к строкам постера; вопрос «а СНиП?» — ловушка |

## 6. Перенять / отвергнуть

**Перенять:** честные FAIL §14 (A13); JURY-маршрут; Releases-кэш с явной деградацией;
drawing_dimension filter; offline+AV; XML; confidence/CI gate.

**Отвергнуть:** IFC в демо; cloud VLM; копирование кода peers; тождество peer↔постер
без доказательств.

## 7. Неподтверждённое

1. OCR текста карточек t.me/967 = полный список имён постера.
2. Соответствие GH-peers командам 1–10 постера.
3. Воспроизводимость чужих F1/OCR на скрытом тесте.
4. Питч **23.10** vs только Фест **30.10** — в посте 967 явно Фест; 23.10 из других анонсов.

## 8. Метод

Постер; t.me/s/leaders_hack/967; пакет ТЗ (локальные вложения); GitHub API+clone+README;
WebSearch/WebFetch. Код продукта не менялся. JURY-onepager — вне этого каталога.
