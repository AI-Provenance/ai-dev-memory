from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from devmemory.core.utils import run_command


@dataclass
class FileAttribution:
    filepath: str
    prompt_lines: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class PromptData:
    prompt_id: str
    tool: str = ""
    model: str = ""
    human_author: str = ""
    messages: list[dict] = field(default_factory=list)
    total_additions: int = 0
    total_deletions: int = 0
    accepted_lines: int = 0
    overridden_lines: int = 0


@dataclass
class CommitStats:
    human_additions: int = 0
    ai_additions: int = 0
    ai_accepted: int = 0
    mixed_additions: int = 0
    total_ai_additions: int = 0
    total_ai_deletions: int = 0
    time_waiting_for_ai: float = 0.0
    git_diff_added_lines: int = 0
    git_diff_deleted_lines: int = 0
    tool_model_breakdown: dict = field(default_factory=dict)


@dataclass
class CommitNote:
    sha: str
    author_name: str
    author_email: str
    subject: str
    date: str
    files: list[FileAttribution] = field(default_factory=list)
    has_ai_note: bool = False
    raw_note: str = ""
    prompts: dict[str, PromptData] = field(default_factory=dict)
    stats: CommitStats | None = None
    body: str = ""


def _looks_like_filepath(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) < 2:
        return False
    if stripped in ("{", "}", "---", "...", "***"):
        return False
    if stripped.startswith("{") or stripped.startswith("["):
        return False
    if all(c in "-=_~*#<>{}[]()@!$%^&+|\\\"'" for c in stripped):
        return False
    if "/" in stripped or "." in stripped:
        return True
    if re.match(r"^[a-zA-Z0-9_]", stripped) and not stripped.startswith(" "):
        return True
    return False


