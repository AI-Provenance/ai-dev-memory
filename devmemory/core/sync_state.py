from __future__ import annotations

import json
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime, timezone


STATE_DIR = Path.home() / ".devmemory"


def _state_file_for_repo(repo_root: str) -> Path:
    safe_name = repo_root.replace("/", "_").replace("\\", "_").strip("_")
    return STATE_DIR / f"state_{safe_name}.json"


@dataclass
class SyncState:
    repo_root: str
    last_synced_sha: str = ""
    last_synced_at: str = ""
    total_synced: int = 0

    @classmethod
    def load(cls, repo_root: str) -> SyncState:
        path = _state_file_for_repo(repo_root)
        if path.exists():
            raw = json.loads(path.read_text())
            return cls(**raw)
        return cls(repo_root=repo_root)

    def save(self) -> None:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        path = _state_file_for_repo(self.repo_root)
        path.write_text(json.dumps(asdict(self), indent=2) + "\n")

    def mark_synced(self, sha: str, count: int = 1) -> None:
        self.last_synced_sha = sha
        self.last_synced_at = datetime.now(timezone.utc).isoformat()
        self.total_synced += count
        self.save()
