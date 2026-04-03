"""Tests for the permission system."""

from pathlib import Path

import pytest

from hephaestus.tools.permissions import (
    PermissionMode,
    PermissionPolicy,
    _tool_category,
)
from types import SimpleNamespace
from unittest.mock import MagicMock

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

@pytest.fixture()
def registry():
    reg = MagicMock()
    def get_tool(name):
        if name in ("read_file", "list_directory"):
            return SimpleNamespace(category="read")
        if name in ("write_file", "export"):
            return SimpleNamespace(category="write")
        if name in ("web_search", "web_fetch"):
            return SimpleNamespace(category="dangerous")
        if name in ("calculator", "list_inventions"):
            return SimpleNamespace(category="safe")
        return None
    reg.get.side_effect = get_tool
    return reg


class TestToolCategory:
    def test_read_tools(self, registry):
        assert _tool_category("read_file", registry) == "read"
        assert _tool_category("list_directory", registry) == "read"

    def test_write_tools(self, registry):
        assert _tool_category("write_file", registry) == "write"
        assert _tool_category("export", registry) == "write"

    def test_dangerous_tools(self, registry):
        assert _tool_category("web_search", registry) == "dangerous"
        assert _tool_category("web_fetch", registry) == "dangerous"

    def test_unknown_is_dangerous(self, registry):
        assert _tool_category("some_unknown_tool", registry) == "dangerous"
        assert _tool_category("some_unknown_tool") == "dangerous"


# ---------------------------------------------------------------------------
# PermissionPolicy
# ---------------------------------------------------------------------------

class TestPermissionPolicyReadOnly:
    @pytest.fixture()
    def policy(self, registry):
        return PermissionPolicy(PermissionMode.READ_ONLY, registry=registry)

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
    def policy(self, tmp_path, registry):
        return PermissionPolicy(PermissionMode.WORKSPACE_WRITE, workspace_root=tmp_path, registry=registry)

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
    def policy(self, registry):
        return PermissionPolicy(PermissionMode.FULL_ACCESS, registry=registry)

    def test_read_allowed(self, policy):
        assert policy.check("read_file") is True

    def test_write_allowed(self, policy):
        assert policy.check("write_file") is True

    def test_dangerous_allowed(self, policy):
        assert policy.check("web_search") is True

    def test_safe_allowed(self, policy):
        assert policy.check("list_inventions") is True


class TestExplainDenial:
    def test_write_denial(self, registry):
        policy = PermissionPolicy(PermissionMode.READ_ONLY, registry=registry)
        msg = policy.explain_denial("write_file")
        assert "WORKSPACE_WRITE" in msg
        assert "read_only" in msg

    def test_dangerous_denial(self, registry):
        policy = PermissionPolicy(PermissionMode.READ_ONLY, registry=registry)
        msg = policy.explain_denial("web_search")
        assert "FULL_ACCESS" in msg
