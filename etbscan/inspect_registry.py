"""Inspect extension entry point.

Inspect auto-loads any installed package registered in the ``inspect_ai``
entry-point group. Importing this module registers the ETB task and scorer, so:

    pip install inspect-ai etb-scan
    inspect eval verdict_injection --model openai/gpt-4o

works with no configuration and no manual import.

Import is guarded: if inspect-ai is not installed, this is a no-op rather than
an error, so etb-scan stays usable as a standalone CLI and pytest plugin.
"""

from __future__ import annotations

try:
    from etbscan.inspect_task import no_verdict_injection, verdict_injection

    __all__ = ["verdict_injection", "no_verdict_injection"]
except ImportError:  # inspect-ai not installed; nothing to register
    __all__ = []
