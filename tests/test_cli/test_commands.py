"""Tests for the shared slash-command registry."""

from __future__ import annotations

import pytest

from hephaestus.cli.commands import Command, CommandRegistry, default_registry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cmd(**overrides) -> Command:
    defaults = dict(
        name="test",
        aliases=["t"],
        description="A test command",
        usage="/test [arg]",
        category="session",
        handler_name="_cmd_test",
        modes=["all"],
        resume_safe=True,
        args_required=False,
    )
    defaults.update(overrides)
    return Command(**defaults)


def _fresh_registry() -> CommandRegistry:
    reg = CommandRegistry()
    reg.register(_make_cmd(name="alpha", aliases=["a"], category="session", usage="/alpha"))
    reg.register(_make_cmd(name="beta", aliases=["b"], category="invention", usage="/beta [arg]"))
    reg.register(_make_cmd(name="gamma", aliases=[], category="session", modes=["repl"], usage="/gamma"))
    return reg


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

class TestRegistration:
    def test_register_and_get_by_name(self):
        reg = CommandRegistry()
        cmd = _make_cmd()
        reg.register(cmd)
        assert reg.get("test") is cmd

    def test_get_by_alias(self):
        reg = CommandRegistry()
        cmd = _make_cmd()
        reg.register(cmd)
        assert reg.get("t") is cmd

    def test_get_case_insensitive(self):
        reg = CommandRegistry()
        cmd = _make_cmd()
        reg.register(cmd)
        assert reg.get("TEST") is cmd
        assert reg.get("T") is cmd

    def test_duplicate_name_raises(self):
        reg = CommandRegistry()
        reg.register(_make_cmd())
        with pytest.raises(ValueError, match="Duplicate command name"):
            reg.register(_make_cmd())

    def test_alias_collision_raises(self):
        reg = CommandRegistry()
        reg.register(_make_cmd(name="one", aliases=["x"]))
        with pytest.raises(ValueError, match="conflicts"):
            reg.register(_make_cmd(name="two", aliases=["x"]))

    def test_alias_collides_with_existing_name(self):
        reg = CommandRegistry()
        reg.register(_make_cmd(name="foo", aliases=[]))
        with pytest.raises(ValueError, match="conflicts"):
            reg.register(_make_cmd(name="bar", aliases=["foo"]))


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------

class TestLookup:
    def test_unknown_command_returns_none(self):
        reg = CommandRegistry()
        assert reg.get("nonexistent") is None

    def test_get_returns_none_for_empty_string(self):
        reg = CommandRegistry()
        assert reg.get("") is None


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------

class TestListCommands:
    def test_list_all(self):
        reg = _fresh_registry()
        assert len(reg.list_commands()) == 3

    def test_list_by_category(self):
        reg = _fresh_registry()
        session_cmds = reg.list_commands(category="session")
        assert len(session_cmds) == 2
        assert all(c.category == "session" for c in session_cmds)

    def test_list_by_mode_filters(self):
        reg = _fresh_registry()
        # gamma has modes=["repl"]; alpha/beta have modes=["all"]
        agent_cmds = reg.list_commands(mode="agent")
        names = {c.name for c in agent_cmds}
        assert "gamma" not in names
        assert "alpha" in names
        assert "beta" in names

    def test_list_by_mode_repl_includes_repl_only(self):
        reg = _fresh_registry()
        repl_cmds = reg.list_commands(mode="repl")
        names = {c.name for c in repl_cmds}
        assert "gamma" in names  # modes=["repl"]
        assert "alpha" in names  # modes=["all"]

    def test_list_unknown_category_empty(self):
        reg = _fresh_registry()
        assert reg.list_commands(category="nonexistent") == []


# ---------------------------------------------------------------------------
# Help formatting
# ---------------------------------------------------------------------------

class TestFormatHelp:
    def test_format_help_nonempty(self):
        reg = _fresh_registry()
        text = reg.format_help()
        assert "Session" in text
        assert "Invention" in text
        assert "/alpha" in text or "alpha" in text

    def test_format_help_empty_registry(self):
        reg = CommandRegistry()
        assert "No commands" in reg.format_help()


