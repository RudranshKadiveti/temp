from __future__ import annotations

import random
import time
from collections import deque


class AdaptiveRateController:
    def __init__(self, min_delay: float = 0.2, max_delay: float = 3.0) -> None:
        self.min_delay = min_delay
        self.max_delay = max_delay
        self._delay = min_delay
        self._history = deque(maxlen=20)

    @property
    def delay(self) -> float:
        return self._delay

    def record(self, response_time: float, bot_signal: bool) -> None:
        self._history.append((response_time, bot_signal, time.time()))

        average_rt = sum(r for r, _, _ in self._history) / max(len(self._history), 1)
        bot_hits = sum(1 for _, b, _ in self._history if b)

        if bot_hits >= 3:
            self._delay = min(self.max_delay, self._delay * 1.35 + 0.15)
            return

        if average_rt > 2.5:
            self._delay = min(self.max_delay, self._delay * 1.15 + 0.05)
        else:
            self._delay = max(self.min_delay, self._delay * 0.92)

    def jitter(self) -> float:
        return self._delay + random.uniform(0.0, 0.35)
