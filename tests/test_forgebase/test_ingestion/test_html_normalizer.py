"""Tests for HTML normalizer."""
from __future__ import annotations

from hephaestus.forgebase.ingestion.html import normalize_html


class TestStripsScriptTags:
    def test_strips_script_tags(self) -> None:
        raw = b"<html><body>Hello<script>alert('xss')</script> World</body></html>"
        result = normalize_html(raw)
        text = result.decode("utf-8")
        assert "script" not in text.lower()
        assert "alert" not in text
        assert "Hello" in text
        assert "World" in text


class TestStripsStyleTags:
    def test_strips_style_tags(self) -> None:
        raw = b"<html><head><style>body{color:red}</style></head><body>Content</body></html>"
        result = normalize_html(raw)
        text = result.decode("utf-8")
        assert "style" not in text.lower()
        assert "color:red" not in text
        assert "Content" in text


class TestStripsAllHtmlTags:
    def test_strips_all_html_tags(self) -> None:
        raw = b"<h1>Title</h1><p>Paragraph with <strong>bold</strong> and <em>italic</em>.</p>"
        result = normalize_html(raw)
        text = result.decode("utf-8")
        assert "<" not in text
        assert ">" not in text
        assert "Title" in text
        assert "Paragraph" in text
        assert "bold" in text
        assert "italic" in text


class TestNormalizesWhitespace:
    def test_normalizes_whitespace(self) -> None:
        raw = b"<p>  Lots   of    spaces  </p>\n\n\n<p> here </p>"
        result = normalize_html(raw)
        text = result.decode("utf-8")
        # No runs of multiple spaces
        assert "   " not in text


class TestPreservesTextContent:
    def test_preserves_text_content(self) -> None:
        raw = b"<div><p>Important information about the project.</p><p>Second paragraph.</p></div>"
        result = normalize_html(raw)
        text = result.decode("utf-8")
        assert "Important information about the project." in text
        assert "Second paragraph." in text


class TestHandlesEmptyInput:
    def test_handles_empty_input(self) -> None:
        result = normalize_html(b"")
        assert result == b""

    def test_handles_empty_tags(self) -> None:
        result = normalize_html(b"<div></div>")
        text = result.decode("utf-8").strip()
        assert "<" not in text
