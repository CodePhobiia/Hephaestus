from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from hephaestus.core.olympus import _compute_fingerprint, build_olympus


def test_compute_fingerprint_includes_dirty_git_state(tmp_path) -> None:
    root = tmp_path
    (root / ".git").mkdir()

    def _run(cmd, **kwargs):
        if cmd[:3] == ["git", "rev-parse", "HEAD"]:
            return SimpleNamespace(returncode=0, stdout="abc123\n")
        if cmd[:3] == ["git", "status", "--porcelain"]:
            return SimpleNamespace(returncode=0, stdout=" M src/file.py\n")
        raise AssertionError(cmd)

    with patch("subprocess.run", side_effect=_run):
        dirty = _compute_fingerprint("problem", root)

    def _run_clean(cmd, **kwargs):
        if cmd[:3] == ["git", "rev-parse", "HEAD"]:
            return SimpleNamespace(returncode=0, stdout="abc123\n")
        if cmd[:3] == ["git", "status", "--porcelain"]:
            return SimpleNamespace(returncode=0, stdout="")
        raise AssertionError(cmd)

    with patch("subprocess.run", side_effect=_run_clean):
        clean = _compute_fingerprint("problem", root)

    assert dirty != clean


@pytest.mark.asyncio
async def test_build_olympus_skips_without_tool_support(tmp_path) -> None:
    root = tmp_path
    (root / ".git").mkdir()
    adapter = object()

    result = await build_olympus("problem", root, adapter)
    assert result is None


@pytest.mark.asyncio
async def test_build_olympus_uses_cached_context(tmp_path) -> None:
    root = tmp_path
    (root / ".git").mkdir()
    cache_dir = root / ".hephaestus"
    cache_dir.mkdir()
    olympus_path = cache_dir / "OLYMPUS.md"
    fingerprint_path = cache_dir / "olympus_fingerprint.json"
    olympus_path.write_text("# cached", encoding="utf-8")

    with patch("hephaestus.core.olympus._compute_fingerprint", return_value="fp123"):
        fingerprint_path.write_text(
            '{"fingerprint": "fp123", "generated_at": "2026-04-08T00:00:00+00:00"}',
            encoding="utf-8",
        )
        adapter = SimpleNamespace(generate_with_tools=AsyncMock())
        result = await build_olympus("problem", root, adapter)

    assert result is not None
    assert result.olympus_md == "# cached"
    adapter.generate_with_tools.assert_not_awaited()
