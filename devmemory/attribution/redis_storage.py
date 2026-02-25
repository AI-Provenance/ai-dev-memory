from __future__ import annotations

import json
from typing import Optional
import redis
from devmemory.core.logging_config import get_logger

log = get_logger(__name__)

# TTL constants (in seconds)
ATTR_TTL_SECONDS = 365 * 24 * 3600  # 1 year
DEPLOY_TTL_SECONDS = 30 * 24 * 3600  # 30 days


class AttributionStorage:
    """Store and retrieve line-level AI attribution data in Redis."""

    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url, decode_responses=True)
        log.debug(f"AttributionStorage: initialized with {redis_url}")

    def _attr_key(self, namespace: str, filepath: str, commit_sha: str) -> str:
        """
        Generate Redis key for attribution data.

        Key format: attr:{namespace}:{filepath}:{commit_sha}
        Note: namespace already includes repo_id from config.get_active_namespace()
        """
        # namespace is already fully qualified (e.g., "default:git-github-com-org-repo")
        return f"attr:{namespace}:{filepath}:{commit_sha}"

    def _deploy_key(self, namespace: str, release: str) -> str:
        """Generate Redis key for deployment mapping."""
        return f"deploy:{namespace}:{release}"

    def store_attribution(
        self,
        namespace: str,
        filepath: str,
        commit_sha: str,
        author_email: str,
        line_ranges: dict[str, dict],
    ) -> None:
        """
        Store line-level attribution for a file.

        Args:
            namespace: Repository namespace (e.g., "acme/payments")
            filepath: Source file path (e.g., "src/auth.js")
            commit_sha: Git commit SHA
            author_email: Committer email
            line_ranges: Dict mapping line ranges to attribution data
                         e.g., {"1-45": {"author": "ai", "tool": "cursor", "prompt_id": "abc"}}
        """
        key = self._attr_key(namespace, filepath, commit_sha)

        # Store line ranges as hash fields
        pipe = self.redis.pipeline()
        for range_str, attr in line_ranges.items():
            attr["author_email"] = author_email
            pipe.hset(key, range_str, json.dumps(attr))

        # Add metadata
        pipe.hset(
            key,
            "_meta",
            json.dumps(
                {
                    "filepath": filepath,
                    "commit_sha": commit_sha,
                    "author_email": author_email,
                }
            ),
        )

        pipe.expire(key, ATTR_TTL_SECONDS)
        pipe.execute()

        log.debug(f"Stored attribution for {filepath}@{commit_sha[:8]} ({len(line_ranges)} ranges)")

    def store_deployment(
        self,
        namespace: str,
        release: str,
        commit_sha: str,
    ) -> None:
        """
        Store release → commit SHA mapping.

        Args:
            namespace: Repository namespace
            release: Release version (e.g., "v2.3.1")
            commit_sha: Git commit SHA
        """
        key = self._deploy_key(namespace, release)
        self.redis.set(key, commit_sha, ex=DEPLOY_TTL_SECONDS)
        log.debug(f"Stored deployment mapping: {release} -> {commit_sha[:8]}")

    def get_attribution(
        self,
        namespace: str,
        filepath: str,
        commit_sha: str,
        lineno: int,
    ) -> Optional[dict]:
        """
        Get attribution for a specific line.

        Returns:
            Attribution dict with keys: author, tool, model, prompt_id, author_email
            Returns {"author": "human"} if no AI attribution found for the line.
        """
        key = self._attr_key(namespace, filepath, commit_sha)

        # Get all ranges and find the one containing lineno
        ranges = self.redis.hgetall(key)

        # Skip metadata
        range_keys = [k for k in ranges.keys() if k != "_meta"]

        for range_str in range_keys:
            try:
                start, end = map(int, range_str.split("-"))
                if start <= lineno <= end:
                    attr = json.loads(ranges[range_str])
                    log.debug(f"Found attribution for {filepath}:{lineno} -> {attr.get('author')}")
                    return attr
            except (ValueError, json.JSONDecodeError):
                continue

        log.debug(f"No AI attribution for {filepath}:{lineno}, defaulting to human")
        return {"author": "human"}

    def get_commit_for_release(
        self,
        namespace: str,
        release: str,
    ) -> Optional[str]:
        """Get commit SHA for a release."""
        key = self._deploy_key(namespace, release)
        return self.redis.get(key)

    def get_file_attribution_summary(
        self,
        namespace: str,
        filepath: str,
        commit_sha: str,
    ) -> Optional[dict]:
        """
        Get summary of AI vs human lines for a file.

        Returns:
            Dict with ai_lines, human_lines, total_lines, ai_percentage
        """
        key = self._attr_key(namespace, filepath, commit_sha)
        ranges = self.redis.hgetall(key)

        ai_lines = 0
        human_lines = 0

        for range_str, attr_json in ranges.items():
            if range_str == "_meta":
                continue
            try:
                start, end = map(int, range_str.split("-"))
                line_count = end - start + 1
                attr = json.loads(attr_json)

                if attr.get("author") == "ai":
                    ai_lines += line_count
                else:
                    human_lines += line_count
            except (ValueError, json.JSONDecodeError):
                continue

        total = ai_lines + human_lines
        if total == 0:
            return None

        return {
            "ai_lines": ai_lines,
            "human_lines": human_lines,
            "total_lines": total,
            "ai_percentage": round((ai_lines / total) * 100, 1),
        }

    def close(self) -> None:
        """Close Redis connection."""
        self.redis.close()
