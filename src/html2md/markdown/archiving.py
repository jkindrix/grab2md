"""Shared conversion-to-archive coordination for batch and crawl workflows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from html2md.markdown.archive import (
    ArtifactManifest,
    ArtifactRecord,
    OutputPlanner,
)
from html2md.markdown.pipeline import AcquiredPage, ConvertedDocument


@dataclass(frozen=True)
class ArchiveOutcome:
    """Durable output selected for one requested page."""

    output_path: Path
    reused: bool


class ArchiveCoordinator:
    """Apply redirect/canonical deduplication and durable registration once."""

    def __init__(
        self,
        *,
        manifest: ArtifactManifest,
        planner: OutputPlanner,
        write_text: Callable[[Path, str], None],
    ) -> None:
        self.manifest = manifest
        self.planner = planner
        self.write_text = write_text

    def archive(
        self,
        requested_url: str,
        page: AcquiredPage,
        convert: Callable[[Path], ConvertedDocument],
    ) -> ArchiveOutcome:
        """Convert only when needed, then write and register one durable artifact."""
        existing = self.manifest.resolve(page.final_url)
        if existing is not None:
            self.manifest.register_alias(requested_url, existing)
            return ArchiveOutcome(existing.output_path, reused=True)

        output_path = self.planner.plan(page.final_url)
        document = convert(output_path)
        canonical_url = document.metadata.canonical_url
        canonical_record = (
            self.manifest.resolve(canonical_url) if canonical_url else None
        )
        if canonical_record is not None:
            self.manifest.register_alias(requested_url, canonical_record)
            self.manifest.register_alias(page.final_url, canonical_record)
            return ArchiveOutcome(canonical_record.output_path, reused=True)

        self.write_text(output_path, document.markdown)
        self.manifest.register(
            ArtifactRecord(
                requested_url=requested_url,
                final_url=page.final_url,
                canonical_url=canonical_url,
                output_path=output_path,
            )
        )
        return ArchiveOutcome(output_path, reused=False)
