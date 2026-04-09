from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

from core.models import Record


class ExportManager:
    def __init__(self, output_dir: str = "data/output", chunk_size: int = 5000) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.chunk_size = chunk_size
        self._session_prefix: str | None = None

    @property
    def session_prefix(self) -> str:
        if self._session_prefix is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            self._session_prefix = f"scrape_session_{ts}"
        return self._session_prefix

    def _versioned_path(self, ext: str) -> Path:
        index = 0
        while True:
            suffix = "" if index == 0 else f"_v{index}"
            path = self.output_dir / f"{self.session_prefix}{suffix}.{ext}"
            if not path.exists():
                return path
            index += 1

    def _iter_chunks(self, records: list[Record]) -> Iterable[list[Record]]:
        for i in range(0, len(records), self.chunk_size):
            yield records[i : i + self.chunk_size]

    def write(self, records: list[Record], fmt: str) -> Path:
        fmt = fmt.lower().strip()
        if fmt in {"csv_file", "csvfile"}:
            fmt = "csv"
        if fmt == "xlsx":
            fmt = "excel"

        if fmt not in {"csv", "json", "jsonl", "excel", "parquet"}:
            raise ValueError(f"Unsupported format: {fmt}")

        ext = "xlsx" if fmt == "excel" else fmt
        path = self._versioned_path(ext)
        if fmt == "csv":
            self._write_csv(path, records)
        elif fmt == "json":
            self._write_json(path, records)
        elif fmt == "jsonl":
            self._write_jsonl(path, records)
        elif fmt == "excel":
            self._write_excel(path, records)
        elif fmt == "parquet":
            self._write_parquet(path, records)
        return path

    def append(self, target: Path, records: list[Record], fmt: str) -> None:
        fmt = fmt.lower().strip()
        if fmt in {"csv_file", "csvfile"}:
            fmt = "csv"
        if fmt == "xlsx":
            fmt = "excel"

        if fmt == "csv":
            self._append_csv(target, records)
        elif fmt == "json":
            self._append_json(target, records)
        elif fmt == "jsonl":
            self._append_jsonl(target, records)
        elif fmt == "excel":
            self._append_excel(target, records)
        elif fmt == "parquet":
            self._append_parquet(target, records)
        else:
            raise ValueError(f"Unsupported format: {fmt}")

    def _write_csv(self, path: Path, records: list[Record]) -> None:
        wrote_header = False
        for chunk in self._iter_chunks(records):
            pd.DataFrame(chunk).to_csv(path, mode="a", index=False, header=not wrote_header)
            wrote_header = True

    def _append_csv(self, path: Path, records: list[Record]) -> None:
        pd.DataFrame(records).to_csv(path, mode="a", index=False, header=not path.exists())

    def _write_json(self, path: Path, records: list[Record]) -> None:
        pd.DataFrame(records).to_json(path, orient="records", force_ascii=False)

    def _append_json(self, path: Path, records: list[Record]) -> None:
        incoming = pd.DataFrame(records)
        if path.exists():
            current = pd.read_json(path)
            merged = pd.concat([current, incoming], ignore_index=True)
        else:
            merged = incoming
        merged.to_json(path, orient="records", force_ascii=False)

    def _write_jsonl(self, path: Path, records: list[Record]) -> None:
        with path.open("w", encoding="utf-8") as f:
            for chunk in self._iter_chunks(records):
                for record in chunk:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _append_jsonl(self, path: Path, records: list[Record]) -> None:
        with path.open("a", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _write_excel(self, path: Path, records: list[Record]) -> None:
        pd.DataFrame(records).to_excel(path, index=False)

    def _append_excel(self, path: Path, records: list[Record]) -> None:
        # Excel appends are expensive; merge-read-write keeps behavior deterministic.
        if path.exists():
            current = pd.read_excel(path)
            merged = pd.concat([current, pd.DataFrame(records)], ignore_index=True)
        else:
            merged = pd.DataFrame(records)
        merged.to_excel(path, index=False)

    def _write_parquet(self, path: Path, records: list[Record]) -> None:
        pd.DataFrame(records).to_parquet(path, engine="fastparquet", index=False)

    def _append_parquet(self, path: Path, records: list[Record]) -> None:
        if path.exists():
            pd.DataFrame(records).to_parquet(path, engine="fastparquet", append=True, index=False)
        else:
            self._write_parquet(path, records)
