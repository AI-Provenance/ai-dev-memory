#!/usr/bin/env bash
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

PASS=0
FAIL=0
WARN=0

pass() { echo -e "  ${GREEN}✓${NC} $1"; PASS=$((PASS+1)); }
fail() { echo -e "  ${RED}✗${NC} $1"; FAIL=$((FAIL+1)); }
skip() { echo -e "  ${YELLOW}!${NC} $1"; WARN=$((WARN+1)); }

echo -e "${BOLD}DevMemory Verification${NC}\n"

echo "Docker Services:"
if docker compose ps --format '{{.Service}}' 2>/dev/null | grep -q redis; then
    pass "Redis container is running"
else
    fail "Redis container is not running"
fi

if docker compose ps --format '{{.Service}}' 2>/dev/null | grep -q api; then
    pass "AMS API container is running"
else
    fail "AMS API container is not running"
fi

if docker compose ps --format '{{.Service}}' 2>/dev/null | grep -q mcp; then
    pass "MCP server container is running"
else
    fail "MCP server container is not running"
fi

echo ""
echo "Service Health:"
if curl -sf http://localhost:8000/v1/health >/dev/null 2>&1; then
    pass "AMS API is healthy (port 8000)"
else
    fail "AMS API is not responding on port 8000"
fi

if docker compose exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; then
    pass "Redis responds to PING"
else
    fail "Redis is not responding"
fi

echo ""
echo "Memory Pipeline:"
TEST_ID="verify-test-$(date +%s)"
CREATE_RESP=$(curl -sf -X POST http://localhost:8000/v1/long-term-memory/ \
    -H "Content-Type: application/json" \
    -d "{
        \"memories\": [{
            \"id\": \"$TEST_ID\",
            \"text\": \"DevMemory verification test memory created at $(date -Iseconds)\",
            \"memory_type\": \"semantic\",
            \"topics\": [\"verification\", \"test\"],
            \"entities\": [\"devmemory\"],
            \"namespace\": \"test\",
            \"user_id\": \"verify\"
        }],
        \"deduplicate\": false
    }" 2>&1) || true

if echo "$CREATE_RESP" | grep -q "status"; then
    pass "Created test memory via AMS API"
else
    fail "Failed to create test memory: $CREATE_RESP"
fi

sleep 2

SEARCH_RESP=$(curl -sf -X POST http://localhost:8000/v1/long-term-memory/search \
    -H "Content-Type: application/json" \
    -d '{
        "text": "DevMemory verification test",
        "namespace": {"eq": "test"},
        "limit": 5
    }' 2>&1) || true

if echo "$SEARCH_RESP" | grep -q "verification"; then
    pass "Semantic search finds test memory"
else
    skip "Semantic search did not find test memory (may need more time for embedding)"
fi

curl -sf -X DELETE "http://localhost:8000/v1/long-term-memory?memory_ids=$TEST_ID" >/dev/null 2>&1 || true

echo ""
echo "Git AI:"
if command -v git-ai &>/dev/null || git ai version &>/dev/null 2>&1; then
    VERSION=$(git-ai version 2>/dev/null || git ai version 2>/dev/null || echo "unknown")
    pass "Git AI installed: $VERSION"
else
    skip "Git AI is not installed (optional for basic testing)"
fi

echo ""
echo "DevMemory CLI:"
if command -v devmemory &>/dev/null; then
    pass "devmemory CLI is installed"
else
    skip "devmemory CLI not on PATH (install with: pip install -e .)"
fi

echo ""
echo "Git Hooks:"
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo "")
if [ -n "$REPO_ROOT" ]; then
    HOOK_FILE="$REPO_ROOT/.git/hooks/post-commit"
    if [ -f "$HOOK_FILE" ] && grep -q "devmemory" "$HOOK_FILE"; then
        pass "Post-commit hook installed"
    else
        skip "Post-commit hook not installed (run: devmemory install)"
    fi
else
    skip "Not in a git repository"
fi

echo ""
echo "Cursor MCP Config:"
MCP_FILE="$HOME/.cursor/mcp.json"
if [ -f "$MCP_FILE" ] && grep -q "agent-memory" "$MCP_FILE"; then
    pass "Cursor MCP config found"
else
    skip "Cursor MCP config not found (run: devmemory install)"
fi

echo ""
echo "Cursor Agent Rule:"
if [ -n "$REPO_ROOT" ]; then
    RULE_FILE="$REPO_ROOT/.cursor/rules/devmemory.mdc"
    if [ -f "$RULE_FILE" ]; then
        if grep -q "agent-memory" "$RULE_FILE" && grep -q "search_long_term_memory" "$RULE_FILE"; then
            pass "Cursor agent rule installed (.cursor/rules/devmemory.mdc)"
        else
            skip "Cursor agent rule exists but may be outdated (run: devmemory install)"
        fi
    else
        skip "Cursor agent rule not installed (run: devmemory install)"
    fi
else
    skip "Not in a git repository — cannot check Cursor rule"
fi

echo ""
echo "Cursor Context Rule:"
if [ -n "$REPO_ROOT" ]; then
    CONTEXT_RULE_FILE="$REPO_ROOT/.cursor/rules/devmemory-context.mdc"
    if [ -f "$CONTEXT_RULE_FILE" ]; then
        pass "Context rule installed (.cursor/rules/devmemory-context.mdc)"
    else
        skip "Context rule not installed (run: devmemory install)"
    fi

    CHECKOUT_HOOK="$REPO_ROOT/.git/hooks/post-checkout"
    if [ -f "$CHECKOUT_HOOK" ] && grep -q "devmemory context" "$CHECKOUT_HOOK"; then
        pass "Post-checkout hook installed (auto-refreshes context)"
    else
        skip "Post-checkout hook not installed (run: devmemory install)"
    fi
else
    skip "Not in a git repository — cannot check context rule"
fi

echo ""
echo -e "${BOLD}Results:${NC} ${GREEN}$PASS passed${NC}, ${RED}$FAIL failed${NC}, ${YELLOW}$WARN warnings${NC}"

if [ "$FAIL" -gt 0 ]; then
    echo -e "\n${RED}Some checks failed. Run 'make up' to start services or 'make logs' to debug.${NC}"
    exit 1
else
    echo -e "\n${GREEN}All critical checks passed!${NC}"
fi
