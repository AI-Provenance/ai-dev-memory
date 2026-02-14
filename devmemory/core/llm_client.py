from __future__ import annotations

import os
import httpx
from pathlib import Path


def _find_env_file() -> Path | None:
    cwd = Path.cwd()
    for d in [cwd, *cwd.parents]:
        env_path = d / ".env"
        if env_path.exists():
            if (d / ".git").exists() or (d / "docker-compose.yml").exists():
                return env_path
        if d == d.parent:
            break
    env_path = cwd / ".env"
    if env_path.exists():
        return env_path
    return None


def _parse_env_file(path: Path) -> dict[str, str]:
    env_vars: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")
            env_vars[key] = value
    return env_vars


def _get_env_var(key: str) -> str:
    value = os.environ.get(key, "")
    if value:
        return value
    env_file = _find_env_file()
    if env_file:
        env_vars = _parse_env_file(env_file)
        return env_vars.get(key, "")
    return ""


def _get_llm_config() -> tuple[str, str, str]:
    """Return (api_key, model, provider) for the configured LLM.

    Provider is "anthropic" or "openai".
    Checks Anthropic first if the model looks like a Claude model,
    then falls back to OpenAI.
    """
    model = _get_env_var("GENERATION_MODEL") or "gpt-4o-mini"
    anthropic_key = _get_env_var("ANTHROPIC_API_KEY")
    openai_key = _get_env_var("OPENAI_API_KEY")

    if anthropic_key and model.startswith("claude"):
        return anthropic_key, model, "anthropic"
    if openai_key:
        return openai_key, model, "openai"
    if anthropic_key:
        return anthropic_key, model, "anthropic"
    return "", model, "openai"


SYSTEM_PROMPT = """\
You are a knowledgebase assistant for a software development project. \
You answer questions by synthesizing information from the project's memory store, \
which contains commit histories, code changes, AI prompts, and development context.

Given the user's question and retrieved memories from the store, provide a clear, concise answer.

Rules:
- Be concise and direct (2-5 sentences for simple queries, more for complex ones)
- Reference specific commits (SHA), files, or code patterns when relevant
- If the memories are not relevant to the question, clearly state: \
"The available memories don't contain information relevant to this question."
- Don't fabricate information not present in the memories
- Focus on answering the question, not describing the memories themselves
- When memories show a pattern of changes (e.g., multiple fixes to the same file), \
summarize the evolution rather than listing each change"""


class LLMError(Exception):
    pass


def _call_openai(
    api_key: str,
    model: str,
    system_prompt: str,
    user_msg: str,
    max_tokens: int = 1000,
    timeout: float = 60.0,
) -> str:
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                "max_completion_tokens": max_tokens,
            },
        )
        if resp.status_code != 200:
            error_msg = resp.json().get("error", {}).get("message", resp.text[:200])
            raise LLMError(f"OpenAI API error ({resp.status_code}): {error_msg}")
        data = resp.json()
        return data["choices"][0]["message"]["content"]


def _call_anthropic(
    api_key: str,
    model: str,
    system_prompt: str,
    user_msg: str,
    max_tokens: int = 1000,
    timeout: float = 60.0,
) -> str:
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "system": system_prompt,
                "messages": [
                    {"role": "user", "content": user_msg},
                ],
            },
        )
        if resp.status_code != 200:
            error_data = resp.json()
            error_msg = error_data.get("error", {}).get("message", resp.text[:200])
            raise LLMError(f"Anthropic API error ({resp.status_code}): {error_msg}")
        data = resp.json()
        return data["content"][0]["text"]


def call_llm(
    system_prompt: str,
    user_msg: str,
    max_tokens: int = 1000,
    timeout: float = 60.0,
) -> str:
    """Call the configured LLM (OpenAI or Anthropic) and return the response text."""
    api_key, model, provider = _get_llm_config()

    if not api_key:
        raise LLMError("no_api_key")

    if provider == "anthropic":
        return _call_anthropic(api_key, model, system_prompt, user_msg, max_tokens, timeout)
    return _call_openai(api_key, model, system_prompt, user_msg, max_tokens, timeout)


def synthesize_answer(
    query: str,
    memories: list[dict],
    timeout: float = 60.0,
) -> str | None:
    context_parts = []
    for i, mem in enumerate(memories, 1):
        topics_str = ", ".join(mem.get("topics", []))
        header = f"--- Memory {i} (type: {mem['type']}, score: {mem['score']:.3f}"
        if topics_str:
            header += f", topics: {topics_str}"
        header += ") ---"
        context_parts.append(f"{header}\n{mem['text']}")

    context = "\n\n".join(context_parts)
    user_msg = f"Question: {query}\n\nRetrieved memories ({len(memories)} results):\n\n{context}"

    return call_llm(SYSTEM_PROMPT, user_msg, max_tokens=1000, timeout=timeout)
