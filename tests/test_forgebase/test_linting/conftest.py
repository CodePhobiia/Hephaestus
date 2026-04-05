"""Shared fixtures for ForgeBase linting tests."""

from __future__ import annotations

import pytest

from hephaestus.forgebase.linting.analyzers.mock_analyzer import MockLintAnalyzer


@pytest.fixture
def mock_analyzer() -> MockLintAnalyzer:
    """Provide a deterministic MockLintAnalyzer for testing."""
    return MockLintAnalyzer()
