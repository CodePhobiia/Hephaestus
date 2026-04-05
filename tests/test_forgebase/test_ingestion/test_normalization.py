"""Tests for the NormalizationPipeline dispatch."""

from __future__ import annotations

import pytest

from hephaestus.forgebase.domain.enums import SourceFormat
from hephaestus.forgebase.ingestion.normalization import NormalizationPipeline


@pytest.fixture
def pipeline() -> NormalizationPipeline:
    return NormalizationPipeline()


class TestNormalizeMarkdownFormat:
    @pytest.mark.asyncio
    async def test_normalize_markdown_format(self, pipeline: NormalizationPipeline) -> None:
        raw = b"# Title\n\n\n\n\nSome content"
        result = await pipeline.normalize(raw, SourceFormat.MARKDOWN)
        text = result.decode("utf-8")
        assert "# Title" in text
        assert "Some content" in text
        # Excessive blank lines should be cleaned
        assert "\n\n\n" not in text


class TestNormalizeHtmlFormat:
    @pytest.mark.asyncio
    async def test_normalize_html_format(self, pipeline: NormalizationPipeline) -> None:
        raw = b"<html><body><h1>Hello</h1><p>World</p></body></html>"
        result = await pipeline.normalize(raw, SourceFormat.URL)
        text = result.decode("utf-8")
        assert "Hello" in text
        assert "World" in text
        assert "<" not in text


class TestNormalizePdfStub:
    @pytest.mark.asyncio
    async def test_normalize_pdf_stub(self, pipeline: NormalizationPipeline) -> None:
        raw = b"%PDF-1.4 fake pdf content"
        result = await pipeline.normalize(raw, SourceFormat.PDF)
        text = result.decode("utf-8")
        assert "PDF" in text
        assert "not yet implemented" in text


class TestNormalizeImageStub:
    @pytest.mark.asyncio
    async def test_normalize_image_stub(self, pipeline: NormalizationPipeline) -> None:
        raw = b"\x89PNG\r\n\x1a\n fake image"
        result = await pipeline.normalize(
            raw, SourceFormat.IMAGE, metadata={"title": "Architecture Diagram"}
        )
        text = result.decode("utf-8")
        assert "Architecture Diagram" in text
        assert "not yet implemented" in text

    @pytest.mark.asyncio
    async def test_normalize_image_stub_no_metadata(self, pipeline: NormalizationPipeline) -> None:
        raw = b"\x89PNG fake image"
        result = await pipeline.normalize(raw, SourceFormat.IMAGE)
        text = result.decode("utf-8")
        assert "Image" in text


class TestNormalizeCsv:
    @pytest.mark.asyncio
    async def test_normalize_csv(self, pipeline: NormalizationPipeline) -> None:
        raw = b"name,age,city\nAlice,30,NYC\nBob,25,LA"
        result = await pipeline.normalize(raw, SourceFormat.CSV)
        text = result.decode("utf-8")
        # Should produce a markdown table or structured summary
        assert "name" in text
        assert "Alice" in text
        assert "Bob" in text

    @pytest.mark.asyncio
    async def test_normalize_csv_empty(self, pipeline: NormalizationPipeline) -> None:
        raw = b""
        result = await pipeline.normalize(raw, SourceFormat.CSV)
        text = result.decode("utf-8")
        assert "CSV" in text or result == b""


class TestNormalizeJson:
    @pytest.mark.asyncio
    async def test_normalize_json(self, pipeline: NormalizationPipeline) -> None:
        raw = b'{"name": "Alice", "age": 30, "skills": ["Python", "ML"]}'
        result = await pipeline.normalize(raw, SourceFormat.JSON)
        text = result.decode("utf-8")
        assert "Alice" in text
        assert "Python" in text

    @pytest.mark.asyncio
    async def test_normalize_json_array(self, pipeline: NormalizationPipeline) -> None:
        raw = b'[{"id": 1, "value": "a"}, {"id": 2, "value": "b"}]'
        result = await pipeline.normalize(raw, SourceFormat.JSON)
        text = result.decode("utf-8")
        assert "1" in text
        assert "2" in text


class TestNormalizeHephOutput:
    @pytest.mark.asyncio
    async def test_normalize_heph_output(self, pipeline: NormalizationPipeline) -> None:
        raw = b"# Analysis Result\n\n\n\n\nThe model found:\n- Item 1\n- Item 2"
        result = await pipeline.normalize(raw, SourceFormat.HEPH_OUTPUT)
        text = result.decode("utf-8")
        assert "# Analysis Result" in text
        assert "Item 1" in text
        # Should clean up excessive blank lines
        assert "\n\n\n" not in text


class TestNormalizeUnknownFormat:
    @pytest.mark.asyncio
    async def test_normalize_unknown_format(self, pipeline: NormalizationPipeline) -> None:
        raw = b"Some raw content that should pass through unchanged"
        # GITHUB_REPO and SLIDE_DECK and TRANSCRIPT are not specifically handled
        result = await pipeline.normalize(raw, SourceFormat.GITHUB_REPO)
        assert result == raw

    @pytest.mark.asyncio
    async def test_normalize_slide_deck_passthrough(self, pipeline: NormalizationPipeline) -> None:
        raw = b"Slide deck binary data"
        result = await pipeline.normalize(raw, SourceFormat.SLIDE_DECK)
        assert result == raw

    @pytest.mark.asyncio
    async def test_normalize_transcript_passthrough(self, pipeline: NormalizationPipeline) -> None:
        raw = b"Transcript content"
        result = await pipeline.normalize(raw, SourceFormat.TRANSCRIPT)
        assert result == raw
