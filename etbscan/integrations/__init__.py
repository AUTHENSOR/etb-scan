"""Adapters that let etb-scan measure judges belonging to other frameworks.

Each submodule imports its framework lazily and raises a clear ImportError if
it is absent, so `etbscan` itself stays stdlib-only and dependency-free.
"""
