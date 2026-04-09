from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class ContentHashCache:
    def __init__(self, cache_dir: str = "data/cache") -> None:
        self.root = Path(cache_dir)
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def digest(payload: str) -> str:
        return hashlib.sha256(payload.encode("utf-8", errors="ignore")).hexdigest()

    def _path(self, namespace: str, key: str) -> Path:
        ns = self.root / namespace
        ns.mkdir(parents=True, exist_ok=True)
        return ns / f"{key}.json"

    def get(self, namespace: str, key: str) -> Any | None:
        path = self._path(namespace, key)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def set(self, namespace: str, key: str, value: Any) -> None:
        path = self._path(namespace, key)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
