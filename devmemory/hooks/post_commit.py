HOOK_TEMPLATE = """#!/bin/bash

# >>> devmemory post-commit hook >>>
(sleep 2 && devmemory sync --latest 2>/dev/null) &
# <<< devmemory post-commit hook <<<
"""

POST_CHECKOUT_HOOK_TEMPLATE = """#!/bin/bash

# >>> devmemory post-checkout hook >>>
(sleep 2 && devmemory refresh 2>/dev/null) &
# <<< devmemory post-checkout hook <<<
"""
