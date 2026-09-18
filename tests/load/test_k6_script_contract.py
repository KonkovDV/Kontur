"""CI-безопасная проверка k6-скрипта (pytest, без k6).

k6 в CI не запускается: нет сервера и нет k6-бинарника.
Но мы можем проверить, что скрипт содержит то, что от него ждут.
Выученный урок: скрипт без thresholds — p95 не контролируется; CI не падает.
"""
from __future__ import annotations

import pathlib
import re

K6_SCRIPT = pathlib.Path(__file__).parent / 'k6_status.js'


def _src() -> str:
    return K6_SCRIPT.read_text(encoding='utf-8')


def test_k6_script_exists() -> None:
    assert K6_SCRIPT.exists(), f'k6 скрипт не найден: {K6_SCRIPT}'


def test_k6_vus_100() -> None:
    src = _src()
    # Порог ТЗ: 100 VU
    assert re.search(r'vus\s*:\s*100', src), 'Скрипт должен задавать vus: 100'


def test_k6_duration_60s() -> None:
    src = _src()
    assert re.search(r"duration\s*:\s*['"]60s['"]", src), 'Скрипт должен задавать duration: 60s'


def test_k6_has_p95_threshold() -> None:
    src = _src()
    # thresholds содержат p(95)<200
    assert 'p(95)<200' in src, 'Отсутствует порог p(95)<200 — p95 не будет контролироваться'


def test_k6_threshold_uses_name_tag() -> None:
    src = _src()
    # Порог привязан к тегу name:status, а не ко всем запросам
    assert 'http_req_duration{name:status}' in src, 'Тег name:status отсутствует'


def test_k6_error_rate_threshold() -> None:
    src = _src()
    assert 'http_req_failed' in src and 'rate<0.01' in src, \
        'Отсутствует порог на долю ошибок'


def test_k6_status_endpoint() -> None:
    src = _src()
    assert '/status' in src, 'Скрипт должен ходить на /status'
