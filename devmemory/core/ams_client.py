"""
AMS Client stub for local mode.

This module provides a stub implementation when AMS is not available.
In local mode, AMS features are disabled.
"""


class AMSClient:
    """Stub AMS client for local mode."""

    def __init__(self, *args, **kwargs):
        raise RuntimeError(
            "AMS features require cloud mode. Use 'devmemory install --mode cloud --api-key YOUR_KEY' to enable."
        )


class MemoryResult:
    """Stub MemoryResult for local mode."""

    pass


class SummaryView:
    """Stub SummaryView for local mode."""

    pass
