"""Tests for markdown normalizer."""
from __future__ import annotations

from hephaestus.forgebase.ingestion.markdown_normalizer import normalize_markdown


class TestStripExcessiveBlankLines:
    def test_strips_excessive_blank_lines(self) -> None:
        raw = b"Hello\n\n\n\n\nWorld"
        result = normalize_markdown(raw)
        text = result.decode("utf-8")
        # Max 2 consecutive newlines (1 blank line between paragraphs)
        assert "\n\n\n" not in text
        assert text == "Hello\n\nWorld\n"


class TestNormalizesLineEndings:
    def test_normalizes_line_endings(self) -> None:
        raw = b"Line one\r\nLine two\rLine three\nLine four"
        result = normalize_markdown(raw)
        text = result.decode("utf-8")
        assert "\r" not in text
        assert text == "Line one\nLine two\nLine three\nLine four\n"


class TestEnsuresHeadingSpacing:
    def test_ensures_heading_spacing(self) -> None:
        raw = b"Some text\n# Heading\nMore text"
        result = normalize_markdown(raw)
        text = result.decode("utf-8")
        # There should be a blank line before the heading
        assert "\n\n# Heading\n\n" in text

    def test_heading_at_start_of_document(self) -> None:
        raw = b"# Title\nSome text"
        result = normalize_markdown(raw)
        text = result.decode("utf-8")
        # Heading at start should not have leading blank line
        assert text.startswith("# Title\n\n")

    def test_multiple_heading_levels(self) -> None:
        raw = b"Text\n## Heading 2\nMore text\n### Heading 3\nEnd"
        result = normalize_markdown(raw)
        text = result.decode("utf-8")
        assert "\n\n## Heading 2\n\n" in text
        assert "\n\n### Heading 3\n\n" in text


class TestStripsHtmlComments:
    def test_strips_html_comments(self) -> None:
        raw = b"Hello <!-- this is a comment --> World"
        result = normalize_markdown(raw)
        text = result.decode("utf-8")
        assert "<!--" not in text
        assert "comment" not in text
        assert "Hello  World" in text

    def test_strips_multiline_html_comments(self) -> None:
        raw = b"Before\n<!-- multi\nline\ncomment -->\nAfter"
        result = normalize_markdown(raw)
        text = result.decode("utf-8")
        assert "<!--" not in text
        assert "Before" in text
        assert "After" in text


class TestHandlesEmptyInput:
    def test_handles_empty_input(self) -> None:
        result = normalize_markdown(b"")
        assert result == b""

    def test_handles_whitespace_only(self) -> None:
        result = normalize_markdown(b"   \n\n   ")
        assert result.decode("utf-8").strip() == ""


class TestHandlesUtf8WithSpecialChars:
    def test_handles_utf8_with_special_chars(self) -> None:
        raw = "Hello café résumé naïve 日本語".encode("utf-8")
        result = normalize_markdown(raw)
        text = result.decode("utf-8")
        assert "café" in text
        assert "日本語" in text

    def test_handles_invalid_utf8_gracefully(self) -> None:
        # Invalid UTF-8 byte sequence
        raw = b"Hello \xff\xfe World"
        result = normalize_markdown(raw)
        # Should not raise, should use replacement characters
        text = result.decode("utf-8")
        assert "Hello" in text
        assert "World" in text
