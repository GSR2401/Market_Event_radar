import json
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional


class Cache:
    def __init__(self, cache_dir: str = "cache"):
        self.dir = Path(cache_dir)
        self.dir.mkdir(exist_ok=True)

    def _path(self, key: str) -> Path:
        safe = key.replace("/", "_").replace(":", "_")
        return self.dir / f"{safe}.json"

    def get(self, key: str, max_age_days: int = 1) -> Optional[Any]:
        p = self._path(key)
        if not p.exists():
            return None
        try:
            payload = json.loads(p.read_text())
            written = date.fromisoformat(payload["date"])
            if (date.today() - written).days > max_age_days:
                return None
            return payload["data"]
        except Exception:
            return None

    def set(self, key: str, data: Any) -> None:
        payload = {"date": date.today().isoformat(), "data": data}
        try:
            self._path(key).write_text(json.dumps(payload, default=str))
        except Exception:
            pass

    def get_weekly(self, key: str) -> Optional[Any]:
        return self.get(key, max_age_days=7)

    def set_weekly(self, key: str, data: Any) -> None:
        self.set(key, data)
