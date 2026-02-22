from __future__ import annotations

import json
import os
from pathlib import Path
from dataclasses import dataclass, asdict
from devmemory.core.utils import get_repo_root, get_repo_id
from devmemory.core.logging_config import get_logger

log = get_logger(__name__)


CONFIG_DIR = Path.home() / ".devmemory"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULTS = {
    "ams_endpoint": os.environ.get("AMS_ENDPOINT", "http://localhost:8000"),
    "mcp_endpoint": os.environ.get("MCP_ENDPOINT", "http://localhost:9050"),
    "namespace": "default",
    "user_id": "",
    "auto_summarize": False,
}


@dataclass
class DevMemoryConfig:
    ams_endpoint: str = DEFAULTS["ams_endpoint"]
    mcp_endpoint: str = DEFAULTS["mcp_endpoint"]
    namespace: str = DEFAULTS["namespace"]
    user_id: str = DEFAULTS["user_id"]
    auto_summarize: bool = DEFAULTS["auto_summarize"]

    @staticmethod
    def get_auth_token() -> str:
        """Get AMS auth token from environment variable (never from config)."""
        return os.environ.get("AMS_AUTH_TOKEN", "")

    @classmethod
    def load(cls) -> DevMemoryConfig:
        log.debug("load: loading configuration")
        config = cls()

        # 1. Load global
        if CONFIG_FILE.exists():
            try:
                raw = json.loads(CONFIG_FILE.read_text())
                for k, v in raw.items():
                    if k in cls.__dataclass_fields__:
                        setattr(config, k, v)
                log.debug(f"load: loaded global config from {CONFIG_FILE}")
            except Exception as e:
                log.warning(f"load: failed to parse global config - {e}")

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
                    log.debug(f"load: loaded local config from {local_file}")
                except Exception as e:
                    log.warning(f"load: failed to parse local config - {e}")

        # 3. Environment variables override saved config
        if os.environ.get("AMS_ENDPOINT"):
            config.ams_endpoint = os.environ["AMS_ENDPOINT"]
        if os.environ.get("MCP_ENDPOINT"):
            config.mcp_endpoint = os.environ["MCP_ENDPOINT"]

        return config

    def save(self, local: bool = False) -> None:
        if local:
            repo_root = get_repo_root()
            if not repo_root:
                log.error("save: not in a git repository, cannot save local config")
                raise RuntimeError("Not in a git repository, cannot save local config.")
            target_dir = Path(repo_root) / ".devmemory"
            target_file = target_dir / "config.json"
        else:
            target_dir = CONFIG_DIR
            target_file = CONFIG_FILE

        target_dir.mkdir(parents=True, exist_ok=True)
        target_file.write_text(json.dumps(asdict(self), indent=2) + "\n")
        log.debug(f"save: saved config to {target_file}")

    def set_value(self, key: str, value: str | bool, local: bool = False) -> None:
        if key not in self.__dataclass_fields__:
            log.error(f"set_value: unknown config key '{key}'")
            raise KeyError(f"Unknown config key: {key}. Valid keys: {list(self.__dataclass_fields__)}")
        log.debug(f"set_value: {key}={value} (local={local})")
        setattr(self, key, value)
        self.save(local=local)

    def get_active_namespace(self) -> str:
        """Resolve the effective namespace for the current repository context."""
        repo_id = get_repo_id()
        if repo_id == "non-git":
            return self.namespace
        return f"{self.namespace}:{repo_id}"
