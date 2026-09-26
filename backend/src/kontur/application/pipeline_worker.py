"""Поток L1–L7 внутри процесса API.

Это не брокер, не compose-сервис и не outbox РиН. Один поток на workspace.
Повторная постановка того же процесса выполняется следом, а не параллельно.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from queue import Queue

RunPipeline = Callable[[str], None]


class PipelineWorker:
    """Сериализует прогоны матрицы и будит читателей, когда прогон закончен."""

    def __init__(self, run: RunPipeline) -> None:
        self._run = run
        self._queue: Queue[tuple[str, int] | None] = Queue()
        self._lock = threading.Lock()
        self._pending: dict[str, threading.Event] = {}
        self._generation: dict[str, int] = {}
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._last_error: str | None = None

    def submit(self, process_id: str) -> None:
        """Поставить прогон. Возврат не означает, что матрица уже посчитана."""

        with self._lock:
            current = self._pending.get(process_id)
            if current is None or current.is_set():
                current = threading.Event()
                self._pending[process_id] = current
            self._generation[process_id] = self._generation.get(process_id, 0) + 1
            generation = self._generation[process_id]
            self._ensure_thread()
        self._queue.put((process_id, generation))

    def wait(self, process_id: str) -> None:
        """Ждать последний поставленный прогон этого процесса."""

        if self._is_worker_thread():
            return
        while True:
            with self._lock:
                event = self._pending.get(process_id)
                generation = self._generation.get(process_id, 0)
            if event is None:
                return
            event.wait()
            with self._lock:
                if self._generation.get(process_id, 0) == generation and event.is_set():
                    return

    def wait_all(self) -> None:
        """Ждать все процессы, которые уже поставлены в этот поток."""

        if self._is_worker_thread():
            return
        while True:
            with self._lock:
                process_ids = list(self._pending)
                generations = dict(self._generation)
                idle = all(event.is_set() for event in self._pending.values())
            if idle:
                return
            for process_id in process_ids:
                self.wait(process_id)
            with self._lock:
                still_idle = all(event.is_set() for event in self._pending.values())
                if still_idle and self._generation == generations:
                    return

    def _is_worker_thread(self) -> bool:
        return self._thread_id is not None and threading.get_ident() == self._thread_id

    def _ensure_thread(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._loop,
            name="kontur-pipeline",
            daemon=True,
        )
        self._thread.start()

    def _loop(self) -> None:
        self._thread_id = threading.get_ident()
        while True:
            item = self._queue.get()
            if item is None:
                return
            process_id, generation = item
            with self._lock:
                if self._generation.get(process_id) != generation:
                    continue
            try:
                self._run(process_id)
            except Exception as exc:
                self._last_error = type(exc).__name__
            finally:
                self._finish(process_id, generation)

    def _finish(self, process_id: str, generation: int) -> None:
        with self._lock:
            if self._generation.get(process_id) != generation:
                return
            event = self._pending.get(process_id)
            if event is not None:
                event.set()
