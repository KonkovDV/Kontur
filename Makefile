# Makefile — быстрые команды для разработки и демо.
# Требует: docker compose v2, python >=3.11, GNU make.

.PHONY: help up down restart logs \
        offline-pull offline-up \
        test test-fast check lint types \
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
