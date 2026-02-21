from __future__ import annotations

import os
import httpx
from pathlib import Path
from devmemory.core.logging_config import get_logger

log = get_logger(__name__)


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


def get_llm_config() -> tuple[str, str, str]:
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
- If the user asks about prompts used, what was prompted, or what kind of prompts led to changes: \
include the actual prompt text from the memories (the [user]: ... or "Prompt to ..." content) in your answer. \
Quote the prompt text; do not only summarize commits or files.
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
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
        }

        if model.startswith("gpt-5") or model.startswith("o3") or model.startswith("o4"):
            payload["max_completion_tokens"] = max_tokens
        else:
            payload["max_tokens"] = max_tokens

        resp = client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        if resp.status_code != 200:
            error_msg = resp.json().get("error", {}).get("message", resp.text[:200])
            raise LLMError(f"OpenAI API error ({resp.status_code}): {error_msg}")
        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            raise LLMError("OpenAI API returned no choices in response")
        choice = choices[0]
        finish_reason = choice.get("finish_reason", "unknown")
        message = choice.get("message", {})
        content = message.get("content")

        if content is None:
            raise LLMError(f"OpenAI API returned null content (finish_reason: {finish_reason})")

        if not isinstance(content, str):
            raise LLMError(f"OpenAI API returned non-string content: {type(content)} (finish_reason: {finish_reason})")

        if not content.strip():
            raise LLMError(
                f"OpenAI API returned empty/whitespace content (finish_reason: {finish_reason}, content length: {len(content)})"
            )

        return content


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
        stop_reason = data.get("stop_reason", "unknown")
        content_list = data.get("content") or []
        if not content_list:
            raise LLMError(f"Anthropic API returned empty content list (stop_reason: {stop_reason})")
        first = content_list[0]
        if not isinstance(first, dict):
            raise LLMError(f"Anthropic API returned invalid content block: {type(first)} (stop_reason: {stop_reason})")
        if first.get("type") != "text":
            raise LLMError(
                f"Anthropic API returned non-text content block: {first.get('type')} (stop_reason: {stop_reason})"
            )
        text = first.get("text")
        if text is None:
            raise LLMError(f"Anthropic API returned null text in content block (stop_reason: {stop_reason})")
        if not isinstance(text, str):
            raise LLMError(f"Anthropic API returned non-string text: {type(text)} (stop_reason: {stop_reason})")
        if not text.strip():
            raise LLMError(
                f"Anthropic API returned empty/whitespace text (stop_reason: {stop_reason}, text length: {len(text)})"
            )
        return text


def call_llm(
    system_prompt: str,
    user_msg: str,
    max_tokens: int = 1000,
    timeout: float = 60.0,
) -> str:
    """Call the configured LLM (OpenAI or Anthropic) and return the response text."""
    api_key, model, provider = get_llm_config()

    if not api_key:
        log.error("call_llm: no API key configured")
        raise LLMError("no_api_key")

    log.debug(f"call_llm: provider={provider} model={model} max_tokens={max_tokens}")

    if provider == "anthropic":
        result = _call_anthropic(api_key, model, system_prompt, user_msg, max_tokens, timeout)
    else:
        result = _call_openai(api_key, model, system_prompt, user_msg, max_tokens, timeout)

    log.debug(f"call_llm: response length={len(result)} chars")
    return result


def synthesize_answer(
    query: str,
    memories: list[dict],
    timeout: float = 60.0,
) -> str | None:
    log.debug(f"synthesize_answer: query='{query[:50]}...' memories={len(memories)}")
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

    result = call_llm(SYSTEM_PROMPT, user_msg, max_tokens=1000, timeout=timeout)
    log.debug(f"synthesize_answer: synthesized answer")
    return result
