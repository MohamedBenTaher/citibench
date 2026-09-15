"""Process-wide sliding window for public generate."""

from __future__ import annotations

import time
from threading import Lock


class SlidingWindow:
    def __init__(self) -> None:
        self._lock = Lock()
        self._hits: list[float] = []

    def allow(self, limit: int, window_s: float = 60.0) -> bool:
        if limit <= 0:
            return True
        now = time.monotonic()
        with self._lock:
            self._hits = [stamp for stamp in self._hits if now - stamp < window_s]
            if len(self._hits) >= limit:
                return False
            self._hits.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


generate_window = SlidingWindow()
