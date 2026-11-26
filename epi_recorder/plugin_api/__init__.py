"""Versioned plugin interface for paid EPI packages.

This package is the only surface `epi_enterprise` is meant to import. Every
name is a re-export; nothing here changes behaviour. The version is independent
of the package version and only changes when a name is removed.

See the private repo's docs/internal/REFACTOR-PLAN.md for the migration order.
"""
from __future__ import annotations

PLUGIN_API_VERSION = "1.0"

__all__ = ["PLUGIN_API_VERSION"]
