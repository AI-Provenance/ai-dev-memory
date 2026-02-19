from __future__ import annotations

import json
from pathlib import Path
from dataclasses import dataclass, field, asdict
from devmemory.core.utils import get_repo_root, get_repo_id


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
        config = cls()
        
        # 1. Load global
        if CONFIG_FILE.exists():
            try:
                raw = json.loads(CONFIG_FILE.read_text())
                for k, v in raw.items():
                    if k in cls.__dataclass_fields__:
                        setattr(config, k, v)
            except Exception:
                pass
                
        # 2. Load local
        repo_root = get_repo_root()
        if repo_root:
            local_file = Path(repo_root) / ".devmemory" / "config.json"
            if local_file.exists():
                try:
                    raw = json.loads(local_file.read_text())
                    for k, v in raw.items():
                        if k in cls.__dataclass_fields__:
                            setattr(config, k, v)
                except Exception:
                    pass
                    
        return config

    def save(self, local: bool = False) -> None:
        if local:
            repo_root = get_repo_root()
            if not repo_root:
                raise RuntimeError("Not in a git repository, cannot save local config.")
            target_dir = Path(repo_root) / ".devmemory"
            target_file = target_dir / "config.json"
        else:
            target_dir = CONFIG_DIR
            target_file = CONFIG_FILE

        target_dir.mkdir(parents=True, exist_ok=True)
        target_file.write_text(json.dumps(asdict(self), indent=2) + "\n")

    def set_value(self, key: str, value: str, local: bool = False) -> None:
        if key not in self.__dataclass_fields__:
            raise KeyError(f"Unknown config key: {key}. Valid keys: {list(self.__dataclass_fields__)}")
        setattr(self, key, value)
        self.save(local=local)

    def get_active_namespace(self) -> str:
        """Resolve the effective namespace for the current repository context."""
        repo_id = get_repo_id()
        if repo_id == "non-git":
            return self.namespace
        return f"{self.namespace}:{repo_id}"
