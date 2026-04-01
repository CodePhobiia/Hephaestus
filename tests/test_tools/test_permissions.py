"""Tests for the permission system."""

from pathlib import Path

import pytest

from hephaestus.tools.permissions import (
    DANGEROUS_TOOLS,
    READ_TOOLS,
    SAFE_TOOLS,
    WRITE_TOOLS,
    PermissionMode,
    PermissionPolicy,
    _tool_category,
)


# ---------------------------------------------------------------------------
# PermissionMode enum
# ---------------------------------------------------------------------------

class TestPermissionMode:
    def test_values(self):
        assert PermissionMode.READ_ONLY.value == "read_only"
        assert PermissionMode.WORKSPACE_WRITE.value == "workspace_write"
        assert PermissionMode.FULL_ACCESS.value == "full_access"

    def test_is_string_enum(self):
        assert isinstance(PermissionMode.READ_ONLY, str)


# ---------------------------------------------------------------------------
# _tool_category helper
# ---------------------------------------------------------------------------

class TestToolCategory:
    def test_read_tools(self):
        assert _tool_category("read_file") == "read"
        assert _tool_category("list_directory") == "read"

    def test_write_tools(self):
        assert _tool_category("write_file") == "write"
        assert _tool_category("export") == "write"

    def test_dangerous_tools(self):
        assert _tool_category("web_search") == "dangerous"
        assert _tool_category("web_fetch") == "dangerous"

    def test_unknown_is_safe(self):
        assert _tool_category("some_unknown_tool") == "safe"


# ---------------------------------------------------------------------------
# PermissionPolicy
# ---------------------------------------------------------------------------

class TestPermissionPolicyReadOnly:
    @pytest.fixture()
    def policy(self):
        return PermissionPolicy(PermissionMode.READ_ONLY)

    def test_read_allowed(self, policy):
        assert policy.check("read_file") is True

    def test_safe_allowed(self, policy):
        assert policy.check("calculator") is True

    def test_write_denied(self, policy):
        assert policy.check("write_file") is False

    def test_dangerous_denied(self, policy):
        assert policy.check("web_search") is False


class TestPermissionPolicyWorkspaceWrite:
    @pytest.fixture()
    def policy(self, tmp_path):
        return PermissionPolicy(PermissionMode.WORKSPACE_WRITE, workspace_root=tmp_path)

    def test_read_allowed(self, policy):
        assert policy.check("read_file") is True

    def test_write_allowed(self, policy):
        assert policy.check("write_file") is True

    def test_dangerous_denied(self, policy):
        assert policy.check("web_search") is False

    def test_workspace_root_stored(self, policy, tmp_path):
        assert policy.workspace_root == tmp_path.resolve()


class TestPermissionPolicyFullAccess:
    @pytest.fixture()
    def policy(self):
        return PermissionPolicy(PermissionMode.FULL_ACCESS)

    def test_read_allowed(self, policy):
        assert policy.check("read_file") is True

    def test_write_allowed(self, policy):
        assert policy.check("write_file") is True

    def test_dangerous_allowed(self, policy):
        assert policy.check("web_search") is True

    def test_safe_allowed(self, policy):
        assert policy.check("list_inventions") is True


class TestExplainDenial:
    def test_write_denial(self):
        policy = PermissionPolicy(PermissionMode.READ_ONLY)
        msg = policy.explain_denial("write_file")
        assert "WORKSPACE_WRITE" in msg
        assert "read_only" in msg

    def test_dangerous_denial(self):
        policy = PermissionPolicy(PermissionMode.READ_ONLY)
        msg = policy.explain_denial("web_search")
        assert "FULL_ACCESS" in msg

    def test_category_sets_non_overlapping(self):
        """Read, write, dangerous, and safe sets should not overlap."""
        all_sets = [READ_TOOLS, WRITE_TOOLS, DANGEROUS_TOOLS]
        for i, a in enumerate(all_sets):
            for b in all_sets[i + 1:]:
                overlap = a & b
                # SAFE_TOOLS may overlap with READ_TOOLS by design
                assert not (overlap - SAFE_TOOLS), f"Unexpected overlap: {overlap}"
