# Makefile — быстрые команды для разработки и демо.
# Требует: docker compose v2, python >=3.11, GNU make.

.PHONY: help up down restart logs \
        offline-pull offline-up \
        test test-fast check lint types \
        ocr-pilot \
        train-public \
        agent-dumps \
        demo-rehearsal \
        clean

PYTHON   := python
DC       := docker compose
DC_OFF   := $(DC) -f docker-compose.yml -f docker-compose.offline.yml

help:          ## Показать справку
	@grep -E '^[a-z_-]+:.*##' Makefile | awk -F':.*##' '{printf "  %-20s %s\n", $$1, $$2}'

# ── Docker ──────────────────────────────────────────────────────────────────

up:            ## Запустить все сервисы (нужен интернет при первом запуске)
	$(DC) up -d

down:          ## Остановить все сервисы
	$(DC) down

restart:       ## Перезапустить все сервисы
	$(DC) restart

logs:          ## Хвост логов всех сервисов
	$(DC) logs -f

offline-pull:  ## Загрузить все образы для offline-режима (нужен интернет)
	@echo "==> Pulling images for offline use..."
	$(DC) pull
	@bash scripts/docker-pull.sh

offline-up:    ## Запустить в offline-режиме (без интернета)
	$(DC_OFF) up -d

ocr-pilot:     ## SILVER CA пилота в Docker (Tesseract). Не закрывает гейт I
	mkdir -p out
	$(DC) build core
	$(DC) run --rm --no-deps \
		--user "$$(id -u):$$(id -g)" \
		-v "$(CURDIR)/files:/app/files:ro" \
		-v "$(CURDIR)/out:/app/out" \
		-e KONTUR_ROOT=/app \
		-e KONTUR_OCR_PILOT_OUT=/app/out \
		-e KONTUR_OCR_PILOT_WORKERS=4 \
		core python -m kontur.evaluation.ocr_pilot

train-public:  ## TRAIN_PUBLIC JSONL в Docker. Не закрывает гейт J
	mkdir -p out
	$(DC) build core
	$(DC) run --rm --no-deps \
		-v "$(CURDIR)/files:/app/files:ro" \
		-v "$(CURDIR)/out:/app/out" \
		-v "$(CURDIR)/data/dataset:/app/data/dataset:ro" \
		-e KONTUR_ROOT=/app \
		-e KONTUR_TRAIN_PUBLIC_OUT=/app/out \
		core python -m kontur.evaluation.train_public

agent-dumps:   ## coverage + handoff JSON для следующего ИИ. Не закрывает гейты
	$(PYTHON) scripts/export_agent_dumps.py

demo-rehearsal: ## Репетиция #78 in-process. Не Polar, не гейт K, не видео
	$(PYTHON) -m pytest backend/tests/test_demo_cold_start.py -q --tb=short
	$(PYTHON) scripts/demo_cold_start.py

# ── Тесты и качество ────────────────────────────────────────────────────────

test:          ## Полный тест-сьют (включая slow)
	$(PYTHON) -m pytest backend/tests -q --tb=short

test-fast:     ## Только быстрые тесты (без slow/e2e)
	$(PYTHON) -m pytest backend/tests -q --tb=short -m "not slow"

check:         ## Ruff + mypy (соответствие стандарту отрасли)
	ruff check backend scripts
	mypy --strict backend/src

lint:          ## Только ruff (быстро)
	ruff check backend scripts

types:         ## Только mypy
	mypy --strict backend/src

clean:         ## Удалить артефакты сборки
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.pyc' -delete 2>/dev/null || true
	rm -rf .mypy_cache .ruff_cache .pytest_cache
