from __future__ import annotations

from hephaestus.core.json_utils import extract_outermost_json_object


def test_extract_outermost_json_object_balances_nested_braces() -> None:
    raw = 'prefix {"outer": {"inner": 1}, "text": "brace } inside"} suffix {"second": true}'
    assert extract_outermost_json_object(raw) == '{"outer": {"inner": 1}, "text": "brace } inside"}'


def test_extract_outermost_json_object_returns_none_without_json() -> None:
    assert extract_outermost_json_object("no json here") is None
