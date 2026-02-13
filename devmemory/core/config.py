from __future__ import annotations

import json
from pathlib import Path
from dataclasses import dataclass, field, asdict


CONFIG_DIR = Path.home() / ".devmemory"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULTS = {
    "ams_endpoint": "http://localhost:8000",
    "mcp_endpoint": "http://localhost:9050",
    "namespace": "default",
    "user_id": "",
}


@dataclass
class DevMemoryConfig:
    ams_endpoint: str = DEFAULTS["ams_endpoint"]
    mcp_endpoint: str = DEFAULTS["mcp_endpoint"]
    namespace: str = DEFAULTS["namespace"]
    user_id: str = DEFAULTS["user_id"]

    @classmethod
    def load(cls) -> DevMemoryConfig:
        if CONFIG_FILE.exists():
            raw = json.loads(CONFIG_FILE.read_text())
            merged = {**DEFAULTS, **raw}
            return cls(**{k: v for k, v in merged.items() if k in cls.__dataclass_fields__})
        return cls()

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(asdict(self), indent=2) + "\n")

    def set_value(self, key: str, value: str) -> None:
        if key not in self.__dataclass_fields__:
            raise KeyError(f"Unknown config key: {key}. Valid keys: {list(self.__dataclass_fields__)}")
        setattr(self, key, value)
        self.save()
