HOOK_TEMPLATE = """#!/bin/bash

# >>> devmemory post-commit hook >>>
(sleep 2 && devmemory sync --latest 2>/dev/null) &
# <<< devmemory post-commit hook <<<
"""
