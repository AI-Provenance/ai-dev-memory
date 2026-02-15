import hashlib
import pytest

from devmemory.core.ams_client import AMSClient
from devmemory.core.config import DevMemoryConfig


def _ams_available() -> bool:
    config = DevMemoryConfig.load()
    try:
        AMSClient(base_url=config.ams_endpoint).health_check()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _ams_available(), reason="AMS (Redis) not reachable")
def test_store_and_search_prompt_from_redis():
    config = DevMemoryConfig.load()
    client = AMSClient(base_url=config.ams_endpoint)
    ns = config.namespace or "default"

    text = "Stored AI prompt for this repository. Prompt to Cursor/claude-4.5: [user]: fix CLI freeze when running install\nResult: 12 lines added\nCommit: fix: avoid install hook freeze (abc123def456)"
    sample_prompt_memory = {
        "id": hashlib.sha256(f"test_prompt:{text}".encode()).hexdigest()[:24],
        "text": text,
        "memory_type": "semantic",
        "topics": ["prompt", "code-change"],
        "entities": ["devmemory", "install"],
        "namespace": ns,
    }
    client.create_memories([sample_prompt_memory], deduplicate=False)

    results = client.search_memories(
        text="stored AI prompt for this repository",
        limit=10,
        namespace=ns,
        topics=["prompt"],
    )
    assert isinstance(results, list)
    for r in results:
        assert r.id and r.text is not None and r.topics is not None

    prompt_memories = [r for r in results if "prompt" in r.topics]
    assert prompt_memories, "expected at least one memory with topic 'prompt'"
    sample = prompt_memories[0]
    assert "Prompt to" in sample.text or "Stored AI prompt" in sample.text


@pytest.mark.skipif(not _ams_available(), reason="AMS (Redis) not reachable")
def test_search_prompts_by_text_only():
    config = DevMemoryConfig.load()
    client = AMSClient(base_url=config.ams_endpoint)
    ns = config.namespace or "default"

    results = client.search_memories(
        text="what were the last prompts used in this repo",
        limit=5,
        namespace=ns,
    )

    assert isinstance(results, list)
    for r in results:
        assert r.id and r.text is not None and r.topics is not None
    prompt_like = [r for r in results if "prompt" in r.topics or "Prompt to" in r.text or "Stored AI prompt" in r.text]
    if prompt_like:
        assert any("Prompt to" in r.text or "Stored AI prompt" in r.text for r in prompt_like)
