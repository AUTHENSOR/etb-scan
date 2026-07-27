"""Load a judge callable from a dotted path, so CI and plugins can find it.

    etbscan --judge mypkg.judges:my_judge

The target must be a callable taking (candidate, rubric, question) or
(candidate, rubric) and returning a verdict dict.
"""

from __future__ import annotations

import importlib
from typing import Any, Callable


def load_judge(spec: str) -> Callable[..., dict[str, Any]]:
    """Resolve "module.path:attribute" (or "module.path.attribute") to a callable."""
    if ":" in spec:
        mod_name, _, attr = spec.partition(":")
    elif "." in spec:
        mod_name, _, attr = spec.rpartition(".")
    else:
        raise ValueError(
            f"judge spec {spec!r} must be 'module:attr' or 'module.attr'"
        )
    try:
        mod = importlib.import_module(mod_name)
    except ImportError as exc:
        raise ImportError(f"could not import {mod_name!r} from judge spec {spec!r}") from exc
    try:
        judge = getattr(mod, attr)
    except AttributeError as exc:
        raise AttributeError(f"{mod_name!r} has no attribute {attr!r}") from exc
    if not callable(judge):
        raise TypeError(f"{spec!r} resolved to {type(judge).__name__}, which is not callable")
    return judge
