# Уведомления о сторонних компонентах

Код Контура — Apache-2.0, см. `LICENSE`. Ниже лицензии зависимостей, которые реально указаны в `backend/pyproject.toml`, `web/package.json` и `gateway/package.json`. Версии Python сняты с метаданных установленных пакетов 23.09.2026 (`License` / `License-Expression`). Лицензии npm сняты командой `npm view <имя> license` в тот же день.

## Python

| Пакет | Версия на момент сверки | Лицензия |
| --- | --- | --- |
| fastapi | 0.141.1 | MIT |
| uvicorn | 0.53.0 | BSD-3-Clause |
| pydantic | 2.13.5 | MIT |
| pypdfium2 | 5.13.0 | BSD-3-Clause и Apache-2.0 (так написано в метаданных; внутри — лицензии зависимостей, включая PDFium) |
| pdfminer.six | 20260107 | MIT |
| jsonschema | 4.26.0 | MIT |
| PyYAML | 6.0.3 | MIT |
| python-multipart | 0.0.32 | Apache-2.0 |
| PyJWT | 2.14.0 | MIT |
| pytesseract | 0.3.13 | Apache-2.0 |
| Pillow | 12.3.0 | MIT-CMU |
| pytest | 9.1.1 | MIT |
| ruff | 0.16.3 | MIT |

`rapidocr-onnxruntime` объявлен в extra `ocr` и в этой среде не установлен. В ядро он не входит, пока отдельно не выбран.

## Образ ядра

`backend/Dockerfile` ставит пакеты Debian `tesseract-ocr`, `tesseract-ocr-rus`, `tesseract-ocr-eng`. Движок Tesseract OCR (upstream) — Apache-2.0. Условия языковых данных — у этих пакетов Debian, отдельно в репозиторий они не копируются.

## npm

| Пакет | Лицензия |
| --- | --- |
| react, react-dom | MIT |
| pdfjs-dist | Apache-2.0 |
| vite | MIT |
| express | MIT |
| http-proxy-middleware | MIT |
| pino | MIT |

## Образы compose

PostgreSQL, Redis, RabbitMQ и MinIO в `docker-compose.yml` — чужие образы. Их тексты лицензий в этот репозиторий не копируются.
