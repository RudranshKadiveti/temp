from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from exporters.manager import ExportManager
from pipelines.quality_guard import CANONICAL_COLUMNS, QualityGuard
from utils.logger import setup_logger

logger = setup_logger(__name__)


class DataPipeline:
    """Streaming pipeline with deduplication, schema alignment, and incremental export."""

    def __init__(self, output_dir: str = "data/output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.exporter = ExportManager(str(self.output_dir))

        self.total_processed = 0
        self.seen_hashes: set[str] = set()
        self.latest_output_path: Path | None = None
        self.schema_path = self.output_dir / "latest_schema.json"
        self.change_log = self.output_dir / "change_log.jsonl"
        self.quality_guard = QualityGuard(self.output_dir)

    @property
    def current_session_file(self) -> str:
        return self.exporter.session_prefix

    def _record_hash(self, record: dict[str, Any]) -> str:
        identity = "|".join(
            [
                str(record.get("name", "")).strip().lower(),
                str(record.get("brand", "")).strip().lower(),
                str(record.get("url", "")).strip().lower(),
            ]
        )
        return hashlib.sha256(identity.encode("utf-8", errors="ignore")).hexdigest()

    def _track_changes(self, records: list[dict[str, Any]]) -> None:
        with self.change_log.open("a", encoding="utf-8") as f:
            for r in records:
                if "price" in r:
                    f.write(json.dumps({"key": r.get("name", ""), "price": r.get("price", "")}) + "\n")

    async def process_batch(self, records: list[dict[str, Any]], format: str = "csv") -> int:
        if not records:
            return 0

        valid_rows, failed_rows, batch_stats = self.quality_guard.process(records, self.seen_hashes)
        if not valid_rows:
            logger.info(
                "Pipeline dropped batch (seen=%s dropped=%s duplicates=%s)",
                batch_stats.get("seen", 0),
                batch_stats.get("dropped", 0),
                batch_stats.get("duplicates", 0),
            )
            return 0

        fixed_schema = {
            "name": "str|null",
            "description": "str|null",
            "price": "float|null",
            "currency": "str|null",
            "rating": "float|null",
            "reviews_count": "int|null",
            "availability": "str|null",
            "url": "str|null",
            "image_url": "str|null",
            "source": "str|null",
            "scraped_at": "datetime|null",
            "confidence": "float|null",
        }
        self.schema_path.write_text(json.dumps(fixed_schema, indent=2), encoding="utf-8")

        aligned = [{k: row.get(k) for k in CANONICAL_COLUMNS} for row in valid_rows]

        if self.latest_output_path is None:
            self.latest_output_path = self.exporter.write(aligned, format)
        else:
            try:
                self.exporter.append(self.latest_output_path, aligned, format)
            except PermissionError:
                # Automatic file versioning when output is locked by external tools.
                self.latest_output_path = self.exporter.write(aligned, format)

        self._track_changes(aligned)
        self.total_processed += len(aligned)
        logger.info(
            "Pipeline emitted %s records (total=%s, dropped=%s)",
            len(aligned),
            self.total_processed,
            len(failed_rows),
        )
        return len(aligned)

    def get_quality_report(self) -> dict[str, Any]:
        return self.quality_guard.current_report()
