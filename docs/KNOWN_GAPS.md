# Известные пробелы

Честный реестр того, чего нет. В путь stop-ship: здесь нет, нет frozen val, нет GOLD OCR, нет scorecard ТЗ.

| ИД | Суть пробела | Куда нет | Курьер нет |
|---|---|---|---|
| GAP-CAP-OCR | Потолок OCR на рукописных подписях | Нет bake-off победителя на ≥16 gold строк с Wilson 95 % CI | gate I |
| GAP-OCR-ROT | Ротация страниц: распознавание падает на перевёрнутых сканах | crop3x-oem1 ветка не влита; auto-deskew не добавлен | gate I |
| GAP-STAMP | Печать с инспектором: SELECT_REVISION есть в API, но stamp evidence не закрывает gate J | inspector-etalon не порождает stamp finding; POST .../select не меняет вывод | конкурсный срез |
| GAP-IOS4-VAL | Нет frozen validation corpus для 132 правил | Нужно ≥16 gold объектов с ответами v2.0; пакет организатора без ответов | gate I/J |
| RT-2609-21 | RT-C / RT-B покрыты тестами, но живых PDF-сессий нет | Нет recorder сессий с files/ от инспектора | gate K |
| GAP-FREE-SEARCH | Свободный поиск по тексту чертежей не реализован | Нет полнотекстового индекса; только структурированные правила | roadmap |
| GAP-DWG | DWG/DXF не читается напрямую | Нет DWG-парсера; только PDF-экспорт | roadmap |
| GAP-SPLIT | Разбивка комбинированного файла ПД+РД не реализована | RD_ID_MIXED загружается только как RD | roadmap |
| GAP-EMB | PDF с вложенными файлами (/EmbeddedFile) | Пайплайн не читает вложения: `PdfDocumentTokens` разбирает только текстовый/растровый слой, вложения игнорируются | тест не писать |
| GAP-ETALON-UI | Инспекторский SELECT_REVISION есть в API, в UI кнопки назначения эталона нет | Двухпанельный viewer (#76) не закрывает J; POST `.../revisions/{file_id}/select` | конкурсный срез |
| GAP-INJ-SCAN | `scan_tokens_for_injection()` объявлен в `infrastructure/injection_scan.py`, но не вызывается из `_pages_from_blobs()` после `tokens = flatten_tokens(document)`; import отсутствует | Облачный агент не берётся: нужна локальная реализация + живые PDF-сессии | #84 |
