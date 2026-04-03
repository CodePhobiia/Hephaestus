"""Phase 0 hardening — verification script.

Uses importlib to import individual modules directly, bypassing hephaestus.__init__
which triggers heavy ML and API client imports.
"""
import sys, os, importlib, importlib.util

# Insert src into path
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src')
sys.path.insert(0, SRC)

def _import_module_direct(dotted_name):
    """Import a module by spec, handling partial chains."""
    parts = dotted_name.split('.')
    # Ensure parent packages exist in sys.modules as namespace stubs
    for i in range(1, len(parts)):
        parent = '.'.join(parts[:i])
        if parent not in sys.modules:
            parent_path = os.path.join(SRC, *parts[:i])
            init_path = os.path.join(parent_path, '__init__.py')
            if os.path.isdir(parent_path):
                # Create a minimal namespace package without executing __init__
                spec = importlib.util.spec_from_file_location(parent, init_path)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    sys.modules[parent] = mod
                    # Don't exec — just register namespace
    # Now import the leaf
    file_path = os.path.join(SRC, *parts[:-1], parts[-1] + '.py')
    if not os.path.isfile(file_path):
        file_path = os.path.join(SRC, *parts, '__init__.py')
    spec = importlib.util.spec_from_file_location(dotted_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot find module: {dotted_name} at {file_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[dotted_name] = mod
    spec.loader.exec_module(mod)
    return mod


# ── Pre-load lightweight dependencies manually ──
# file_ops has no heavy deps
file_ops = _import_module_direct('hephaestus.tools.file_ops')

# permissions: just needs its own constants
permissions = _import_module_direct('hephaestus.tools.permissions')


def test_path_traversal():
    from pathlib import Path
    workspace = Path(__file__).parent.resolve()
    file_ops.set_workspace_root(workspace)

    safe = file_ops._resolve_safe_path(str(workspace / "README.md"))
    assert safe == (workspace / "README.md").resolve()

    # The critical test: sibling path (old code used string prefix)
    try:
        file_ops._resolve_safe_path(str(workspace) + "2/evil")
        print("✗ PATH TRAVERSAL BUG: sibling path not blocked!")
        sys.exit(1)
    except PermissionError:
        pass

    try:
        file_ops._resolve_safe_path(str(workspace / ".." / "evil"))
        print("✗ PATH TRAVERSAL BUG: parent path not blocked!")
        sys.exit(1)
    except PermissionError:
        pass

    print("✓ Path traversal: all tests passed")


def test_write_file_append():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        file_ops.set_workspace_root(Path(tmp))
        test_file = str(Path(tmp) / "test_append.txt")

        file_ops.write_file(test_file, "hello")
        file_ops.write_file(test_file, " world", append=True)
        content = file_ops.read_file(test_file)
        assert content == "hello world", f"Expected 'hello world', got '{content}'"

        file_ops.write_file(test_file, "replaced", append=False)
        content = file_ops.read_file(test_file)
        assert content == "replaced", f"Expected 'replaced', got '{content}'"

    print("✓ Write file append: all tests passed")


def test_search_files():
    from pathlib import Path
    workspace = Path(__file__).parent.resolve()
    file_ops.set_workspace_root(workspace)

    result = file_ops.search_files("*.py", str(workspace / "src" / "hephaestus" / "tools"))
    assert "file_ops.py" in result, f"file_ops.py not in search results: {result[:200]}"
    assert "Found" in result

    result = file_ops.grep_search("_resolve_safe_path", str(workspace / "src" / "hephaestus" / "tools"))
    assert "file_ops.py" in result, f"file_ops.py not in grep results: {result[:200]}"
    assert "Found" in result

    print("✓ Search tools: all tests passed")


def test_permissions_default_deny():
    cat = permissions._tool_category
    assert cat("calculator") == "safe", f"calculator should be safe, got {cat('calculator')}"
    assert cat("totally_unknown_123") == "dangerous", f"unknown should be dangerous, got {cat('totally_unknown_123')}"
    assert cat("read_file") == "read"
    assert cat("write_file") == "write"
    print("✓ Permissions default-deny: all tests passed")


def test_ast_calculator():
    """We need defaults.py but it imports from file_ops (which we already loaded)
    and from other modules. Let's test _ast_eval_node and _safe_eval directly."""
    import ast, math, operator

    # Pre-seed modules it needs
    sys.modules['hephaestus.tools.file_ops'] = file_ops

    # Stub out modules defaults.py imports that we don't need
    class StubModule:
        def __getattr__(self, name):
            return lambda *a, **kw: None

    for mod_name in [
        'hephaestus.session.todos',
        'hephaestus.tools.registry',
        'hephaestus.tools.web_tools',
    ]:
        if mod_name not in sys.modules:
            sys.modules[mod_name] = StubModule()

    # Also need TodoList, ToolDefinition, ToolRegistry, web_fetch, web_search
    td_stub = StubModule()
    td_stub.TodoList = type('TodoList', (), {})
    sys.modules['hephaestus.session.todos'] = td_stub

    reg_stub = StubModule()
    def _td_init(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)
    reg_stub.ToolDefinition = type('ToolDefinition', (), {'__init__': _td_init})
    reg_stub.ToolRegistry = type('ToolRegistry', (), {'__init__': lambda self, **kw: None})
    sys.modules['hephaestus.tools.registry'] = reg_stub

    web_stub = StubModule()
    web_stub.web_fetch = lambda *a, **kw: None
    web_stub.web_search = lambda *a, **kw: None
    sys.modules['hephaestus.tools.web_tools'] = web_stub

    defaults = _import_module_direct('hephaestus.tools.defaults')
    safe_eval = defaults._safe_eval

    # Basic arithmetic
    assert safe_eval("2 + 3") == "5"
    assert safe_eval("10 * 5 - 3") == "47"
    assert safe_eval("100 / 4") == "25.0"
    assert safe_eval("2 ** 10") == "1024"
    assert safe_eval("7 // 2") == "3"
    assert safe_eval("17 % 5") == "2"

    # Unary
    assert safe_eval("-5") == "-5"
    assert safe_eval("-(3 + 2)") == "-5"

    # Whitelisted functions
    assert safe_eval("abs(-42)") == "42"
    assert safe_eval("max(3, 7, 1)") == "7"
    assert safe_eval("min(3, 7, 1)") == "1"
    assert safe_eval("round(3.14159, 2)") == "3.14"

    # Attack vectors
    attacks = [
        "__import__('os').system('echo pwned')",
        "eval('1+1')",
        "exec('import os')",
        "().__class__.__bases__[0].__subclasses__()",
        "open('/etc/passwd').read()",
        "lambda: 1",
        "[x for x in range(10)]",
        "{'a': 1}",
    ]
    for attack in attacks:
        result = safe_eval(attack)
        assert result.startswith("Calculation error"), f"Attack not blocked: {attack} -> {result}"

    # Length limit
    long_expr = "1+" * 300 + "1"
    result = safe_eval(long_expr)
    assert "too long" in result

    # Exponent guard
    result = safe_eval("2 ** 10000")
    assert "too large" in result

    print("✓ AST calculator: all tests passed")


if __name__ == "__main__":
    test_path_traversal()
    test_write_file_append()
    test_search_files()
    test_permissions_default_deny()
    test_ast_calculator()
    print()
    print("=" * 50)
    print("ALL PHASE 0 VERIFICATION TESTS PASSED")
    print("=" * 50)