def get_head_sha() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def get_commit_diff(sha: str) -> str:
    try:
        result = subprocess.run(
            ["git", "diff", f"{sha}~1..{sha}", "--stat"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return ""


def get_commit_diff_full(sha: str) -> str:
    return run_command(["git", "diff", f"{sha}~1..{sha}", "--no-color"]) or ""


def get_per_file_diffs(sha: str) -> dict[str, str]:
    full_diff = get_commit_diff_full(sha)
    if not full_diff:
        return {}

    file_diffs: dict[str, str] = {}
    current_file = ""
    current_lines: list[str] = []

    for line in full_diff.splitlines():
        if line.startswith("diff --git"):
            if current_file and current_lines:
                file_diffs[current_file] = "\n".join(current_lines)
            match = re.search(r" b/(.+)$", line)
            current_file = match.group(1) if match else ""
            current_lines = []
        elif current_file:
            current_lines.append(line)

    if current_file and current_lines:
        file_diffs[current_file] = "\n".join(current_lines)

    return file_diffs


def get_commit_body(sha: str) -> str:
    return run_command(["git", "log", "-1", "--format=%b", sha]) or ""


def parse_ai_note(raw_note: str) -> list[FileAttribution]:
    files: list[FileAttribution] = []
    current_file: FileAttribution | None = None

    for line in raw_note.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        if not line.startswith(" ") and not line.startswith("\t"):
            if _looks_like_filepath(stripped):
                current_file = FileAttribution(filepath=stripped)
                files.append(current_file)
            else:
                current_file = None
        elif current_file is not None:
            parts = stripped.split(None, 1)
            if len(parts) == 2:
                prompt_id, line_ranges = parts
                if re.match(r"^[a-f0-9]+$", prompt_id):
                    current_file.prompt_lines[prompt_id] = line_ranges.split(",")
            elif len(parts) == 1 and re.match(r"^[a-f0-9]+$", parts[0]):
                current_file.prompt_lines[parts[0]] = []

    return files


def get_prompt_data(prompt_id: str, commit_sha: str | None = None) -> PromptData | None:
    cmd = _git_ai_prefix() + ["show-prompt", prompt_id]
    if commit_sha:
        cmd.extend(["--commit", commit_sha])

    output = run_command(cmd)
    if not output:
        return None

    try:
        data = json.loads(output)
    except (json.JSONDecodeError, ValueError):
        return None

    prompt = data.get("prompt", {})
    agent_id = prompt.get("agent_id", {})

    messages = prompt.get("messages", [])
    if isinstance(messages, str):
        messages = [{"role": "user", "content": messages}]

    return PromptData(
        prompt_id=prompt_id,
        tool=agent_id.get("tool", ""),
        model=agent_id.get("model", ""),
        human_author=prompt.get("human_author", ""),
        messages=messages,
        total_additions=prompt.get("total_additions", 0),
        total_deletions=prompt.get("total_deletions", 0),
        accepted_lines=prompt.get("accepted_lines", 0),
        overridden_lines=prompt.get("overriden_lines", 0),
    )


def get_commit_stats(sha: str) -> CommitStats | None:
    cmd = _git_ai_prefix() + ["stats", sha, "--json"]
    output = run_command(cmd)
    if not output:
        return None

    try:
        data = json.loads(output)
    except (json.JSONDecodeError, ValueError):
        return None

    return CommitStats(
        human_additions=data.get("human_additions", 0),
        ai_additions=data.get("ai_additions", 0),
        ai_accepted=data.get("ai_accepted", 0),
        mixed_additions=data.get("mixed_additions", 0),
        total_ai_additions=data.get("total_ai_additions", 0),
        total_ai_deletions=data.get("total_ai_deletions", 0),
        time_waiting_for_ai=data.get("time_waiting_for_ai", 0.0),
        git_diff_added_lines=data.get("git_diff_added_lines", 0),
        git_diff_deleted_lines=data.get("git_diff_deleted_lines", 0),
        tool_model_breakdown=data.get("tool_model_breakdown", {}),
    )


def _collect_prompt_ids(files: list[FileAttribution]) -> set[str]:
    ids: set[str] = set()
    for f in files:
        ids.update(f.prompt_lines.keys())
    return ids


def get_ai_note_for_commit(sha: str) -> str:
    return run_command(["git", "notes", "--ref=ai", "show", sha]) or ""


def _parse_ai_note_metadata(raw_note: str) -> dict | None:
    if not raw_note or "---" not in raw_note:
        return None
    raw_note = raw_note.replace("\r\n", "\n")
    parts = re.split(r"\n\s*---\s*\n", raw_note, maxsplit=1)
    if len(parts) != 2:
        parts = raw_note.split("\n---\n", 1)
    if len(parts) != 2:
        return None
    json_str = parts[1].strip()
    if not json_str:
        return None
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, ValueError):
        return None


def _messages_from_note_prompt_record(record: dict) -> list[dict]:
    out: list[dict] = []
    for m in record.get("messages") or []:
        kind = m.get("type", "user")
        if kind not in ("user", "assistant"):
            continue
        text = m.get("text", "") or m.get("content", "")
        if isinstance(text, list):
            text = " ".join(t.get("text", "") if isinstance(t, dict) else str(t) for t in text)
        out.append({"role": kind, "content": text})
    return out


def _prompts_from_note_metadata(raw_note: str) -> dict[str, dict]:
    meta = _parse_ai_note_metadata(raw_note)
    if not meta:
        return {}
    prompts = meta.get("prompts") or {}
    return {str(k): v for k, v in prompts.items() if isinstance(v, dict) and re.match(r"^[a-f0-9]+$", str(k))}


def _note_prompt_record_for_id(note_prompts: dict[str, dict], pid: str) -> dict | None:
    if pid in note_prompts:
        return note_prompts[pid]
    for key, rec in note_prompts.items():
        if key.startswith(pid) or pid.startswith(key):
            return rec
    return None


def get_commits_since(since_sha: str | None, limit: int = 50, all_branches: bool = False) -> list[dict]:
    fmt = "%H|%an|%ae|%s|%aI"
    cmd = ["git", "log", f"--format={fmt}", f"-{limit}"]
    if all_branches:
        cmd.append("--all")

    if since_sha:
        cmd.append(f"{since_sha}..HEAD")

    output = run_command(cmd)
    if not output:
        return []

    commits = []
    for line in output.strip().splitlines():
        if not line.strip():
            continue
        parts = line.split("|", 4)
        if len(parts) < 5:
            continue
        commits.append(
            {
                "sha": parts[0],
                "author_name": parts[1],
                "author_email": parts[2],
                "subject": parts[3],
                "date": parts[4],
            }
        )
    return commits


def _build_commit_note(c: dict, enrich: bool = True) -> CommitNote:
    raw_note = get_ai_note_for_commit(c["sha"])
    has_ai = bool(raw_note)
    files = parse_ai_note(raw_note) if has_ai else []

    prompts: dict[str, PromptData] = {}
    stats: CommitStats | None = None
    body = ""

    if has_ai and enrich:
        prompt_ids = _collect_prompt_ids(files)
        note_prompts = _prompts_from_note_metadata(raw_note)
        for pid in prompt_ids:
            pd = get_prompt_data(pid, commit_sha=c["sha"])
            if pd is None and c["sha"]:
                pd = get_prompt_data(pid, commit_sha=None)
            if pd:
                rec = _note_prompt_record_for_id(note_prompts, pid)
                if not pd.messages and rec:
                    msgs = _messages_from_note_prompt_record(rec)
                    if msgs:
                        agent = rec.get("agent_id") or {}
                        pd = PromptData(
                            prompt_id=pid,
                            tool=agent.get("tool", pd.tool),
                            model=agent.get("model", pd.model),
                            human_author=rec.get("human_author", pd.human_author),
                            messages=msgs,
                            total_additions=rec.get("total_additions", pd.total_additions),
                            total_deletions=rec.get("total_deletions", pd.total_deletions),
                            accepted_lines=rec.get("accepted_lines", pd.accepted_lines),
                            overridden_lines=rec.get("overriden_lines", pd.overridden_lines),
                        )
                prompts[pid] = pd
            else:
                rec = _note_prompt_record_for_id(note_prompts, pid)
            if not pd and rec:
                agent = rec.get("agent_id") or {}
                msgs = _messages_from_note_prompt_record(rec)
                pd = PromptData(
                    prompt_id=pid,
                    tool=agent.get("tool", ""),
                    model=agent.get("model", ""),
                    human_author=rec.get("human_author", ""),
                    messages=msgs,
                    total_additions=rec.get("total_additions", 0),
                    total_deletions=rec.get("total_deletions", 0),
                    accepted_lines=rec.get("accepted_lines", 0),
                    overridden_lines=rec.get("overriden_lines", 0),
                )
                prompts[pid] = pd

        stats = get_commit_stats(c["sha"])
        body = get_commit_body(c["sha"])

    return CommitNote(
        sha=c["sha"],
        author_name=c["author_name"],
        author_email=c["author_email"],
        subject=c["subject"],
        date=c["date"],
        files=files,
        has_ai_note=has_ai,
        raw_note=raw_note,
        prompts=prompts,
        stats=stats,
        body=body,
    )


def get_ai_notes_since(since_sha: str | None, limit: int = 50, all_branches: bool = False) -> list[CommitNote]:
    commits = get_commits_since(since_sha, limit, all_branches=all_branches)
    return [_build_commit_note(c) for c in commits]


def get_latest_commit_note() -> CommitNote | None:
    commits = get_commits_since(None, limit=1)
    if not commits:
        return None
    return _build_commit_note(commits[0])


def _resolve_git_ai() -> list[str] | None:
    """Find a working git-ai command: PATH, well-known install dir, or git subcommand."""
    candidates = [
        ["git-ai", "version"],
        [os.path.expanduser("~/.git-ai/bin/git-ai"), "version"],
        ["git", "ai", "version"],
    ]
    for cmd in candidates:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                return cmd[:-1]  # return without the "version" arg
        except FileNotFoundError:
            continue
    return None


# Cache the result so we don't probe on every call
_git_ai_cmd_prefix: list[str] | None = None
_git_ai_resolved = False


def _git_ai_prefix() -> list[str]:
    """Return the command prefix for git-ai (cached after first lookup)."""
    global _git_ai_cmd_prefix, _git_ai_resolved
    if not _git_ai_resolved:
        _git_ai_cmd_prefix = _resolve_git_ai()
        _git_ai_resolved = True
    return _git_ai_cmd_prefix or ["git-ai"]


def is_git_ai_installed() -> bool:
    return _resolve_git_ai() is not None


def get_git_ai_version() -> str:
    prefix = _resolve_git_ai()
    if not prefix:
        return "not installed"
    try:
        result = subprocess.run(prefix + ["version"], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
    except FileNotFoundError:
        pass
    return "not installed"


def enable_prompt_storage_notes() -> bool:
    try:
        cmd = _git_ai_prefix() + ["config", "set", "prompt_storage", "notes"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode == 0
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def install_git_ai_hooks() -> bool:
    try:
        cmd = _git_ai_prefix() + ["install-hooks"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode == 0
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
