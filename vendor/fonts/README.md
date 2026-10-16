# Шрифт для синтетических PDF

`NotoSans-Regular.ttf` — Noto Sans Regular (латиница, греческий, кириллица),
SIL Open Font License 1.1, текст лицензии в `OFL.txt`.

Источник файла:
`https://raw.githubusercontent.com/notofonts/notofonts.github.io/main/fonts/NotoSans/hinted/ttf/NotoSans-Regular.ttf`
(скачан 16.10.2026). Текст лицензии:
`https://raw.githubusercontent.com/notofonts/latin-greek-cyrillic/main/OFL.txt`.
SHA-256 обоих файлов — в `SHA256SUMS`; тест `backend/tests/test_vendored_font.py` их сверяет.

Зачем: учебный комплект демо и тестовые листы встраивают шрифт в PDF. Системный
шрифт на разных машинах разный (или его нет): тогда `/demo/kit` отвечает 503, а байты
и хеши PDF расходятся. Теперь первым берётся этот файл; `KONTUR_TEST_FONT`
по-прежнему имеет приоритет.

Шрифт не изменялся. Имя «Noto» — зарезервированное имя шрифта по OFL; файл
распространяется как есть.
