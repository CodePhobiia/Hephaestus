"""MissingFigureDetector — detects images without meaningful alt text or descriptions."""
from __future__ import annotations

import re

from hephaestus.forgebase.domain.enums import FindingCategory, FindingSeverity
from hephaestus.forgebase.domain.models import LintFinding
from hephaestus.forgebase.linting.detectors.base import LintDetector, RawFinding
from hephaestus.forgebase.linting.state import VaultLintState

# Regex patterns for image references in Markdown / HTML
_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]+\)")
_HTML_IMG_RE = re.compile(r"<img\b[^>]*alt=[\"']([^\"']*)[\"'][^>]*/?>", re.IGNORECASE)

# Alt text values considered "missing"
_EMPTY_ALT_TEXTS = frozenset({"", "image", "img", "figure", "photo", "picture"})


class MissingFigureDetector(LintDetector):
    """Detects images with empty or generic alt text in page content.

    This is a data-only detector: it uses regex to scan page content for
    image references (Markdown ``![...]()`` and HTML ``<img>``) and flags
    those with empty or meaningless alt text.
    """

    def __init__(self) -> None:
        pass  # No analyzer needed — pure data detector

    @property
    def name(self) -> str:
        return "missing_figure"

    @property
    def categories(self) -> list[FindingCategory]:
        return [FindingCategory.MISSING_FIGURE_EXPLANATION]

    @property
    def version(self) -> str:
        return "1.0.0"

    async def detect(self, state: VaultLintState) -> list[RawFinding]:
        pages = await state.pages()
        findings: list[RawFinding] = []

        for page, pv in pages:
            try:
                content_bytes = await state.page_content(page.page_id)
            except (ValueError, KeyError):
                continue
            content = content_bytes.decode("utf-8", errors="replace")

            # Find Markdown images
            for match in _MD_IMAGE_RE.finditer(content):
                alt_text = match.group(1).strip()
                if alt_text.lower() in _EMPTY_ALT_TEXTS:
                    findings.append(
                        RawFinding(
                            category=FindingCategory.MISSING_FIGURE_EXPLANATION,
                            severity=FindingSeverity.INFO,
                            description=(
                                f"Image on page '{pv.title}' has "
                                f"{'empty' if not alt_text else 'generic'} "
                                f"alt text: '{alt_text or '(empty)'}'"
                            ),
                            affected_entity_ids=[page.page_id],
                            normalized_subject=f"{page.page_id}:{match.group(0)[:60]}",
                            suggested_action="Add a meaningful description to the image.",
                            confidence=1.0,
                            page_id=page.page_id,
                        )
                    )

            # Find HTML images
            for match in _HTML_IMG_RE.finditer(content):
                alt_text = match.group(1).strip()
                if alt_text.lower() in _EMPTY_ALT_TEXTS:
                    findings.append(
                        RawFinding(
                            category=FindingCategory.MISSING_FIGURE_EXPLANATION,
                            severity=FindingSeverity.INFO,
                            description=(
                                f"HTML image on page '{pv.title}' has "
                                f"{'empty' if not alt_text else 'generic'} "
                                f"alt text: '{alt_text or '(empty)'}'"
                            ),
                            affected_entity_ids=[page.page_id],
                            normalized_subject=f"{page.page_id}:{match.group(0)[:60]}",
                            suggested_action="Add a meaningful alt attribute to the image.",
                            confidence=1.0,
                            page_id=page.page_id,
                        )
                    )

        return findings

    async def is_resolved(
        self,
        original_finding: LintFinding,
        current_state: VaultLintState,
        new_findings: list[RawFinding],
    ) -> bool:
        """Resolved if the image reference now has a meaningful description."""
        # Check if a new finding with the same normalized subject still exists
        if original_finding.page_id is None:
            return True

        # Find the page in current state
        pages = await current_state.pages()
        page_exists = any(p.page_id == original_finding.page_id for p, _pv in pages)
        if not page_exists:
            return True  # Page gone

        # Check if any new finding has the same affected entities
        for new_f in new_findings:
            if (
                new_f.category == FindingCategory.MISSING_FIGURE_EXPLANATION
                and new_f.affected_entity_ids == original_finding.affected_entity_ids
                and new_f.normalized_subject == original_finding.finding_fingerprint
            ):
                return False

        # If no matching new finding, assume the issue is fixed
        return True
