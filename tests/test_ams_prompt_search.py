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
def test_search_prompts_from_redis():
    config = DevMemoryConfig.load()
    client = AMSClient(base_url=config.ams_endpoint)
    ns = config.namespace or "default"

    results = client.search_memories(
        text="stored AI prompt for this repository",
        limit=10,
        namespace=ns,
        topics=["prompt"],
    )

    assert isinstance(results, list)
    for r in results:
        assert r.id
        assert r.text is not None
        assert r.topics is not None

    prompt_memories = [r for r in results if "prompt" in r.topics]
    print(prompt_memories)
    if prompt_memories:
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
    print(results)
    assert isinstance(results, list)
    for r in results:
        assert r.id and r.text is not None and r.topics is not None
    prompt_like = [r for r in results if "prompt" in r.topics or "Prompt to" in r.text or "Stored AI prompt" in r.text]
    if prompt_like:
        assert any("Prompt to" in r.text or "Stored AI prompt" in r.text for r in prompt_like)
