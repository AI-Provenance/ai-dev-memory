import functools
import subprocess
import os
import shutil
from typing import Optional

@functools.lru_cache(maxsize=1)
def get_git_ai_path() -> Optional[str]:
    """Find the path to the git-ai executable."""
    return shutil.which("git-ai")

@functools.lru_cache(maxsize=1)
def get_repo_root() -> Optional[str]:
    """Get the root directory of the current git repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except Exception:
        return None

def run_command(cmd: list[str], cwd: Optional[str] = None) -> Optional[str]:
    """Run a shell command and return its output."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            cwd=cwd
        )
        return result.stdout.strip()
    except Exception:
        return None
