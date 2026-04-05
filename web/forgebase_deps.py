"""ForgeBase dependency injection for FastAPI.

Provides a lazy-initialized singleton ForgeBase instance via FastAPI's
dependency injection system.  The instance is created on first request
and reused for the lifetime of the process.
"""
from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

from fastapi import Depends, Request

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Singleton holder
# ---------------------------------------------------------------------------

_forgebase_instance = None
_forgebase_lock = asyncio.Lock()


async def _get_forgebase():
    """Lazy-create and cache a ForgeBase instance (process-scoped singleton)."""
    global _forgebase_instance
    if _forgebase_instance is not None:
        return _forgebase_instance

    async with _forgebase_lock:
        # Double-check after acquiring lock
        if _forgebase_instance is not None:
            return _forgebase_instance

        from hephaestus.forgebase.factory import ForgeBaseConfig, create_forgebase

        logger.info("Creating ForgeBase instance (lazy init)")
        _forgebase_instance = await create_forgebase(
            ForgeBaseConfig(sqlite_path="forgebase_dev.db"),
        )
        return _forgebase_instance


async def get_forgebase():
    """FastAPI dependency that returns the ForgeBase singleton."""
    return await _get_forgebase()


async def shutdown_forgebase() -> None:
    """Close the ForgeBase instance on app shutdown."""
    global _forgebase_instance
    if _forgebase_instance is not None:
        await _forgebase_instance.close()
        _forgebase_instance = None
        logger.info("ForgeBase instance closed")
