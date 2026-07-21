"""Atomic persistence for versioned crawl-state documents."""

from __future__ import annotations

import json
import os
import re
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from grab2md.utils.atomic_writer import atomic_write_json
from grab2md.utils.path_safety import contained_path
from grab2md.utils.redaction import get_redacting_logger
from grab2md.utils.state_schema import CrawlState

logger = get_redacting_logger(__name__)

SAFE_CRAWL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")
MINIMUM_CRAWL_ID_PREFIX = 8


class CrawlStateStore:
    def __init__(self, state_dir: Path) -> None:
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _validate_crawl_id(crawl_id: str) -> str:
        if not SAFE_CRAWL_ID.fullmatch(crawl_id):
            raise ValueError(f"Invalid crawl ID: {crawl_id!r}")
        return crawl_id

    def _state_path(self, crawl_id: str) -> Path:
        safe_id = self._validate_crawl_id(crawl_id)
        return contained_path(self.state_dir, f"{safe_id}.json")

    def _resolve_crawl_id(self, crawl_id: str) -> str:
        """Resolve an exact ID or one unambiguous displayed prefix."""
        safe_id = self._validate_crawl_id(crawl_id)
        exact = self._state_path(safe_id)
        if exact.exists():
            return safe_id
        if len(safe_id) < MINIMUM_CRAWL_ID_PREFIX:
            return safe_id
        matches = sorted(
            path.stem
            for path in self.state_dir.glob("*.json")
            if path.stem.startswith(safe_id) and SAFE_CRAWL_ID.fullmatch(path.stem)
        )
        if len(matches) > 1:
            raise ValueError(
                f"Crawl ID prefix {crawl_id!r} is ambiguous; use the full ID"
            )
        return matches[0] if matches else safe_id

    def load(self, crawl_id: str) -> Optional[CrawlState]:
        resolved_id = self._resolve_crawl_id(crawl_id)
        state_file = self._state_path(resolved_id)
        if not state_file.exists():
            logger.error("State file not found: %s", state_file)
            return None
        for unresolved_candidate in (state_file, state_file.with_suffix(".bak")):
            candidate = contained_path(self.state_dir, unresolved_candidate)
            if not candidate.exists():
                continue
            try:
                state = CrawlState.from_dict(
                    json.loads(candidate.read_text(encoding="utf-8"))
                )
                if state.crawl_id != resolved_id:
                    raise ValueError(
                        f"State document ID {state.crawl_id!r} does not match "
                        f"filename {resolved_id!r}"
                    )
                return state
            except Exception as error:
                logger.error("Failed to load state from %s: %s", candidate, error)
        return None

    def save(self, state: CrawlState) -> None:
        state_file = self._state_path(state.crawl_id)
        state.last_checkpoint = datetime.now().isoformat()
        if state_file.exists():
            backup_file = contained_path(self.state_dir, state_file.with_suffix(".bak"))
            shutil.copy2(state_file, backup_file)
            if os.name == "posix":
                os.chmod(backup_file, 0o600)
        atomic_write_json(
            state_file,
            state.to_dict(),
            indent=2,
            private=True,
            private_parent=True,
        )

    def list_resumable(self) -> list[Dict[str, Any]]:
        crawls: list[Dict[str, Any]] = []
        for unresolved_state_file in self.state_dir.glob("*.json"):
            try:
                state_file = contained_path(self.state_dir, unresolved_state_file)
                state = CrawlState.from_dict(
                    json.loads(state_file.read_text(encoding="utf-8"))
                )
                if state.crawl_id != state_file.stem:
                    raise ValueError("State document ID does not match its filename")
                crawls.append(
                    {
                        "crawl_id": state.crawl_id,
                        "start_url": state.start_url,
                        "created_at": state.created_at,
                        "last_checkpoint": state.last_checkpoint,
                        "urls_processed": len(state.urls_visited),
                        "urls_queued": len(state.urls_queued),
                        "state_file": str(state_file),
                    }
                )
            except Exception as error:
                logger.error("Failed to read state file %s: %s", state_file, error)
        crawls.sort(key=lambda item: str(item["last_checkpoint"]), reverse=True)
        return crawls

    def clean_older_than(self, days: int) -> int:
        cutoff_time = time.time() - (days * 24 * 60 * 60)
        cleaned = 0
        for state_file in self.state_dir.glob("*.json"):
            if state_file.stat().st_mtime >= cutoff_time:
                continue
            state_file.unlink()
            state_file.with_suffix(".bak").unlink(missing_ok=True)
            cleaned += 1
        return cleaned

    def export(self, crawl_id: str, output_file: Path) -> None:
        state = self.load(crawl_id)
        if state is None:
            raise ValueError(f"Crawl {crawl_id} not found")
        atomic_write_json(output_file, state.to_dict(), indent=2, private=True)

    def import_file(self, input_file: Path) -> CrawlState:
        state = CrawlState.from_dict(
            json.loads(Path(input_file).read_text(encoding="utf-8"))
        )
        state.crawl_id = str(uuid.uuid4())
        self.save(state)
        return state
