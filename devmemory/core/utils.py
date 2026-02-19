import functools
import subprocess
import os
import shutil
import re
import hashlib
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

@functools.lru_cache(maxsize=1)
def get_repo_id() -> str:
    """Generate a unique identifier for the current repository."""
    repo_root = get_repo_root()
    if not repo_root:
        return "non-git"
    
    # Try remote origin URL first
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
            cwd=repo_root
        )
        remote_url = result.stdout.strip()
        if remote_url:
            # Clean up URL to be a safe ID
            clean_id = re.sub(r'[^a-zA-Z0-9]', '-', remote_url)
            return clean_id.strip("-")
    except Exception:
        pass
    
    # Fallback: basename + hash of path
    basename = os.path.basename(repo_root)
    path_hash = hashlib.sha256(repo_root.encode()).hexdigest()[:8]
    return f"{basename}-{path_hash}"

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