# ---------------------------------------------------------------------------
# Completions
# ---------------------------------------------------------------------------

class TestCompletions:
    def test_completions_prefix(self):
        reg = _fresh_registry()
        assert "/alpha" in reg.completions("al")

    def test_completions_with_slash(self):
        reg = _fresh_registry()
        assert "/beta" in reg.completions("/b")

    def test_completions_includes_aliases(self):
        reg = _fresh_registry()
        assert "/a" in reg.completions("a")

    def test_completions_empty_prefix_returns_all(self):
        reg = _fresh_registry()
        comps = reg.completions("")
        assert len(comps) >= 3  # 3 commands + aliases

    def test_completions_respects_mode(self):
        reg = _fresh_registry()
        comps = reg.completions("g", mode="agent")
        assert "/gamma" not in comps  # gamma is repl-only


# ---------------------------------------------------------------------------
# parse_command
# ---------------------------------------------------------------------------

class TestParseCommand:
    def test_parse_simple(self):
        reg = _fresh_registry()
        cmd, args = reg.parse_command("/alpha")
        assert cmd is not None
        assert cmd.name == "alpha"
        assert args == ""

    def test_parse_with_args(self):
        reg = _fresh_registry()
        cmd, args = reg.parse_command("/beta some arguments here")
        assert cmd is not None
        assert cmd.name == "beta"
        assert args == "some arguments here"

    def test_parse_alias(self):
        reg = _fresh_registry()
        cmd, args = reg.parse_command("/a")
        assert cmd is not None
        assert cmd.name == "alpha"

    def test_parse_unknown(self):
        reg = _fresh_registry()
        cmd, args = reg.parse_command("/unknown")
        assert cmd is None
        assert args == ""

    def test_parse_empty_string(self):
        reg = _fresh_registry()
        cmd, args = reg.parse_command("")
        assert cmd is None

    def test_parse_no_slash(self):
        reg = _fresh_registry()
        cmd, args = reg.parse_command("alpha")
        assert cmd is None

    def test_parse_whitespace_stripped(self):
        reg = _fresh_registry()
        cmd, args = reg.parse_command("  /alpha   foo  ")
        assert cmd is not None
        assert args == "foo"


# ---------------------------------------------------------------------------
# default_registry coverage
# ---------------------------------------------------------------------------

EXPECTED_COMMANDS = {
    "help", "status", "quit", "clear", "history", "compare",
    "usage", "cost", "refine", "alternatives", "deeper", "domain",
    "trace", "candidates", "model", "backend", "intensity", "mode",
    "context", "export", "save", "load", "todo", "plan",
    # ForgeBase
    "vault", "ask", "fuse", "ingest", "fb-lint", "fb-compile",
    "workbook", "fb-export",
}


class TestDefaultRegistry:
    def test_all_expected_commands_present(self):
        reg = default_registry()
        for name in EXPECTED_COMMANDS:
            assert reg.get(name) is not None, f"Missing command: {name}"

    def test_exit_alias_resolves_to_quit(self):
        reg = default_registry()
        cmd = reg.get("exit")
        assert cmd is not None
        assert cmd.name == "quit"

    def test_help_aliases(self):
        reg = default_registry()
        assert reg.get("h") is not None
        assert reg.get("?") is not None
        assert reg.get("h").name == "help"

    def test_domain_requires_args(self):
        reg = default_registry()
        cmd = reg.get("domain")
        assert cmd is not None
        assert cmd.args_required is True

    def test_load_requires_args(self):
        reg = default_registry()
        cmd = reg.get("load")
        assert cmd is not None
        assert cmd.args_required is True

    def test_handler_names_populated(self):
        reg = default_registry()
        for name in EXPECTED_COMMANDS:
            cmd = reg.get(name)
            assert cmd.handler_name, f"{name} missing handler_name"

    def test_categories_are_known(self):
        reg = default_registry()
        known = {"session", "invention", "config", "context", "export", "workspace", "forgebase"}
        for cmd in reg.list_commands():
            assert cmd.category in known, f"{cmd.name} has unknown category {cmd.category!r}"

    def test_completions_for_slash_r(self):
        reg = default_registry()
        comps = reg.completions("/r")
        assert "/refine" in comps
